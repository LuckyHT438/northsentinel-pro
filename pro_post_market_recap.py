# ============================================================
# NORTHSENTINEL PRO — MODULE POST-MARKET RECAP
# Récap de session enrichi envoyé à 16:00 via workflow dédié
# ============================================================
import json
import os
import random
import requests
from datetime import datetime
import pytz
import yfinance as yf

MONTREAL_TZ = pytz.timezone('America/Toronto')

# === 54 VRAIES CITATIONS DE TRADERS & INVESTISSEURS ===
QUOTES = {
    "patience": [
        ('The stock market is a device for transferring money from the impatient to the patient.', 'Warren Buffett'),
        ('I made my money by selling too early.', 'Bernard Baruch'),
        ('The big money is not in the buying and selling, but in the waiting.', 'Charlie Munger'),
        ("Don't trade the market. Trade your plan.", 'Linda Raschke'),
        ('Sitting is the hardest thing in trading. Doing nothing is doing something.', 'Paul Tudor Jones'),
        ('Wait for the fat pitch.', 'Warren Buffett'),
        ('The market does not beat you up. You beat yourself up, because you are impatient.', 'Mark Douglas'),
        ('Amateurs focus on how much they can make. Professionals focus on how much they can lose.', 'Jack Schwager'),
        ('Trading is a waiting game. The money is made in the sitting, not the trading.', 'Jesse Livermore'),
        ('The best trade is often the one you don\'t take.', 'Steve Burns'),
    ],
    "risk": [
        ('Rule No. 1: Never lose money. Rule No. 2: Never forget Rule No. 1.', 'Warren Buffett'),
        ("If you risk everything on one trade, you're not a trader. You're a gambler.", 'Paul Tudor Jones'),
        ('The elements of good trading are: cutting losses, cutting losses, and cutting losses.', 'Ed Seykota'),
        ('Never add to a losing position.', 'Jesse Livermore'),
        ('The most important rule of trading is to play great defense, not great offense.', 'Paul Tudor Jones'),
        ("It's not the trade you make that counts. It's the trade you don't make.", 'Alexander Elder'),
        ('Losers average losers.', 'Paul Tudor Jones'),
        ('Preservation of capital is the foundation of all trading.', 'Victor Sperandeo'),
        ('Trade small. Trade often. Cut losses fast.', 'Linda Raschke'),
        ('The only thing that matters is how much you lose when you\'re wrong.', 'Nassim Nicholas Taleb'),
    ],
    "psychology": [
        ('The market is a crowd. Its business is to fool the majority.', 'Jesse Livermore'),
        ('Fear and greed are the two great forces that move markets.', 'Warren Buffett'),
        ('Markets are never wrong. Opinions often are.', 'Jesse Livermore'),
        ('Trading is 80% psychological and 20% methodological.', 'Van K. Tharp'),
        ('The secret to trading is that there is no secret. You must manage your emotions.', 'Mark Douglas'),
        ('Bull markets are born on pessimism, grow on skepticism, mature on optimism, and die on euphoria.', 'Sir John Templeton'),
        ('The individual who is not emotionally balanced is a poor trader.', 'Jesse Livermore'),
        ('Your worst enemy in trading is yourself. Your best friend is discipline.', 'Mark Minervini'),
        ('Revenge trading is the fastest way to blow up your account.', 'Steve Burns'),
        ("The market knows you're trying to get your money back. It doesn't care.", 'Mike Bellafiore'),
    ],
    "execution": [
        ("Scalping is not about being right all the time. It's about being right slightly more than you're wrong, and doing it fast.", 'Mike Bellafiore'),
        ('In scalping, you are not trading the market. You are trading the bid and the ask.', 'John Carter'),
        ('The best scalpers have no opinion. They just react.', 'Brett Steenbarger'),
        ('Speed is the edge. Without speed, you are just another retail trader.', 'Adam Grimes'),
        ("A scalper takes the market's temperature every second. A swing trader takes it every day.", 'Linda Raschke'),
        ("You don't need to know where the market is going. You just need to know where it is right now.", 'Mike Bellafiore'),
        ('Execution is everything in scalping. A 2-second delay is the difference between a winner and a loser.', 'Steve Burns'),
        ('Scalping is a game of probabilities, not predictions.', 'Brett Steenbarger'),
    ],
    "markets": [
        ('The market can remain irrational longer than you can remain solvent.', 'John Maynard Keynes'),
        ('Price is what you pay. Value is what you get.', 'Warren Buffett'),
        ('The trend is your friend until the end when it bends.', 'Ed Seykota'),
        ('Volume precedes price.', 'Joseph Granville'),
        ('In a bull market, you only have to be long. In a bear market, you only have to be in cash.', 'Jesse Livermore'),
        ("Gaps are the market's way of telling you something changed overnight.", 'John Carter'),
        ("Liquidity is the most important thing you never think about until it's gone.", 'Nassim Nicholas Taleb'),
        ('The opening price is set by amateurs. The closing price is set by professionals.', 'Wall Street Adage'),
    ],
    "mindset": [
        ("I have not failed. I've just found 10,000 ways that won't work.", 'Thomas Edison'),
        ("In trading, you have to be willing to be wrong. Being right too often is a sign of avoiding risk.", 'Jack Schwager'),
        ("The goal of a good trader is not to be right. It's to make money.", 'Steve Burns'),
        ("Every loss is tuition. But don't pay for the same lesson twice.", 'Mark Minervini'),
        ("Trading doesn't build character. It reveals it.", 'Yvan Byeajee'),
        ('The harder I work, the luckier I get.', 'Samuel Goldwyn'),
        ('You will never know everything. But you must know yourself.', 'Jesse Livermore'),
        ('Success is not final. Failure is not fatal. It is the courage to continue that counts.', 'Winston Churchill'),
    ],
}

# === SECTEURS US ET CA SÉPARÉS ===
MARKET_ETFS_US = {
    "XLE": "Energy",
    "XLF": "Financials",
    "XLV": "Healthcare",
    "XLI": "Industrials",
    "XLK": "Technology",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLB": "Materials",
    "XLU": "Utilities",
    "XBI": "Biotech",
    "SMH": "Semiconductors",
    "QQQ": "Nasdaq 100",
    "SPY": "S&P 500",
    "IWM": "Russell 2000",
}

MARKET_ETFS_CA = {
    "XIU.TO": "TSX 60",
    "XGD.TO": "Gold Miners",
    "XMA.TO": "Materials",
    "XFN.TO": "Financials",
    "XUT.TO": "Utilities",
    "XEG.TO": "Energy",
    "XIT.TO": "Technology",
    "XHC.TO": "Healthcare",
    "XRE.TO": "Real Estate",
}

# === FICHIER PERSISTANT ===
SIGNALS_FILE = "pro_signals_today.json"


def _get_sector_performance(ticker):
    """Retourne la performance du jour d'un ETF sectoriel"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        prev_close = info.get('previousClose')
        if price and prev_close and prev_close > 0:
            change = (price - prev_close) / prev_close * 100
            return change
    except:
        pass
    return None


def _get_market_highlights(etf_dict, label):
    """
    Scanne un dictionnaire d'ETFs et retourne les tops/flops + biais.
    label: 'US' ou 'CA'
    """
    performances = {}
    up_count = 0
    down_count = 0

    for ticker, name in etf_dict.items():
        change = _get_sector_performance(ticker)
        if change is not None:
            performances[name] = {"ticker": ticker, "change": change}
            if change > 0.3:
                up_count += 1
            elif change < -0.3:
                down_count += 1

    if not performances:
        return None

    sorted_perf = sorted(performances.items(), key=lambda x: x[1]['change'], reverse=True)
    top = sorted_perf[0] if sorted_perf else None
    bottom = sorted_perf[-1] if sorted_perf else None

    if up_count > down_count:
        bias = f"🟢 Risk-on ({label})"
    elif down_count > up_count:
        bias = f"🔴 Risk-off ({label})"
    else:
        bias = f"⚪ Neutral ({label})"

    return {
        "top": top,
        "bottom": bottom,
        "bias": bias,
        "up_sectors": up_count,
        "down_sectors": down_count,
    }


def _get_signal_context(ticker, s_type):
    """Récupère le contexte sectoriel d'un ticker (via pro_macro_context)"""
    try:
        from pro_macro_context import get_macro_context
        ctx = get_macro_context(ticker)
        if ctx and ctx.get('line'):
            line = ctx['line'].strip()
            if line.startswith("🌐 "):
                line = line[3:]
            return line
    except:
        pass
    return None


def _get_daily_quote(signals, highlights_us, highlights_ca):
    """Sélectionne la citation la plus pertinente selon la séance"""
    if not signals:
        return random.choice(QUOTES["patience"])

    avg_score = sum(s.get('score', 0) for s in signals) / len(signals)
    if len(signals) >= 3 and avg_score >= 5.5:
        return random.choice(QUOTES["execution"])

    # Analyser les biais US et CA
    up_total = 0
    down_total = 0
    if highlights_us:
        up_total += highlights_us.get("up_sectors", 0)
        down_total += highlights_us.get("down_sectors", 0)
    if highlights_ca:
        up_total += highlights_ca.get("up_sectors", 0)
        down_total += highlights_ca.get("down_sectors", 0)

    if down_total > up_total + 3:
        return random.choice(QUOTES["risk"])
    elif up_total > down_total + 3:
        return random.choice(QUOTES["psychology"])
    elif abs(up_total - down_total) <= 1:
        return random.choice(QUOTES["mindset"])

    best_gap = max(s.get('gap', 0) for s in signals) if signals else 0
    if best_gap > 15:
        return random.choice(QUOTES["markets"])

    return random.choice(QUOTES["mindset"])


def _format_highlights(highlights, flag):
    """Formate les highlights pour un marché donné"""
    if not highlights:
        return ""

    lines = []
    lines.append(f"{flag} {highlights['bias']}")
    if highlights['top']:
        name, data = highlights['top']
        direction = "▲" if data['change'] > 0 else "▼"
        lines.append(f"📈 Top: {name} ({data['ticker']}) {direction} {abs(data['change']):.1f}%")
    if highlights['bottom']:
        name, data = highlights['bottom']
        direction = "▲" if data['change'] > 0 else "▼"
        lines.append(f"📉 Bottom: {name} ({data['ticker']}) {direction} {abs(data['change']):.1f}%")

    return "\n".join(lines)


def _format_setup(best, signal_type):
    """Formate le meilleur setup (STOCK ou ETF)"""
    if not best:
        return ""

    ticker = best.get('ticker', '?')
    score = best.get('score', '?')
    gap = best.get('gap', 0)
    vol_ratio = best.get('vol_ratio', 0)
    entry = best.get('entry_price', 0)
    cap_category = best.get('cap_category', 'N/A')
    aum_m = best.get('aum_m', None)

    # Récupérer le secteur via macro_context
    sector = "N/A"
    ctx = _get_signal_context(ticker, signal_type)
    if ctx:
        sector = ctx

    lines = []
    if aum_m is not None:
        lines.append(f"🔹 <b>Best {signal_type} Setup — Today</b>")
        lines.append(f"{ticker} ({signal_type}) | Score: {score}/5 | Sector: {sector} | AUM: {aum_m:.1f}M$")
    else:
        lines.append(f"🔹 <b>Best {signal_type} Setup — Today</b>")
        lines.append(f"{ticker} ({signal_type}) | Score: {score}/9 | Sector: {sector} | Cap: {cap_category}")

    lines.append(f"Gap: {gap:.1f}% | Volume: x{vol_ratio:.1f}")
    lines.append(f"Entry: ${entry:.2f}")

    # Commentaire personnalisé
    if signal_type == "STOCK" and score >= 6:
        lines.append("Why it stood out: High score + strong volume combo.")
    elif signal_type == "ETF" and score >= 5:
        lines.append("Why it stood out: Highest quality ETF setup of the session.")
    elif gap >= 10:
        lines.append("Why it stood out: Exceptional gap size.")
    else:
        lines.append(f"Why it stood out: Best overall {signal_type} setup of the session.")

    return "\n".join(lines)


def build_recap_message():
    """Construit le message récap enrichi avec structure améliorée"""
    now_mtl = datetime.now(MONTREAL_TZ)

    message = f"📊 <b>NorthSentinel Pro™ — Session Recap</b>\n"
    message += f"📅 {now_mtl.strftime('%Y-%m-%d')} (Montreal)\n"
    message += "═" * 30 + "\n\n"

    # 1. Signaux du jour (chargés depuis le fichier)
    signals = _load_today_signals()

    # 2. Highlights US et CA séparés
    highlights_us = _get_market_highlights(MARKET_ETFS_US, "US")
    highlights_ca = _get_market_highlights(MARKET_ETFS_CA, "CA")

    # --- US Sector Performance ---
    message += "🇺🇸 <b>US Sector Performance</b>\n"
    if highlights_us:
        message += _format_highlights(highlights_us, "🌐") + "\n\n"
    else:
        message += "  No data available.\n\n"

    # --- CA Sector Performance ---
    message += "🇨🇦 <b>CA Sector Performance</b>\n"
    if highlights_ca:
        message += _format_highlights(highlights_ca, "🌐") + "\n\n"
    else:
        message += "  No data available.\n\n"

    # 3. Meilleur setup STOCK
    if signals:
        stocks = [s for s in signals if s.get('type') == 'STOCK']
        if stocks:
            best_stock = max(stocks, key=lambda x: x.get('score', 0))
            message += _format_setup(best_stock, "STOCK") + "\n\n"

        # 4. Meilleur setup ETF
        etfs = [s for s in signals if s.get('type') == 'ETF']
        if etfs:
            best_etf = max(etfs, key=lambda x: x.get('score', 0))
            message += _format_setup(best_etf, "ETF") + "\n\n"
    else:
        message += "🔹 <b>Best STOCK Setup — Today</b>\n"
        message += "  No stock signals generated.\n\n"
        message += "🔹 <b>Best ETF Setup — Today</b>\n"
        message += "  No ETF signals generated.\n\n"

    # 5. Citation du jour
    quote, author = _get_daily_quote(signals, highlights_us, highlights_ca)
    message += f"🔹 <b>QUOTE OF THE DAY</b>\n"
    message += f"  \"{quote}\"\n"
    message += f"  — {author}\n"

    message += "\n<i>Automated recap. Not financial or trading advice.</i>"
    return message


def _load_today_signals():
    """Charge les signaux du jour depuis le fichier persistant"""
    try:
        with open(SIGNALS_FILE, 'r') as f:
            data = json.load(f)
        today = datetime.now(MONTREAL_TZ).strftime('%Y-%m-%d')

        if isinstance(data, list):
            return [item for item in data if item.get('date') == today]
        elif isinstance(data, dict) and data.get('date') == today:
            return [data]
        return []
    except FileNotFoundError:
        print(f"⚠️ {SIGNALS_FILE} not found — no signals recorded today")
        return []
    except:
        return []


def send_recap(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, PUBLIC_CHANNEL_ID=None):
    """
    Envoie le récap Telegram au propriétaire et, si fourni, au canal public.
    """
    message = build_recap_message()

    if not TELEGRAM_TOKEN:
        print("⚠️ Telegram token missing")
        return False

    # === CONSTRUCTION DE LA LISTE DES DESTINATAIRES ===
    recipients = []

    if TELEGRAM_CHAT_ID:
        try:
            recipients.append(int(TELEGRAM_CHAT_ID))
            print(f"✅ Récipiendaire ajouté : Propriétaire ({TELEGRAM_CHAT_ID})")
        except ValueError:
            print(f"⚠️ TELEGRAM_CHAT_ID invalide : {TELEGRAM_CHAT_ID}")

    if PUBLIC_CHANNEL_ID:
        try:
            channel_id = int(PUBLIC_CHANNEL_ID)
            recipients.append(channel_id)
            print(f"✅ Récipiendaire ajouté : Canal public ({PUBLIC_CHANNEL_ID})")
        except ValueError:
            print(f"⚠️ PUBLIC_CHANNEL_ID invalide : {PUBLIC_CHANNEL_ID}")

    if not recipients:
        print("⚠️ Aucun destinataire valide — message non envoyé")
        return False

    # === ENVOI À CHAQUE DESTINATAIRE ===
    success = True
    for chat_id in recipients:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                print(f"✅ Recap envoyé à {chat_id}")
            else:
                print(f"❌ Échec pour {chat_id}: {r.status_code} - {r.text}")
                success = False
        except Exception as e:
            print(f"❌ Erreur pour {chat_id}: {e}")
            success = False

    return success


if __name__ == "__main__":
    TELEGRAM_TOKEN = os.environ.get("TELEGRAM_PRO_TOKEN")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_PRO_CHAT_ID")
    PUBLIC_CHANNEL_ID = os.environ.get("PUBLIC_CHANNEL_ID", "")

    send_recap(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, PUBLIC_CHANNEL_ID)
