# ============================================================
# NORTHSENTINEL CA ONLY — SCANNER INTRADAY CONTINU (BOUCLE)
# SHORTS + LONGS — 3 SOURCES DE NEWS
# ============================================================
import requests
import yfinance as yf
import time
import random
import os
import sys
import re
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import pytz
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==================== CONFIGURATION INTÉGRÉE ====================
CONFIG = {
    "market": "CA",
    "capital": 1_000_000,
    "risk_per_trade": 0.02,
    "max_capital_per_position": 0.10,
    "max_spread_pct": 5.0,
    "score_min_stocks": 5,
    "score_min_etfs": 4,
    "price_min_stocks": 2.00,
    "price_max_stocks": 300.00,
    "price_max_etfs": 9999.00,
    "tickers": {
        "stocks": [
            "MFC.TO", "GWO.TO", "POW.TO", "SU.TO", "CNQ.TO",
            "WCP.TO", "CCO.TO", "DOL.TO", "ABX.TO", "K.TO",
            "LUN.TO", "FM.TO", "T.TO", "BCE.TO", "RCI-B.TO",
            "BB.TO", "LSPD.TO", "AC.TO", "CAE.TO", "SNC.TO",
            "ATZ.TO", "GRGD.TO", "SPCX.TO", "CSU.TO", "ATD.TO",
            "MRU.TO", "L.TO", "EMP.A.TO", "CP.TO", "CNR.TO",
            "TFII.TO", "MDA.TO", "BBD-B.TO", "CGO.TO", "QBR-B.TO",
            "IFC.TO", "SLF.TO", "RBA.TO", "AND.TO", "WELL.TO",
            "GIB-A.TO", "OTEX.TO", "DSG.TO", "CLS.TO", "KTN.TO",
            "AEM.TO", "WPM.TO", "EQX.TO", "LUG.TO", "FSV.TO",
            "BEP-UN.TO", "BAM.TO", "BN.TO", "NTR.TO"
        ],
        "etfs": [
            "XFN.TO", "ZEB.TO", "XEG.TO", "ZEO.TO", "XGD.TO",
            "XMA.TO", "XIT.TO", "XST.TO", "XRE.TO", "XUT.TO",
            "ZSP.TO", "XIC.TO", "HCLN.TO", "HHIS.TO", "HXS.TO",
            "HXQ.TO", "VFV.TO", "XQQ.TO", "HHL.TO", "TXF.TO",
            "HUTL.TO", "ZDI.TO", "VI.TO", "VRE.TO", "FIE.TO",
            "ZDC.TO", "ZWA.TO"
        ]
    }
}

# ==================== PARAMÈTRES GLOBAUX ====================
MONTREAL_TZ = pytz.timezone('America/Toronto')
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_CA_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CA_CHAT_ID")

# Détection du mode manuel (GitHub Actions OU terminal interactif)
GITHUB_EVENT = os.environ.get("GITHUB_EVENT_NAME", "")
IS_MANUAL_RUN = (GITHUB_EVENT == "workflow_dispatch") or sys.stdin.isatty()

CAPITAL = CONFIG['capital']
RISK_PER_TRADE = CONFIG['risk_per_trade']
MAX_CAPITAL_PER_POSITION = CONFIG['max_capital_per_position']
MAX_SPREAD_PCT = CONFIG['max_spread_pct']
SCORE_MIN_STOCKS = CONFIG['score_min_stocks']
SCORE_MIN_ETFS = CONFIG['score_min_etfs']
PRICE_MIN_STOCKS = CONFIG['price_min_stocks']
PRICE_MAX_STOCKS = CONFIG['price_max_stocks']
PRICE_MAX_ETFS = CONFIG['price_max_etfs']
STOCK_TICKERS = CONFIG['tickers']['stocks']
ETF_TICKERS = CONFIG['tickers']['etfs']

# ==================== SOURCES RSS NEWS ====================
RSS_FEEDS = [
    "https://www.cbc.ca/webfeed/rss/rss-business",
    "https://business.financialpost.com/feed/"
]

# ==================== SESSION HTTP ====================
def create_session():
    session = requests.Session()
    retry = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    return session

HTTP_SESSION = create_session()

# ==================== FONCTIONS TELEGRAM ====================
def send_telegram(message):
    """Envoie un message Telegram si les tokens sont configurés."""
    if not TELEGRAM_TOKEN:
        print("⚠️ Token Telegram manquant")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("✅ Telegram envoyé")
            return True
        else:
            print(f"❌ Erreur {r.status_code}: {r.text}")
            return False
    except Exception as e:
        print(f"❌ Exception Telegram: {e}")
        return False

# ==================== JOURS FÉRIÉS CANADA ====================
def _adjust_weekend(d):
    if d.weekday() == 5:
        return d - timedelta(days=1)
    elif d.weekday() == 6:
        return d + timedelta(days=1)
    return d

def _build_ca_holidays(year):
    from datetime import date
    ca = set()
    ca.add(date(year, 1, 1))
    ca.add(date(year, 7, 1))
    ca.add(date(year, 12, 25))
    ca.add(date(year, 12, 26))
    # Family Day
    fam = date(year, 2, 1)
    while fam.weekday() != 0:
        fam = date(year, 2, fam.day + 1)
    ca.add(date(year, 2, fam.day + 14))
    # Good Friday
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    easter = date(year, month, day)
    ca.add(easter - timedelta(days=2))
    # Victoria Day
    vic = date(year, 5, 24)
    while vic.weekday() != 0:
        vic = date(year, 5, vic.day - 1)
    ca.add(vic)
    # Civic Holiday
    civ = date(year, 8, 1)
    while civ.weekday() != 0:
        civ = date(year, 8, civ.day + 1)
    ca.add(civ)
    # Labour Day
    lab = date(year, 9, 1)
    while lab.weekday() != 0:
        lab = date(year, 9, lab.day + 1)
    ca.add(lab)
    # Canadian Thanksgiving
    thanks = date(year, 10, 1)
    while thanks.weekday() != 0:
        thanks = date(year, 10, thanks.day + 1)
    ca.add(date(year, 10, thanks.day + 7))
    return ca

def is_ca_market_closed(check_date):
    """Vérifie si le marché canadien est fermé (week-end ou jour férié)."""
    if isinstance(check_date, datetime):
        check_date = check_date.date()
    if check_date.weekday() >= 5:
        return True
    holidays = _build_ca_holidays(check_date.year)
    adjusted = {_adjust_weekend(d) for d in holidays}
    return check_date in adjusted

# ==================== NEWS SCANNER (3 SOURCES) ====================
def get_news_for_ticker(ticker):
    all_news = []
    ticker_clean = ticker.replace('.TO', '').upper()
    # 1. Google News
    try:
        params = {"q": f"{ticker}+stock", "hl": "en-CA", "gl": "CA"}
        r = requests.get("https://news.google.com/rss/search", params=params, timeout=5)
        soup = BeautifulSoup(r.content, 'xml')
        for item in soup.find_all('item')[:5]:
            title = item.find('title').text if item.find('title') else ''
            pub_date_str = item.find('pubDate').text if item.find('pubDate') else ''
            try:
                pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %Z').replace(tzinfo=timezone.utc)
                hours_ago = (datetime.now(timezone.utc) - pub_date).total_seconds() / 3600
                if hours_ago < 6:
                    all_news.append({'title': title, 'hours_ago': hours_ago})
            except:
                pass
    except:
        pass
    # 2. CBC + Financial Post
    for feed_url in RSS_FEEDS:
        try:
            r = requests.get(feed_url, timeout=5)
            soup = BeautifulSoup(r.content, 'xml')
            for item in soup.find_all('item')[:15]:
                title = item.find('title').text if item.find('title') else ''
                description = item.find('description').text if item.find('description') else ''
                if ticker_clean in title.upper() or ticker_clean in description.upper():
                    pub_date_str = item.find('pubDate').text if item.find('pubDate') else ''
                    try:
                        pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %Z').replace(tzinfo=timezone.utc)
                        hours_ago = (datetime.now(timezone.utc) - pub_date).total_seconds() / 3600
                        if hours_ago < 6:
                            all_news.append({'title': title, 'hours_ago': hours_ago})
                    except:
                        pass
        except:
            pass
    seen = set()
    unique_news = []
    for n in all_news:
        if n['title'] not in seen:
            seen.add(n['title'])
            unique_news.append(n)
    unique_news.sort(key=lambda x: x['hours_ago'])
    return unique_news[:5]

def analyze_sentiment(title):
    text = title.lower()
    bullish_strong = [
        'fda approval', 'partnership', 'deal', 'acquisition', 'buyout', 'merger',
        'earnings beat', 'upgraded', 'breakthrough', 'contract awarded',
        'drill results', 'high-grade', 'discovery', 'resource estimate',
        'feasibility study', 'permit granted', 'commercial production',
        'joint venture', 'bought deal', 'flow-through', 'positive', 'upgrade',
        'record revenue', 'guidance raised'
    ]
    bullish = [
        'growth', 'revenue', 'profit', 'gain', 'surge', 'rally', 'momentum',
        'expansion', 'launch', 'agreement', 'assay', 'buy rating', 'outperform',
        'overweight', 'new contract', 'granted', 'approved', 'commenced',
        'completed', 'successful'
    ]
    bearish_strong = [
        'dilution', 'offering', 'bankruptcy', 'lawsuit', 'sec investigation',
        'delisting', 'fda rejection', 'clinical failure', 'downgraded',
        'private placement', 'unit offering', 'permit denied', 'cease trade',
        'suspension', 'default', 'going concern', 'termination',
        'insider selling', 'ceo departure', 'investigation', 'guidance lowered',
        'missed estimates'
    ]
    bearish = [
        'loss', 'decline', 'drop', 'fall', 'warning', 'concern', 'risk',
        'delay', 'delayed', 'suspended', 'halted', 'reduced', 'lowered',
        'restructuring', 'layoff', 'impairment', 'write-down', 'debt'
    ]
    score = 0
    if any(w in text for w in bullish_strong):
        score += 2
    elif any(w in text for w in bullish):
        score += 1
    if any(w in text for w in bearish_strong):
        score -= 2
    elif any(w in text for w in bearish):
        score -= 1
    return score

def run_news_scan():
    print("📰 Scan News 9h25 (3 sources: Google, CBC, Financial Post)...")
    alerts = []
    all_tickers = STOCK_TICKERS + ETF_TICKERS
    for ticker in all_tickers:
        news = get_news_for_ticker(ticker)
        if not news:
            continue
        for n in news:
            sentiment = analyze_sentiment(n['title'])
            if abs(sentiment) >= 1:
                alerts.append({
                    'ticker': ticker,
                    'title': n['title'],
                    'sentiment': sentiment,
                    'hours_ago': round(n['hours_ago'], 1)
                })
                break
    if not alerts:
        print("ℹ️ Aucune news significative trouvée.")
        return
    msg = "📰 <b>NorthSentinel CA Only</b>™️\n"
    msg += "<i>Morning News Alert (9:25 AM ET)</i>\n"
    msg += "═" * 35 + "\n\n"
    for a in alerts:
        emoji = "📈 BULLISH" if a['sentiment'] > 0 else "📉 BEARISH" if a['sentiment'] < 0 else "➡️ NEUTRAL"
        msg += f"🔹 <b>{a['ticker']}</b>\n"
        msg += f"   {a['title']}\n"
        msg += f"   {emoji} | {a['hours_ago']}h ago\n\n"
    msg += "<i>Informational automated signal. Not financial or trading advice.</i>"
    send_telegram(msg)

# ==================== FONCTIONS D'ANALYSE (STOCKS & ETF) ====================
def get_market_cap_category(ticker):
    try:
        info = yf.Ticker(ticker).info
        mc = info.get('marketCap', 0)
        if mc == 0:
            return "N/A"
        elif mc < 300_000_000:
            return "Micro Cap"
        elif mc < 2_000_000_000:
            return "Small Cap"
        elif mc < 10_000_000_000:
            return "Mid Cap"
        elif mc < 200_000_000_000:
            return "Large Cap"
        else:
            return "Mega Cap"
    except:
        return "N/A"

def get_exchange(info):
    ex = info.get('exchange', '')
    map_ex = {'TOR': 'TMX', 'TSX': 'TMX', 'TSXV': 'TSXV', 'CNQ': 'CSE'}
    return map_ex.get(ex, ex if ex else 'TMX')

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if len(rsi) > 0 else None

def get_confidence_score(score, vol_ratio, gap, cap_category):
    conf = 5.0
    conf += min(score * 0.4, 2.0)
    conf += min(vol_ratio * 0.3, 1.5)
    if abs(gap) > 10:
        conf += 0.5
    if cap_category in ['Large Cap', 'Mega Cap']:
        conf += 0.5
    return min(round(conf, 1), 10.0)

# ==================== ANALYSE STOCKS (LONG + SHORT) ====================
def analyze_stock(ticker):
    try:
        stock = yf.Ticker(ticker, session=HTTP_SESSION)
        info = stock.info
        time.sleep(random.uniform(0.2, 0.4))
        price = info.get('regularMarketPrice') or info.get('currentPrice')
        if not price or price < PRICE_MIN_STOCKS or price > PRICE_MAX_STOCKS:
            return None
        bid = info.get('bid')
        ask = info.get('ask')
        spread_pct = 0.0
        if bid and ask and bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            spread_pct = ((ask - bid) / mid) * 100
            if spread_pct > MAX_SPREAD_PCT:
                return None
            if spread_pct > 0.3:
                price = ask
        prev_close = info.get('previousClose')
        if not prev_close or prev_close == 0:
            return None
        gap = ((price - prev_close) / prev_close) * 100
        score = 0
        # Seuils assouplis pour les stocks
        if 3 <= gap <= 40:
            direction = "LONG"
            score += 1
        elif -40 <= gap <= -3:
            direction = "SHORT"
            score += 1
        else:
            return None
        volume = info.get('volume', 0)
        avg_vol = info.get('averageVolume', volume)
        vol_ratio = volume / avg_vol if avg_vol > 0 else 1
        if vol_ratio > 1.2:   # abaissé de 1.5 à 1.2
            score += 1
        float_shares = info.get('floatShares')
        if float_shares is not None and float_shares < 100_000_000:  # assoupli à 100M
            score += 1
        elif float_shares is None:
            score += 1
        beta = info.get('beta')
        if beta is not None and beta > 0.8:  # abaissé de 1.0 à 0.8
            score += 1
        elif beta is None:
            score += 1
        short_ratio = info.get('shortRatio')
        if short_ratio is not None and short_ratio > 1.5:  # abaissé de 2.0 à 1.5
            score += 1
        elif short_ratio is None:
            score += 1
        sma50 = info.get('fiftyDayAverage')
        if sma50:
            if direction == "LONG" and price > sma50:
                score += 1
            elif direction == "SHORT" and price < sma50:
                score += 1
        news = get_news_for_ticker(ticker)
        if news:
            for n in news[:3]:
                sent = analyze_sentiment(n['title'])
                if direction == "LONG" and sent >= 1:
                    score += 1
                    break
                elif direction == "SHORT" and sent <= -1:
                    score += 1
                    break
                elif direction == "LONG" and sent <= -2:
                    score -= 1
                    break
                elif direction == "SHORT" and sent >= 2:
                    score -= 1
                    break
        if score < SCORE_MIN_STOCKS:
            return None
        cap_category = get_market_cap_category(ticker)
        exchange = get_exchange(info)
        confidence = get_confidence_score(score, vol_ratio, gap, cap_category)
        if abs(gap) >= 20:
            tp_pct = 1.02 + (score - 4) * 0.006
        elif abs(gap) >= 10:
            tp_pct = 1.015 + (score - 4) * 0.004
        else:
            tp_pct = 1.005 + (score - 4) * 0.002
        if score >= 6:
            sl_pct = 0.96
        else:
            sl_pct = 0.95
        if score >= 8:
            trail = 2.5
        elif score >= 6:
            trail = 3.0
        else:
            trail = 4.0
        return {
            'ticker': ticker,
            'exchange': exchange,
            'price': price,
            'gap': gap,
            'score': score,
            'vol_ratio': vol_ratio,
            'cap_category': cap_category,
            'confidence': confidence,
            'spread_pct': spread_pct,
            'direction': direction,
            'tp_mult': round(tp_pct, 3),
            'sl_mult': round(sl_pct, 3),
            'trail_pct': round(trail, 2)
        }
    except Exception:
        return None

# ==================== ANALYSE ETF (LONG + SHORT) ====================
def analyze_etf(ticker):
    try:
        stock = yf.Ticker(ticker, session=HTTP_SESSION)
        info = stock.info
        hist = stock.history(period="1mo")
        time.sleep(random.uniform(0.2, 0.4))
        if hist.empty or len(hist) < 2:
            return None
        closes = hist['Close']
        volumes = hist['Volume']
        price = closes.iloc[-1]
        bid = info.get('bid')
        ask = info.get('ask')
        spread_pct = 0.0
        if bid and ask and bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            spread_pct = ((ask - bid) / mid) * 100
            if spread_pct > MAX_SPREAD_PCT:
                return None
            if spread_pct > 0.3:
                price = ask
        prev_close = closes.iloc[-2] if len(closes) > 1 else None
        if not prev_close:
            return None
        gap = ((price - prev_close) / prev_close) * 100
        volume = info.get('volume', 0)
        avg_vol = volumes.mean() if len(volumes) > 0 else volume
        vol_ratio = volume / avg_vol if avg_vol > 0 else 1
        aum = info.get('totalAssets', 0) or info.get('assetsUnderManagement', 0)
        score = 0
        if 0.5 <= gap <= 8:
            direction = "LONG"
            score += 1
        elif -8 <= gap <= -0.5:
            direction = "SHORT"
            score += 1
        else:
            return None
        if vol_ratio > 0.9:
            score += 1
        if aum > 50_000_000 or aum == 0:
            score += 1
        rsi = None
        if len(closes) > 14:
            rsi = calculate_rsi(closes)
            if rsi and 35 <= rsi <= 80:
                score += 1
        if len(closes) >= 20:
            sma20 = closes.rolling(20).mean().iloc[-1]
            if sma20:
                if direction == "LONG" and price > 0.7 * sma20:
                    score += 1
                elif direction == "SHORT" and price < 1.3 * sma20:
                    score += 1
        if score < SCORE_MIN_ETFS:
            return None
        exchange = get_exchange(info)
        confidence = get_confidence_score(score, vol_ratio, gap, "Large Cap")
        if abs(gap) >= 6:
            tp_pct = 1.015 + (score - 3) * 0.005
        elif abs(gap) >= 3:
            tp_pct = 1.01 + (score - 3) * 0.005
        else:
            tp_pct = 1.005 + (score - 3) * 0.005
        sl_pct = 0.96
        trail_pct = 3.0
        return {
            'ticker': ticker,
            'exchange': exchange,
            'price': price,
            'gap': gap,
            'score': score,
            'vol_ratio': vol_ratio,
            'aum_m': round(aum / 1_000_000, 1) if aum else 0,
            'confidence': confidence,
            'spread_pct': spread_pct,
            'direction': direction,
            'tp_mult': round(tp_pct, 3),
            'sl_mult': round(sl_pct, 3),
            'trail_pct': round(trail_pct, 2)
        }
    except Exception:
        return None

# ==================== CALCUL DES QUANTITÉS ====================
def calculate_quantity(entry, stop, capital, risk_pct, max_cap_pct):
    risk_amount = capital * risk_pct
    max_exposure = capital * max_cap_pct
    stop_dist = abs(entry - stop)
    if stop_dist <= 0:
        return 0
    qty_risk = int(risk_amount / stop_dist)
    qty_cap = int(max_exposure / entry)
    return max(0, min(qty_risk, qty_cap))

# ==================== FORMATAGE DES MESSAGES ====================
def format_price(p):
    return f"{p:.2f}"

def get_verdict(confidence):
    if confidence >= 8.5:
        return "Strong", "🟢"
    elif confidence >= 7.5:
        return "Favorable", "🔵"
    elif confidence >= 5.5:
        return "Mixed", "🟡"
    elif confidence >= 3.5:
        return "Weak", "🟠"
    else:
        return "Poor", "🔴"

def build_setup_message(data, is_etf=False, bias="⚪ Neutral (CA)"):
    max_score = 7 if not is_etf else 5
    entry = data['price']
    direction = data['direction']
    if direction == "LONG":
        tp = round(entry * data['tp_mult'], 2)
        sl = round(entry * data['sl_mult'], 2)
        trail_price = round(entry * (1 - data['trail_pct'] / 100), 2)
        tp_label = "TAKE-PROFIT"
        sl_label = "STOP LOSS"
    else:
        tp = round(entry * (2 - data['tp_mult']), 2)
        sl = round(entry * (2 - data['sl_mult']), 2)
        trail_price = round(entry * (1 + data['trail_pct'] / 100), 2)
        tp_label = "TAKE-PROFIT"
        sl_label = "STOP LOSS"
    qty = calculate_quantity(entry, sl, CAPITAL, RISK_PER_TRADE, MAX_CAPITAL_PER_POSITION)
    spread_display = ""
    if data['spread_pct'] > 0:
        spread_usd = round((data['spread_pct'] / 100) * entry, 2)
        spread_display = f" | Spread: {data['spread_pct']:.2f}% (${spread_usd:.2f})"
    verdict_text, verdict_emoji = get_verdict(data['confidence'])
    direction_emoji = "📈 LONG" if direction == "LONG" else "📉 SHORT"
    gap_display = f"+{data['gap']:.2f}%" if data['gap'] >= 0 else f"{data['gap']:.2f}%"
    msg = f"🔹 <b>{data['ticker']}</b> ({data['exchange']}){spread_display}\n"
    msg += f"   Direction: <b>{direction_emoji}</b>\n"
    msg += f"   Quality: <b>{data['score']}/{max_score}</b> | Confidence: <b>{data['confidence']}/10</b>\n"
    msg += f"   GAP: {gap_display} | VOL: x{data['vol_ratio']:.2f}\n"
    if not is_etf and 'cap_category' in data:
        msg += f"   Cap: {data['cap_category']}\n"
    if is_etf:
        msg += f"   AUM: {data['aum_m']}M$\n"
    msg += f"   Bias: {bias}\n"   # déplacé ici, juste avant le verdict
    msg += f"   ⚖️ VERDICT: {verdict_emoji} {verdict_text}\n"
    msg += f"   🎯 ENTRY: ${format_price(entry)}\n"
    msg += f"   📦 QTY: {qty} {'shares' if not is_etf else 'units'}\n"
    msg += f"   📈 {tp_label}: ${format_price(tp)} ({'+' if direction == 'LONG' else ''}{round((tp/entry - 1) * 100 if direction == 'LONG' else (1 - tp/entry) * 100, 1)}%)\n"
    msg += f"   🛑 {sl_label}: ${format_price(sl)} ({'-' if direction == 'LONG' else '+'}{round((1 - sl/entry) * 100 if direction == 'LONG' else (sl/entry - 1) * 100, 1)}%)\n"
    msg += f"   🔄 TRAILING: ${format_price(trail_price)} → {data['trail_pct']}%\n"
    return msg

# ==================== FONCTION D'ATTENTE ====================
def wait_until_target(target_hour, target_minute):
    """Attend jusqu'à l'heure:minute cible (pour les scans multiples de 15 minutes)."""
    now = datetime.now(MONTREAL_TZ)
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    # Si la cible est déjà passée, on ajoute 15 minutes
    if target <= now:
        target += timedelta(minutes=15)
    diff = (target - now).total_seconds()
    if diff > 0:
        print(f"⏳ Attente jusqu'à {target.strftime('%H:%M')}... ({diff/60:.1f} min)")
        time.sleep(diff)

# ==================== MAIN CONTINU ====================
def main():
    now = datetime.now(MONTREAL_TZ)
    heure = now.hour
    minute = now.minute

    # Vérifier si le marché est fermé (week-end ou férié)
    if is_ca_market_closed(now):
        print("🏖️ Marché CA fermé – Arrêt.")
        if IS_MANUAL_RUN:
            msg = (
                "🤖 <b>NorthSentinel CA Only</b>™\n"
                "<i>Canadian intraday trading signals. Long & Short. Manual execution.</i>\n"
                f"<i>📅 {now.strftime('%Y-%m-%d %H:%M')} (Montreal) | 💰 Capital: ${CAPITAL:,.0f}</i>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "⏰ Manual run triggered on a closed market day (weekend or holiday).\n"
                "The scanner only runs on Canadian market days during active windows.\n"
                "⏳ Scheduled active scan windows:\n"
                "   • 9:25 AM – 11:30 AM ET\n"
                "   • 1:00 PM – 3:30 PM ET\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "<i>Informational automated signal. Not financial or trading advice.</i>"
            )
            send_telegram(msg)
        return

    # Déterminer la session en fonction de l'heure de lancement
    if 9 <= heure <= 11 and (heure < 11 or minute <= 30):
        session = "morning"
        start_hour, start_min = 9, 25
        end_hour, end_min = 11, 30
        print("☀️ Session MATIN détectée.")
    elif 13 <= heure <= 15 and (heure < 15 or minute <= 30):
        session = "afternoon"
        start_hour, start_min = 13, 0
        end_hour, end_min = 15, 30
        print("🌙 Session APRÈS-MIDI détectée.")
    else:
        print("⏰ Lancement hors des plages horaires (9h-11h30 ou 13h-15h30) – Arrêt.")
        if IS_MANUAL_RUN:
            msg = (
                "🤖 <b>NorthSentinel CA Only</b>™\n"
                "<i>Canadian intraday trading signals. Long & Short. Manual execution.</i>\n"
                f"<i>📅 {now.strftime('%Y-%m-%d %H:%M')} (Montreal) | 💰 Capital: ${CAPITAL:,.0f}</i>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "⏰ Manual run triggered outside trading hours.\n"
                "⏳ Scheduled active scan windows:\n"
                "   • 9:25 AM – 11:30 AM ET\n"
                "   • 1:00 PM – 3:30 PM ET\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "<i>Informational automated signal. Not financial or trading advice.</i>"
            )
            send_telegram(msg)
        return

    # Attendre le début de la session si nécessaire
    now = datetime.now(MONTREAL_TZ)
    if now.hour < start_hour or (now.hour == start_hour and now.minute < start_min):
        print(f"⏳ Attente du début de session à {start_hour:02d}:{start_min:02d}...")
        wait_until_target(start_hour, start_min)
        now = datetime.now(MONTREAL_TZ)

    # Boucle principale
    first_scan_done = False  # pour le scan news à 9h25 (une seule fois)
    while True:
        now = datetime.now(MONTREAL_TZ)
        # Vérifier si on a dépassé l'heure de fin
        if now.hour > end_hour or (now.hour == end_hour and now.minute > end_min):
            print(f"⏹️ Fin de session atteinte ({end_hour:02d}:{end_min:02d}) – Arrêt.")
            # Envoyer un message de fin de session
            session_label = "Morning" if session == "morning" else "Afternoon"
            msg = (
                f"🤖 <b>NorthSentinel CA Only</b>™\n"
                f"<i>{session_label} Session ended – {now.strftime('%H:%M')} (ET)</i>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🛑 Automatic shutdown completed.\n"
                "⏳ Next session will start at the scheduled time.\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "<i>Informational automated signal. Not financial or trading advice.</i>"
            )
            send_telegram(msg)
            break

        current_hour, current_min = now.hour, now.minute

        # Si session matin et 9h25, faire scan news (une seule fois) et envoyer immédiatement
        if session == "morning" and current_hour == 9 and current_min == 25 and not first_scan_done:
            run_news_scan()
            first_scan_done = True
            # On ne fait pas d'attente ici – on continue la boucle pour le prochain scan à 9h30
            continue

        # Sinon, scan des prix toutes les 15 minutes (multiples de 15)
        if current_min % 15 == 0:
            # Éviter de scanner à 9h25 (déjà traité) et à 9h30 (premier scan prix)
            if not (session == "morning" and current_hour == 9 and current_min == 25 and first_scan_done):
                print(f"\n📊 Scan de prix à {now.strftime('%H:%M')} (session {session})")
                # Scans
                stocks_results = []
                for ticker in STOCK_TICKERS:
                    print(f"  - {ticker}...", end=" ")
                    data = analyze_stock(ticker)
                    if data:
                        stocks_results.append(data)
                        print(f"✅ Score {data['score']}/7 | {data['direction']}")
                    else:
                        print("❌")
                etfs_results = []
                for ticker in ETF_TICKERS:
                    print(f"  - {ticker}...", end=" ")
                    data = analyze_etf(ticker)
                    if data:
                        etfs_results.append(data)
                        print(f"✅ Score {data['score']}/5 | {data['direction']}")
                    else:
                        print("❌")
                best_stock = max(stocks_results, key=lambda x: (x['score'], x['vol_ratio'])) if stocks_results else None
                best_etf = max(etfs_results, key=lambda x: (x['score'], x['vol_ratio'])) if etfs_results else None
                if best_stock or best_etf:
                    msg = "🤖 <b>NorthSentinel CA Only</b>™\n"
                    # L'en-tête ne contient plus le Bias
                    msg += f"<i>Scan {now.strftime('%H:%M')} (ET) | Scanned: {len(STOCK_TICKERS)} Stocks, {len(ETF_TICKERS)} ETFs</i>\n"
                    msg += f"<i>💰 Capital: ${CAPITAL:,.0f}</i>\n"
                    msg += "═" * 35 + "\n"
                    if best_stock:
                        msg += "\n🚀 <b>BEST STOCK SETUP</b>\n"
                        msg += build_setup_message(best_stock, is_etf=False, bias="⚪ Neutral (CA)")
                    else:
                        msg += "\n🚀 <b>BEST STOCK SETUP</b>\n❌ No valid stock setup for this scan.\n"
                    if best_etf:
                        msg += "\n🚀 <b>BEST ETF SETUP</b>\n"
                        msg += build_setup_message(best_etf, is_etf=True, bias="⚪ Neutral (CA)")
                    else:
                        msg += "\n🚀 <b>BEST ETF SETUP</b>\n❌ No valid ETF setup for this scan.\n"
                    msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    msg += "<i>Informational automated signal. Not financial or trading advice.</i>"
                    send_telegram(msg)
                else:
                    print("ℹ️ Aucun setup valide – Pas de message Telegram.")
        # Attendre la prochaine minute multiple de 15
        next_min = ((current_min // 15) + 1) * 15
        next_hour = current_hour
        if next_min == 60:
            next_min = 0
            next_hour += 1
        wait_until_target(next_hour, next_min)

if __name__ == "__main__":
    main()
