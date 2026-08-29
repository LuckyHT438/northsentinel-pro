# ============================================================
# NORTHSENTINEL CA ONLY — SCANNER INTRADAY 9h25-11h30 & 13h00-15h30
# SHORTS + LONGS — 3 SOURCES DE NEWS
# ============================================================
import requests
import yfinance as yf
import time
import random
import os
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
    "risk_per_trade": 0.02,           # 2% du capital par trade
    "max_capital_per_position": 0.10, # 10% maximum du capital alloué à une position
    "max_spread_pct": 5.0,
    "score_min_stocks": 5,            # sur 7
    "score_min_etfs": 4,              # sur 5
    "price_min_stocks": 2.00,
    "price_max_stocks": 300.00,
    "price_max_etfs": 9999.00,
    "tickers": {
        "stocks": [
            "MFC.TO", "GWO.TO", "POW.TO", "SU.TO", "CNQ.TO",
            "CVE.TO", "MEG.TO", "WCP.TO", "ABX.TO", "K.TO",
            "LUN.TO", "FM.TO", "T.TO", "BCE.TO", "RCI.B.TO",
            "BB.TO", "LSPD.TO", "AC.TO", "CAE.TO", "SNC.TO"
        ],
        "etfs": [
            "XFN.TO", "ZEB.TO", "XEG.TO", "ZEO.TO", "XGD.TO",
            "XMA.TO", "XIT.TO", "XST.TO", "XRE.TO", "XUT.TO",
            "ZSP.TO", "XIC.TO", "HCLN.TO"
        ]
    }
}

# ==================== PARAMÈTRES GLOBAUX ====================
MONTREAL_TZ = pytz.timezone('America/Toronto')
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_CA_ONLY_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CA_CHAT_ID")

# Détection du mode de déclenchement du workflow
GITHUB_EVENT = os.environ.get("GITHUB_EVENT_NAME", "")
IS_MANUAL_RUN = (GITHUB_EVENT == "workflow_dispatch")

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
# 3 sources : Google News + CBC Business + Financial Post
RSS_FEEDS = [
    "https://www.cbc.ca/webfeed/rss/rss-business",          # CBC News Business
    "https://business.financialpost.com/feed/"              # Financial Post
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
    # Vérification du week-end (samedi ou dimanche)
    if check_date.weekday() >= 5:
        return True
    holidays = _build_ca_holidays(check_date.year)
    adjusted = {_adjust_weekend(d) for d in holidays}
    return check_date in adjusted

# ==================== NEWS SCANNER (3 SOURCES) ====================
def get_news_for_ticker(ticker):
    """
    Récupère les news des 3 sources (Google News, CBC, Financial Post)
    pour un ticker donné. Retourne une liste de titres (max 5) des 6 dernières heures.
    """
    all_news = []
    ticker_clean = ticker.replace('.TO', '').upper()

    # 1. Google News RSS
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

    # 2. CBC Business + Financial Post (flux RSS généraux filtrés par ticker)
    for feed_url in RSS_FEEDS:
        try:
            r = requests.get(feed_url, timeout=5)
            soup = BeautifulSoup(r.content, 'xml')
            for item in soup.find_all('item')[:15]:
                title = item.find('title').text if item.find('title') else ''
                description = item.find('description').text if item.find('description') else ''
                # Vérifie si le ticker ou le nom de l'entreprise apparaît
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

    # Déduplication par titre
    seen = set()
    unique_news = []
    for n in all_news:
        if n['title'] not in seen:
            seen.add(n['title'])
            unique_news.append(n)

    # Tri par date (les plus récents d'abord)
    unique_news.sort(key=lambda x: x['hours_ago'])
    return unique_news[:5]

def analyze_sentiment(title):
    """
    Analyse le sentiment d'un titre de news.
    Retourne un score : +2 (bullish fort), +1 (bullish), -1 (bearish), -2 (bearish fort), 0 (neutre).
    """
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
    """Exécute le scan de news à 9h25 et envoie un récapitulatif Telegram."""
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

    # Construction du message en anglais
    msg = "📰 <b>NorthSentinel CA Only</b> – Morning News Alert (9:25 AM ET)\n"
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
    """Retourne la catégorie de capitalisation boursière."""
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
    """Retourne l'échange à partir des infos Yahoo Finance."""
    ex = info.get('exchange', '')
    map_ex = {'TOR': 'TMX', 'TSX': 'TMX', 'TSXV': 'TSXV', 'CNQ': 'CSE'}
    return map_ex.get(ex, ex if ex else 'TMX')

def calculate_rsi(prices, period=14):
    """Calcule le RSI sur une série de prix."""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if len(rsi) > 0 else None

def get_confidence_score(score, vol_ratio, gap, cap_category):
    """Calcule un score de confiance (sur 10) pour qualifier la qualité du setup."""
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
    """
    Analyse un titre pour détecter un setup LONG ou SHORT.
    Retourne un dictionnaire avec direction, score, TP/SL, etc. ou None si invalide.
    """
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
                price = ask  # On utilise le ask pour l'entry (achat)

        prev_close = info.get('previousClose')
        if not prev_close or prev_close == 0:
            return None
        gap = ((price - prev_close) / prev_close) * 100

        # ===== SCORING (7 critères) =====
        score = 0

        # 1. Gap (accepte positif pour LONG, négatif pour SHORT)
        if 5 <= gap <= 40:   # LONG
            direction = "LONG"
            score += 1
        elif -40 <= gap <= -5:  # SHORT
            direction = "SHORT"
            score += 1
        else:
            return None  # Gap insuffisant des deux côtés

        # 2. Volume relatif
        volume = info.get('volume', 0)
        avg_vol = info.get('averageVolume', volume)
        vol_ratio = volume / avg_vol if avg_vol > 0 else 1
        if vol_ratio > 1.5:
            score += 1

        # 3. Float
        float_shares = info.get('floatShares')
        if float_shares is not None and float_shares < 50_000_000:
            score += 1
        elif float_shares is None:
            score += 1

        # 4. Bêta
        beta = info.get('beta')
        if beta is not None and beta > 1.0:
            score += 1
        elif beta is None:
            score += 1

        # 5. Short Ratio
        short_ratio = info.get('shortRatio')
        if short_ratio is not None and short_ratio > 2:
            score += 1
        elif short_ratio is None:
            score += 1

        # 6. SMA50 (direction dépend du sens)
        sma50 = info.get('fiftyDayAverage')
        if sma50:
            if direction == "LONG" and price > sma50:
                score += 1
            elif direction == "SHORT" and price < sma50:
                score += 1

        # 7. News sentiment (bonus selon la direction)
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

        # ===== VALIDATION DU SCORE =====
        if score < SCORE_MIN_STOCKS:
            return None

        # ===== CALCUL DES TP/SL/TRAILING =====
        cap_category = get_market_cap_category(ticker)
        exchange = get_exchange(info)
        confidence = get_confidence_score(score, vol_ratio, gap, cap_category)

        # TP / SL / TRAIL (symétriques LONG/SHORT)
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
    """
    Analyse un ETF pour détecter un setup LONG ou SHORT.
    Similaire à analyze_stock mais avec des critères adaptés aux ETF.
    """
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

        # ===== SCORING (5 critères) =====
        score = 0

        # 1. Gap (positif ou négatif)
        if 0.5 <= gap <= 8:
            direction = "LONG"
            score += 1
        elif -8 <= gap <= -0.5:
            direction = "SHORT"
            score += 1
        else:
            return None

        # 2. Volume ratio
        if vol_ratio > 0.9:
            score += 1

        # 3. AUM
        if aum > 50_000_000 or aum == 0:
            score += 1

        # 4. RSI (entre 35 et 80, quelle que soit la direction)
        rsi = None
        if len(closes) > 14:
            rsi = calculate_rsi(closes)
            if rsi and 35 <= rsi <= 80:
                score += 1

        # 5. SMA20 (direction dépend du sens)
        if len(closes) >= 20:
            sma20 = closes.rolling(20).mean().iloc[-1]
            if sma20:
                if direction == "LONG" and price > 0.7 * sma20:
                    score += 1
                elif direction == "SHORT" and price < 1.3 * sma20:
                    # Pour le short, on accepte si le prix n'est pas trop au-dessus de la SMA20
                    # Critère simplifié : on vérifie que le prix n'est pas en nette tendance haussière
                    score += 1

        # ===== VALIDATION =====
        if score < SCORE_MIN_ETFS:
            return None

        exchange = get_exchange(info)
        confidence = get_confidence_score(score, vol_ratio, gap, "Large Cap")

        # TP/SL/Trail pour ETF
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
    """
    Calcule le nombre d'unités à acheter/vendre selon le risque.
    - risk_pct : pourcentage du capital risqué par trade (ex: 0.02 = 2%)
    - max_cap_pct : pourcentage maximum du capital alloué à une position (ex: 0.10 = 10%)
    """
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
    """Retourne le libellé et l'émoji du verdict selon la confiance."""
    if confidence >= 8.5:
        return "Strong", "🟢"
    elif confidence >= 7.5:
        return "Favorable", "🔵"   # Bleu pour Favorable
    elif confidence >= 5.5:
        return "Mixed", "🟡"
    elif confidence >= 3.5:
        return "Weak", "🟠"
    else:
        return "Poor", "🔴"

def build_setup_message(data, is_etf=False):
    """
    Construit le message Telegram pour un setup (LONG ou SHORT).
    Retourne une chaîne formatée en HTML pour Telegram.
    """
    max_score = 7 if not is_etf else 5
    entry = data['price']
    direction = data['direction']

    # TP et SL selon la direction
    if direction == "LONG":
        tp = round(entry * data['tp_mult'], 2)
        sl = round(entry * data['sl_mult'], 2)
        trail_price = round(entry * (1 - data['trail_pct'] / 100), 2)
        tp_label = "TAKE-PROFIT"
        sl_label = "STOP LOSS"
    else:  # SHORT
        tp = round(entry * (2 - data['tp_mult']), 2)  # TP en dessous du prix
        sl = round(entry * (2 - data['sl_mult']), 2)  # SL au-dessus du prix
        trail_price = round(entry * (1 + data['trail_pct'] / 100), 2)
        tp_label = "TAKE-PROFIT"
        sl_label = "STOP LOSS"

    qty = calculate_quantity(entry, sl, CAPITAL, RISK_PER_TRADE, MAX_CAPITAL_PER_POSITION)

    # Spread
    spread_display = ""
    if data['spread_pct'] > 0:
        spread_usd = round((data['spread_pct'] / 100) * entry, 2)
        spread_display = f" | Spread: {data['spread_pct']:.2f}% (${spread_usd:.2f})"

    # Verdict
    verdict_text, verdict_emoji = get_verdict(data['confidence'])

    # Construction du message
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

    msg += f"   ⚖️ VERDICT: {verdict_emoji} {verdict_text}\n"
    msg += f"   🎯 ENTRY: ${format_price(entry)}\n"
    msg += f"   📦 QTY: {qty} {'shares' if not is_etf else 'units'}\n"
    msg += f"   📈 {tp_label}: ${format_price(tp)} ({'+' if direction == 'LONG' else ''}{round((tp/entry - 1) * 100 if direction == 'LONG' else (1 - tp/entry) * 100, 1)}%)\n"
    msg += f"   🛑 {sl_label}: ${format_price(sl)} ({'-' if direction == 'LONG' else '+'}{round((1 - sl/entry) * 100 if direction == 'LONG' else (sl/entry - 1) * 100, 1)}%)\n"
    msg += f"   🔄 TRAILING: ${format_price(trail_price)} → {data['trail_pct']}%\n"

    return msg

# ==================== MAIN ====================
def main():
    now = datetime.now(MONTREAL_TZ)
    heure = now.hour
    minute = now.minute

    # Vérification jour férié OU week-end
    if is_ca_market_closed(now):
        print(f"🏖️ Marché CA fermé (week-end ou férié) – Arrêt.")
        if IS_MANUAL_RUN:
            msg = (
                "🤖 <b>NorthSentinel CA Only</b>\n"
                "Canadian intraday trading signals. Long & Short. Manual execution.\n"
                f"📅 {now.strftime('%Y-%m-%d %H:%M')} (Montreal) | 💰 Capital: ${CAPITAL:,.0f}\n"
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

    # Fenêtres horaires : 9h25-11h30 et 13h00-15h30
    morning = (heure == 9 and minute >= 25) or (heure == 10) or (heure == 11 and minute <= 30)
    afternoon = (heure == 13) or (heure == 14) or (heure == 15 and minute <= 30)

    if not (morning or afternoon):
        print(f"⏰ Hors fenêtre (9:25-11:30 ou 13:00-15:30 ET) – Arrêt.")
        # Envoi d'un message si le run est manuel
        if IS_MANUAL_RUN:
            msg = (
                "🤖 <b>NorthSentinel CA Only</b>\n"
                "Canadian intraday trading signals. Long & Short. Manual execution.\n"
                f"📅 {now.strftime('%Y-%m-%d %H:%M')} (Montreal) | 💰 Capital: ${CAPITAL:,.0f}\n"
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

    print("=" * 50)
    print(f"🤖 NorthSentinel CA Only – {now.strftime('%Y-%m-%d %H:%M')} (Montreal)")
    print(f"💰 Capital: ${CAPITAL:,.0f}")
    print(f"📰 News sources: Google RSS + CBC + Financial Post (3 sources)")
    print(f"📊 Modes: LONG + SHORT")
    print(f"⚙️ Risk per trade: {RISK_PER_TRADE*100:.1f}% | Max position: {MAX_CAPITAL_PER_POSITION*100:.1f}%")
    print("=" * 50)

    # === MODE NEWS (9h25 uniquement) ===
    if heure == 9 and minute == 25:
        run_news_scan()
        return

    # === MODE SCAN PRIX ===
    print("\n🔍 Scanning STOCKS...")
    stocks_results = []
    for ticker in STOCK_TICKERS:
        print(f"  - {ticker}...", end=" ")
        data = analyze_stock(ticker)
        if data:
            stocks_results.append(data)
            print(f"✅ Score {data['score']}/7 | {data['direction']}")
        else:
            print("❌")

    print("\n🔍 Scanning ETFs...")
    etfs_results = []
    for ticker in ETF_TICKERS:
        print(f"  - {ticker}...", end=" ")
        data = analyze_etf(ticker)
        if data:
            etfs_results.append(data)
            print(f"✅ Score {data['score']}/5 | {data['direction']}")
        else:
            print("❌")

    # Sélection du meilleur setup (par score puis volume)
    best_stock = max(stocks_results, key=lambda x: (x['score'], x['vol_ratio'])) if stocks_results else None
    best_etf = max(etfs_results, key=lambda x: (x['score'], x['vol_ratio'])) if etfs_results else None

    # Pas de message si aucun setup
    if not best_stock and not best_etf:
        print("\nℹ️ Aucun setup valide – Pas de message Telegram.")
        return

    # Construction du message Telegram (en anglais)
    msg = f"🤖 <b>NorthSentinel CA Only</b> – Scan {now.strftime('%H:%M')} (ET)\n"
    msg += f"💰 Capital: ${CAPITAL:,.0f} | Bias: ⚪ Neutral (CA)\n"
    msg += f"📊 Scanned: {len(STOCK_TICKERS)} Stocks, {len(ETF_TICKERS)} ETFs\n"
    msg += "═" * 35 + "\n"

    if best_stock:
        msg += "\n🚀 <b>BEST STOCK SETUP</b>\n"
        msg += build_setup_message(best_stock, is_etf=False)
    else:
        msg += "\n🚀 <b>BEST STOCK SETUP</b>\n❌ No valid stock setup for this scan.\n"

    if best_etf:
        msg += "\n🚀 <b>BEST ETF SETUP</b>\n"
        msg += build_setup_message(best_etf, is_etf=True)
    else:
        msg += "\n🚀 <b>BEST ETF SETUP</b>\n❌ No valid ETF setup for this scan.\n"

    msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "<i>Informational automated signal. Not financial or trading advice.</i>"

    send_telegram(msg)
    print("\n✅ Scan terminé.")

if __name__ == "__main__":
    main()
