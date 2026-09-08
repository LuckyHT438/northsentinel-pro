# ============================================================
# NORTHSENTINEL CA ONLY — SCANNER INTRADAY CONTINU (BOUCLE)
# SHORTS + LONGS — 3 SOURCES DE NEWS (uniquement pour le scoring)
# VERSION 120 TICKERS — PRIX D'ENTRÉE = DERNIER PRIX NÉGOCIÉ
# AVEC GESTION DES RISQUES DYNAMIQUE (spread, volume, cap, gap, institutions)
# R/R ≥ 2:1 — SCORE INSTITUTIONNEL DÉTAILLÉ DANS LES LOGS
# GESTION COMPLÈTE DES JOURS FÉRIÉS ET EARLY CLOSES
# INTÉGRATION VWAP (Polygon.io) ET POC (Alpha Vantage)
# SCAN TOUTES LES 30 MINUTES — CONVICTION INTÉGRÉE
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
    "price_max_etfs": 300.00,
    "scan_interval_minutes": 30,
    "tickers": {
        "stocks": [
            # === EXISTANTS (54) ===
            "MFC.TO", "GWO.TO", "POW.TO", "SU.TO", "CNQ.TO",
            "WCP.TO", "CCO.TO", "DOL.TO", "ABX.TO", "K.TO",
            "LUN.TO", "FM.TO", "T.TO", "BCE.TO", "RCI-B.TO",
            "BB.TO", "LSPD.TO", "AC.TO", "CAE.TO",
            "BNS.TO",
            "ATZ.TO", "GRGD.TO", "SPCX.TO", "ATD.TO",
            "MRU.TO", "L.TO", "EMP.A.TO", "CP.TO", "CNR.TO",
            "TFII.TO", "MDA.TO", "BBD-B.TO", "CGO.TO", "QBR-B.TO",
            "IFC.TO", "SLF.TO", "RBA.TO",
            "NA.TO",
            "WELL.TO",
            "GIB-A.TO", "OTEX.TO", "DSG.TO", "CLS.TO",
            "KTN.V",
            "AEM.TO", "WPM.TO", "EQX.TO", "LUG.TO", "FSV.TO",
            "BEP-UN.TO", "BAM.TO", "BN.TO", "NTR.TO",

            # === NOUVEAUX (24) ===
            # Financiers
            "TD.TO", "CM.TO", "RY.TO",
            # Énergie
            "ENB.TO", "ARX.TO", "VET.TO", "PPL.TO", "TRP.TO",
            # Mines & matériaux
            "BTO.TO", "FNV.TO", "HBM.TO", "AGI.TO", "NCM.TO",
            # Technologie / Infrastructure IA
            "SHOP.TO", "KEEL.TO",
            # Industrie / Équipements tech
            "WN.TO", "HPS-A.TO",
            # TSX-Venture
            "ARTG.V", "TOI.V", "QNC.V",

            # === REMPLACEMENTS (7) ===
            "BTE.TO", "MEG.TO", "FR.TO", "SIL.TO", "EQB.TO", "TRI.TO", "GIL.TO"
        ],
        "etfs": [
            # === EXISTANTS (27) ===
            "XFN.TO", "ZEB.TO", "XEG.TO", "ZEO.TO", "XGD.TO",
            "XMA.TO", "XIT.TO", "XST.TO", "XRE.TO", "XUT.TO",
            "ZSP.TO", "XIC.TO", "HCLN.TO", "HHIS.TO", "HXS.TO",
            "HXQ.TO", "VFV.TO", "XQQ.TO", "HHL.TO", "TXF.TO",
            "HUTL.TO", "ZDI.TO", "VI.TO", "VRE.TO", "FIE.TO",
            "ZDC.TO", "ZWA.TO",

            # === NOUVEAUX (15) ===
            "XIU.TO", "ZCN.TO", "HNU.TO", "HOU.TO", "ZUB.TO",
            "ZFL.TO", "DLR.TO", "ZWB.TO", "HXT.TO",
            "XSP.TO", "XEF.TO", "XEC.TO", "ZAG.TO"
        ]
    }
}

# ==================== PARAMÈTRES GLOBAUX ====================
MONTREAL_TZ = pytz.timezone('America/Toronto')
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_CA_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CA_CHAT_ID")
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
ALPHAVANTAGE_API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY")

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
SCAN_INTERVAL = CONFIG['scan_interval_minutes']
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
    retry = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    session.timeout = 15
    return session

HTTP_SESSION = create_session()

# ==================== FONCTIONS TELEGRAM ====================
def send_telegram(message):
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

# ==================== JOURS FÉRIÉS ====================
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
    # Family Day (deuxième lundi de février)
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
    # Victoria Day (lundi précédant le 25 mai)
    vic = date(year, 5, 24)
    while vic.weekday() != 0:
        vic = date(year, 5, vic.day - 1)
    ca.add(vic)
    # Civic Holiday (premier lundi d'août)
    civ = date(year, 8, 1)
    while civ.weekday() != 0:
        civ = date(year, 8, civ.day + 1)
    ca.add(civ)
    # Labour Day (premier lundi de septembre)
    lab = date(year, 9, 1)
    while lab.weekday() != 0:
        lab = date(year, 9, lab.day + 1)
    ca.add(lab)
    # Canadian Thanksgiving (deuxième lundi d'octobre)
    thanks = date(year, 10, 1)
    while thanks.weekday() != 0:
        thanks = date(year, 10, thanks.day + 1)
    ca.add(date(year, 10, thanks.day + 7))
    return ca

def is_ca_market_closed(check_date):
    if isinstance(check_date, datetime):
        check_date = check_date.date()
    if check_date.weekday() >= 5:
        return True
    holidays = _build_ca_holidays(check_date.year)
    adjusted = {_adjust_weekend(d) for d in holidays}
    return check_date in adjusted

# ==================== FERMETURES ANTICIPÉES (EARLY CLOSE) ====================
def _build_early_close_dates(year):
    from datetime import date
    early_dates = {}
    # 24 décembre
    early_dates[date(year, 12, 24)] = 13
    # 31 décembre
    early_dates[date(year, 12, 31)] = 13
    return early_dates

def is_early_close(check_date):
    if isinstance(check_date, datetime):
        check_date = check_date.date()
    early_dates = _build_early_close_dates(check_date.year)
    return check_date in early_dates

def get_early_close_hour(check_date):
    if isinstance(check_date, datetime):
        check_date = check_date.date()
    early_dates = _build_early_close_dates(check_date.year)
    return early_dates.get(check_date, None)

# ==================== NEWS ====================
def get_news_for_ticker(ticker):
    all_news = []
    ticker_clean = ticker.replace('.TO', '').replace('.V', '').upper()
    try:
        params = {"q": f"{ticker_clean}+stock", "hl": "en-CA", "gl": "CA"}
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
    bullish_strong = ['fda approval', 'partnership', 'deal', 'acquisition', 'buyout', 'merger', 'earnings beat', 'upgraded', 'breakthrough', 'contract awarded', 'drill results', 'high-grade', 'discovery', 'resource estimate', 'feasibility study', 'permit granted', 'commercial production', 'joint venture', 'bought deal', 'flow-through', 'positive', 'upgrade', 'record revenue', 'guidance raised']
    bullish = ['growth', 'revenue', 'profit', 'gain', 'surge', 'rally', 'momentum', 'expansion', 'launch', 'agreement', 'assay', 'buy rating', 'outperform', 'overweight', 'new contract', 'granted', 'approved', 'commenced', 'completed', 'successful']
    bearish_strong = ['dilution', 'offering', 'bankruptcy', 'lawsuit', 'sec investigation', 'delisting', 'fda rejection', 'clinical failure', 'downgraded', 'private placement', 'unit offering', 'permit denied', 'cease trade', 'suspension', 'default', 'going concern', 'termination', 'insider selling', 'ceo departure', 'investigation', 'guidance lowered', 'missed estimates']
    bearish = ['loss', 'decline', 'drop', 'fall', 'warning', 'concern', 'risk', 'delay', 'delayed', 'suspended', 'halted', 'reduced', 'lowered', 'restructuring', 'layoff', 'impairment', 'write-down', 'debt']
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

# ==================== VWAP ET POC ====================
def get_vwap_polygon(ticker):
    """Récupère le VWAP via Polygon.io. Retourne None si erreur ou clé manquante."""
    if not POLYGON_API_KEY:
        return None
    try:
        # Polygon utilise le format sans suffixe .TO pour les tickers canadiens
        clean_ticker = ticker.replace('.TO', '').replace('.V', '')
        url = f"https://api.polygon.io/v1/indicators/vwap/{clean_ticker}?timespan=minute&window=1&adjusted=true&apiKey={POLYGON_API_KEY}"
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            return None
        data = r.json()
        if 'results' in data and data['results'] and 'values' in data['results']:
            # Le dernier VWAP est le plus récent
            return data['results']['values'][-1]['value']
        return None
    except:
        return None

def get_poc_alphavantage(ticker):
    """Récupère le POC via Alpha Vantage (Volume Profile simplifié). Retourne None si erreur ou clé manquante."""
    if not ALPHAVANTAGE_API_KEY:
        return None
    try:
        clean_ticker = ticker.replace('.TO', '').replace('.V', '')
        url = f"https://www.alphavantage.co/query?function=OHLCV&symbol={clean_ticker}&interval=1min&apikey={ALPHAVANTAGE_API_KEY}&outputsize=compact"
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            return None
        data = r.json()
        if 'Time Series (1min)' not in data:
            return None
        time_series = data['Time Series (1min)']
        # On calcule le POC comme le prix avec le plus gros volume sur la session
        # On agrège les volumes par prix (approximation grossière)
        volume_by_price = {}
        for ts, values in time_series.items():
            # On prend le prix de clôture comme représentatif
            price = float(values['4. close'])
            volume = float(values['5. volume'])
            # Arrondir le prix à 2 décimales pour regrouper
            price_rounded = round(price, 2)
            volume_by_price[price_rounded] = volume_by_price.get(price_rounded, 0) + volume
        if not volume_by_price:
            return None
        # Le POC est le prix avec le plus gros volume
        poc = max(volume_by_price, key=volume_by_price.get)
        return poc
    except:
        return None

def get_vwap_poc(ticker):
    """Retourne un tuple (vwap, poc) pour un ticker donné."""
    vwap = get_vwap_polygon(ticker)
    poc = get_poc_alphavantage(ticker)
    return vwap, poc

# ==================== SCORE INSTITUTIONNEL (AVEC DÉTAILS) ====================
def calculate_institutional_interest(info, price, vol_ratio, gap, direction):
    """
    Calcule un score d'intérêt institutionnel (0-10) basé sur des données disponibles pour le marché canadien.
    Retourne (score, details) où details est un dictionnaire contenant les sous-composantes.
    """
    score = 0
    details = {}
    held = info.get('heldPercentInstitutions', 0)
    if held is None:
        held = 0
    short_ratio = info.get('shortRatio', 0)
    if short_ratio is None:
        short_ratio = 0
    sma50 = info.get('fiftyDayAverage', 0)

    details['held'] = held
    details['short_ratio'] = short_ratio
    details['vol_ratio'] = vol_ratio
    details['sma50'] = sma50
    details['price'] = price
    details['gap'] = gap
    details['direction'] = direction

    # 1. Taux de détention institutionnelle élevé
    if held >= 0.6:
        score += 2
        details['held_bonus'] = 2
    elif held >= 0.4:
        score += 1
        details['held_bonus'] = 1
    else:
        details['held_bonus'] = 0

    # 2. Short squeeze potentiel : short ratio > 3 + gap haussier > 3% + direction LONG
    if short_ratio > 3 and direction == "LONG" and gap > 3:
        score += 2
        details['short_squeeze_bonus'] = 2
    else:
        details['short_squeeze_bonus'] = 0

    # 3. Volume anormal + cassure SMA50 (institutions actives)
    if vol_ratio > 2 and sma50 and price > sma50:
        score += 2
        details['volume_sma_bonus'] = 2
    elif vol_ratio > 1.5 and sma50 and price > sma50:
        score += 1
        details['volume_sma_bonus'] = 1
    else:
        details['volume_sma_bonus'] = 0

    # 4. Short ratio très élevé seul (intérêt baissier institutionnel)
    if short_ratio > 4 and direction == "SHORT":
        score += 1
        details['short_high_bonus'] = 1
    else:
        details['short_high_bonus'] = 0

    score = min(score, 10)
    details['total'] = score
    return score, details

# ==================== CONVICTION ====================
def calculate_conviction(direction, gap, vol_ratio, vwap, entry_price, inst_interest, market_bias):
    """
    Calcule le niveau de conviction pour un setup LONG ou SHORT.
    Retourne (label, emoji) : ("High", "🟢"), ("Moderate", "🟡"), ("Low", "⚫")
    """
    # Nettoyage du market_bias (enlève les émojis)
    bias = market_bias.replace("⚪ ", "").replace("🟢 ", "").replace("🔴 ", "").strip()
    
    # Feux verts pour LONG
    if direction == "LONG":
        # Feu 1: Gap >= 3% ET volume >= 1.5
        green_gap_vol = (gap >= 3.0 and vol_ratio >= 1.5)
        # Feu 2: VWAP disponible ET entry_price dans 0.5% du VWAP
        green_vwap = (vwap is not None and abs(entry_price - vwap) / vwap <= 0.005)
        # Feu 3: Inst. Interest >= 7
        green_inst = (inst_interest >= 7)
        
        green_count = sum([green_gap_vol, green_vwap, green_inst])
        
        # Décision
        if green_count == 3 and bias in ["Neutral", "Risk-on"]:
            return "High", "🟢"
        elif green_count >= 2 and bias in ["Neutral", "Risk-on"]:
            return "Moderate", "🟡"
        else:
            return "Low", "⚫"
    
    # Feux verts pour SHORT
    elif direction == "SHORT":
        # Feu 1: Gap <= -3% ET volume >= 1.5
        green_gap_vol = (gap <= -3.0 and vol_ratio >= 1.5)
        # Feu 2: VWAP disponible ET entry_price est en dessous du VWAP avec marge >= 0.2%
        green_vwap = (vwap is not None and entry_price < vwap * 0.998)
        # Feu 3: Inst. Interest >= 7
        green_inst = (inst_interest >= 7)
        
        green_count = sum([green_gap_vol, green_vwap, green_inst])
        
        # Décision
        if green_count == 3 and bias in ["Neutral", "Risk-off"]:
            return "High", "🟢"
        elif green_count == 2 and bias == "Neutral":
            return "Moderate", "🟡"
        else:
            return "Low", "⚫"
    
    # Fallback
    return "Low", "⚫"

# ==================== FONCTIONS D'ANALYSE ====================
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
    map_ex = {'TOR': 'TMX', 'TSX': 'TMX', 'TSXV': 'TSXV', 'CNQ': 'CSE', 'V': 'TSXV'}
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

# ==================== GESTION DES RISQUES DYNAMIQUE AVEC INSTITUTIONS ====================
def adjust_risk_with_factors(base_tp_pct, base_sl_pct, spread_pct, vol_ratio, cap_category, gap, held_pct):
    """
    Ajuste le TP, le SL et le Trailing en fonction des facteurs de marché.
    Retourne (tp_pct, sl_pct, trail_adj) où trail_adj est un ajustement en pourcentage à ajouter au trailing.
    """
    tp_pct = base_tp_pct
    sl_pct = base_sl_pct
    trail_adj = 0.0

    # 1. Spread
    if spread_pct > 0.5:
        sl_pct += 0.2

    # 2. Volume relatif
    if vol_ratio > 2.0:
        sl_pct -= 0.3
        tp_pct += 0.5
    elif vol_ratio < 0.5:
        sl_pct += 0.3

    # 3. Capitalisation
    if cap_category in ["Micro Cap", "Small Cap"]:
        sl_pct += 0.5
        tp_pct += 1.0
    elif cap_category in ["Large Cap", "Mega Cap"]:
        sl_pct -= 0.2

    # 4. Gap
    if abs(gap) > 10:
        tp_pct += 0.5

    # 5. Taux de détention institutionnelle
    if held_pct >= 0.6:
        sl_pct -= 0.2      # plus serré
        tp_pct -= 0.5      # moins ambitieux
        trail_adj -= 0.5   # trailing plus serré
    elif held_pct <= 0.2:
        sl_pct += 0.3      # plus large
        tp_pct += 1.0      # plus ambitieux
        trail_adj += 1.0   # trailing plus large

    # Bornes de sécurité
    sl_pct = max(0.5, min(sl_pct, 3.0))
    tp_pct = max(0.5, min(tp_pct, 8.0))

    return round(tp_pct, 2), round(sl_pct, 2), round(trail_adj, 2)

def apply_risk_mandate(tp_pct, sl_pct, min_ratio=2.0):
    """
    Garantit un ratio R/R ≥ min_ratio (ex: 2:1).
    Retourne (tp_pct, sl_pct) ajustés.
    """
    required_tp = sl_pct * min_ratio
    if tp_pct < required_tp:
        tp_pct = round(required_tp, 2)

    if sl_pct < 0.5:
        sl_pct = 0.5

    tp_pct = min(tp_pct, 8.0)
    sl_pct = min(sl_pct, 3.0)

    return round(tp_pct, 2), round(sl_pct, 2)

# ==================== ANALYSE STOCKS ====================
def analyze_stock(ticker, verbose=True):
    try:
        stock = yf.Ticker(ticker, session=HTTP_SESSION)
        info = stock.info
        time.sleep(random.uniform(0.3, 0.6))

        price = info.get('regularMarketPrice') or info.get('currentPrice')
        if not price or price < PRICE_MIN_STOCKS or price > PRICE_MAX_STOCKS:
            if verbose:
                print(f"  ❌ Prix hors limites ({price})")
            return None

        bid = info.get('bid')
        ask = info.get('ask')
        spread_pct = 0.0
        if bid and ask and bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            spread_pct = ((ask - bid) / mid) * 100
            if spread_pct > MAX_SPREAD_PCT:
                if verbose:
                    print(f"  ❌ Spread {spread_pct:.2f}% > {MAX_SPREAD_PCT}%")
                return None

        prev_close = info.get('previousClose')
        if not prev_close or prev_close == 0:
            if verbose:
                print("  ❌ Pas de prix de clôture précédent")
            return None

        gap = ((price - prev_close) / prev_close) * 100

        # === SCORING ===
        score = 0
        criteres = {}

        if 2 <= gap <= 40:
            direction = "LONG"
            score += 1
            criteres['gap'] = "✅"
        elif -40 <= gap <= -2:
            direction = "SHORT"
            score += 1
            criteres['gap'] = "✅"
        else:
            criteres['gap'] = "❌"
            if verbose:
                print(f"  ❌ Gap {gap:.2f}% hors [2,40] ou [-40,-2]")
            return None

        volume = info.get('volume', 0)
        avg_vol = info.get('averageVolume', volume)
        vol_ratio = volume / avg_vol if avg_vol > 0 else 1
        if vol_ratio > 0.8:
            score += 1
            criteres['vol'] = "✅"
        else:
            criteres['vol'] = "❌"

        float_shares = info.get('floatShares')
        if float_shares is not None and float_shares < 100_000_000:
            score += 1
            criteres['float'] = "✅"
        elif float_shares is None:
            score += 1
            criteres['float'] = "✅ (N/A)"
        else:
            criteres['float'] = "❌"

        beta = info.get('beta')
        if beta is not None and beta > 0.8:
            score += 1
            criteres['beta'] = "✅"
        elif beta is None:
            score += 1
            criteres['beta'] = "✅ (N/A)"
        else:
            criteres['beta'] = "❌"

        short_ratio = info.get('shortRatio')
        if short_ratio is not None and short_ratio > 1.5:
            score += 1
            criteres['short'] = "✅"
        elif short_ratio is None:
            score += 1
            criteres['short'] = "✅ (N/A)"
        else:
            criteres['short'] = "❌"

        sma50 = info.get('fiftyDayAverage')
        if sma50:
            if direction == "LONG" and price > sma50:
                score += 1
                criteres['sma50'] = "✅"
            elif direction == "SHORT" and price < sma50:
                score += 1
                criteres['sma50'] = "✅"
            else:
                criteres['sma50'] = "❌"
        else:
            criteres['sma50'] = "❌ (N/A)"

        news = get_news_for_ticker(ticker)
        if news:
            for n in news[:3]:
                sent = analyze_sentiment(n['title'])
                if direction == "LONG" and sent >= 1:
                    score += 1
                    criteres['news'] = "✅"
                    break
                elif direction == "SHORT" and sent <= -1:
                    score += 1
                    criteres['news'] = "✅"
                    break
                elif direction == "LONG" and sent <= -2:
                    score -= 1
                    criteres['news'] = "⚠️ (-1)"
                    break
                elif direction == "SHORT" and sent >= 2:
                    score -= 1
                    criteres['news'] = "⚠️ (-1)"
                    break
            else:
                criteres['news'] = "❌"
        else:
            criteres['news'] = "❌"

        if verbose:
            print(f"  📊 Score: {score}/7 | Gap: {gap:.2f}% | Vol: {vol_ratio:.2f}x | Direction: {direction}")
            print(f"     Critères: Gap {criteres.get('gap','❌')} | Vol {criteres.get('vol','❌')} | Float {criteres.get('float','❌')} | Beta {criteres.get('beta','❌')} | Short {criteres.get('short','❌')} | SMA50 {criteres.get('sma50','❌')} | News {criteres.get('news','❌')}")

        if score < SCORE_MIN_STOCKS:
            if verbose:
                print(f"  ❌ Score {score} < {SCORE_MIN_STOCKS}")
            return None

        # === CALCUL DU SCORE INSTITUTIONNEL ===
        inst_score, inst_details = calculate_institutional_interest(info, price, vol_ratio, gap, direction)

        if verbose:
            # Label du score
            if inst_score >= 7:
                inst_label = "High"
            elif inst_score >= 4:
                inst_label = "Moderate"
            else:
                inst_label = "Low"
            print(f"     🏛️ Inst. Interest: {inst_score}/10 ({inst_label})")
            held_bonus = inst_details['held_bonus']
            if held_bonus > 0:
                print(f"       - heldPercentInstitutions: {inst_details['held']*100:.1f}% → +{held_bonus}")
            if inst_details['short_squeeze_bonus'] > 0:
                print(f"       - Short Ratio: {inst_details['short_ratio']:.1f} → bonus short squeeze +{inst_details['short_squeeze_bonus']}")
            vol_sma_bonus = inst_details['volume_sma_bonus']
            if vol_sma_bonus > 0:
                if inst_details['vol_ratio'] > 2:
                    print(f"       - Vol ratio: {inst_details['vol_ratio']:.2f} (>2) → +{vol_sma_bonus}")
                else:
                    print(f"       - Vol ratio: {inst_details['vol_ratio']:.2f} (>1.5) → +{vol_sma_bonus}")
                print(f"       - Prix > SMA50 ({inst_details['price']:.2f} > {inst_details['sma50']:.2f}) → +{vol_sma_bonus}")
            if inst_details['short_high_bonus'] > 0:
                print(f"       - Short Ratio: {inst_details['short_ratio']:.1f} (>4) → +1")
            print(f"       - Total: {inst_score}/10")

        # === RÉCUPÉRATION VWAP/POC ===
        vwap, poc = get_vwap_poc(ticker)
        if vwap is not None:
            vwap = round(vwap, 2)
        if poc is not None:
            poc = round(poc, 2)

        # === CALCUL DES TP/SL ===
        cap_category = get_market_cap_category(ticker)
        exchange = get_exchange(info)
        confidence = get_confidence_score(score, vol_ratio, gap, cap_category)

        held_pct = info.get('heldPercentInstitutions', 0.5)
        if held_pct is None:
            held_pct = 0.5

        if abs(gap) >= 20:
            tp_brut = 2.0 + (score - 4) * 0.6
        elif abs(gap) >= 10:
            tp_brut = 1.5 + (score - 4) * 0.4
        else:
            tp_brut = 0.5 + (score - 4) * 0.2

        if score >= 6:
            sl_brut = 2.0
        else:
            sl_brut = 2.5

        tp_adj, sl_adj, trail_adj = adjust_risk_with_factors(
            tp_brut, sl_brut, spread_pct, vol_ratio, cap_category, gap, held_pct
        )

        tp_final, sl_final = apply_risk_mandate(tp_adj, sl_adj, min_ratio=2.0)

        if direction == "LONG":
            tp_mult = 1 + tp_final / 100
            sl_mult = 1 - sl_final / 100
        else:
            tp_mult = 1 - tp_final / 100
            sl_mult = 1 + sl_final / 100

        if score >= 8:
            trail = 2.5
        elif score >= 6:
            trail = 3.0
        else:
            trail = 4.0

        trail += trail_adj
        trail = max(1.0, min(trail, 6.0))

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
            'tp_mult': round(tp_mult, 3),
            'sl_mult': round(sl_mult, 3),
            'trail_pct': round(trail, 2),
            'tp_pct': round(tp_final, 2),
            'sl_pct': round(sl_final, 2),
            'inst_interest': inst_score,
            'short_ratio': short_ratio,   # ajout pour affichage
            'vwap': vwap,
            'poc': poc
        }

    except Exception as e:
        if verbose:
            print(f"  ❌ Exception: {e}")
        return None

# ==================== ANALYSE ETF ====================
def analyze_etf(ticker):
    try:
        stock = yf.Ticker(ticker, session=HTTP_SESSION)
        info = stock.info
        hist = stock.history(period="1mo")
        time.sleep(random.uniform(0.3, 0.6))

        price = info.get('regularMarketPrice') or info.get('currentPrice')
        if not price:
            if not hist.empty and len(hist) > 0:
                price = hist['Close'].iloc[-1]
            else:
                return None

        if price < PRICE_MIN_STOCKS or price > PRICE_MAX_STOCKS:
            return None

        bid = info.get('bid')
        ask = info.get('ask')
        spread_pct = 0.0
        if bid and ask and bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            spread_pct = ((ask - bid) / mid) * 100
            if spread_pct > MAX_SPREAD_PCT:
                return None

        if hist.empty or len(hist) < 2:
            return None

        closes = hist['Close']
        volumes = hist['Volume']

        prev_close = closes.iloc[-2] if len(closes) > 1 else None
        if not prev_close:
            return None
        gap = ((price - prev_close) / prev_close) * 100

        volume = info.get('volume', 0)
        avg_vol = volumes.mean() if len(volumes) > 0 else volume
        vol_ratio = volume / avg_vol if avg_vol > 0 else 1
        aum = info.get('totalAssets', 0) or info.get('assetsUnderManagement', 0)

        # === SCORING ETF ===
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

        # === SCORE INSTITUTIONNEL ===
        inst_score, _ = calculate_institutional_interest(info, price, vol_ratio, gap, direction)

        # === VWAP/POC ===
        vwap, poc = get_vwap_poc(ticker)
        if vwap is not None:
            vwap = round(vwap, 2)
        if poc is not None:
            poc = round(poc, 2)

        # === Récupération du Short Ratio (si disponible) ===
        short_ratio = info.get('shortRatio', None)

        # === CALCUL DES TP/SL ===
        if abs(gap) >= 6:
            tp_brut = 1.5 + (score - 3) * 0.5
        elif abs(gap) >= 3:
            tp_brut = 1.0 + (score - 3) * 0.5
        else:
            tp_brut = 0.5 + (score - 3) * 0.5

        sl_brut = 2.0

        cap_etf = "Large Cap"
        held_pct = info.get('heldPercentInstitutions', 0.5)
        if held_pct is None:
            held_pct = 0.5
        tp_adj, sl_adj, trail_adj = adjust_risk_with_factors(
            tp_brut, sl_brut, spread_pct, vol_ratio, cap_etf, gap, held_pct
        )

        tp_final, sl_final = apply_risk_mandate(tp_adj, sl_adj, min_ratio=2.0)

        if direction == "LONG":
            tp_mult = 1 + tp_final / 100
            sl_mult = 1 - sl_final / 100
        else:
            tp_mult = 1 - tp_final / 100
            sl_mult = 1 + sl_final / 100

        trail = 3.0
        trail += trail_adj
        trail = max(1.0, min(trail, 6.0))

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
            'tp_mult': round(tp_mult, 3),
            'sl_mult': round(sl_mult, 3),
            'trail_pct': round(trail, 2),
            'tp_pct': round(tp_final, 2),
            'sl_pct': round(sl_final, 2),
            'inst_interest': inst_score,
            'short_ratio': short_ratio,   # ajout pour affichage (peut être None)
            'vwap': vwap,
            'poc': poc
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

def build_setup_message(data, is_etf=False, bias="⚪ Neutral"):
    max_score = 7 if not is_etf else 5
    entry = data['price']
    direction = data['direction']

    if direction == "LONG":
        tp = round(entry * data['tp_mult'], 2)
        sl = round(entry * data['sl_mult'], 2)
        trail_price = round(entry * (1 - data['trail_pct'] / 100), 2)
        gain_pct = round((tp/entry - 1) * 100, 1)
        loss_pct = round((1 - sl/entry) * 100, 1)
    else:
        tp = round(entry * (2 - data['tp_mult']), 2)
        sl = round(entry * (2 - data['sl_mult']), 2)
        trail_price = round(entry * (1 + data['trail_pct'] / 100), 2)
        gain_pct = round((1 - tp/entry) * 100, 1)
        loss_pct = round((sl/entry - 1) * 100, 1)

    qty = calculate_quantity(entry, sl, CAPITAL, RISK_PER_TRADE, MAX_CAPITAL_PER_POSITION)

    spread_display = ""
    if data['spread_pct'] > 0:
        spread_usd = round((data['spread_pct'] / 100) * entry, 2)
        spread_display = f" | Spread: {data['spread_pct']:.2f}% (${spread_usd:.2f})"

    verdict_text, verdict_emoji = get_verdict(data['confidence'])
    direction_emoji = "📈 LONG" if direction == "LONG" else "📉 SHORT"
    gap_display = f"+{data['gap']:.2f}%" if data['gap'] >= 0 else f"{data['gap']:.2f}%"

    inst = data.get('inst_interest', 0)
    if inst >= 7:
        inst_label = "High"
    elif inst >= 4:
        inst_label = "Moderate"
    else:
        inst_label = "Low"

    vwap_display = f"${data['vwap']:.2f}" if data.get('vwap') is not None else "N/A"
    poc_display = f"${data['poc']:.2f}" if data.get('poc') is not None else "N/A"
    cap_display = f"{data['cap_category']}" if not is_etf and 'cap_category' in data else ""

    # Short Ratio
    short_ratio = data.get('short_ratio')
    if short_ratio is not None:
        short_display = f"{short_ratio:.1f}"
    else:
        short_display = "N/A"

    # Conviction
    conv_label, conv_emoji = calculate_conviction(
        direction, data['gap'], data['vol_ratio'], data.get('vwap'), entry, inst, bias
    )

    msg = f"🔹 <b>{data['ticker']}</b> ({data['exchange']}){spread_display}\n"
    msg += f"   Direction: <b>{direction_emoji}</b>\n"
    msg += f"   Quality: <b>{data['score']}/{max_score}</b> | Confidence: <b>{data['confidence']}/10</b>\n"
    msg += f"   GAP: {gap_display} | Volume: x{data['vol_ratio']:.2f} | Short ratio: {short_display}\n"
    msg += f"   VWAP: {vwap_display} | POC: {poc_display}"
    if cap_display:
        msg += f" | Cap: {cap_display}"
    msg += "\n"
    msg += f"   Market Bias: {bias}\n"
    msg += f"   🏛️ Institutional Interest: {inst}/10 ({inst_label})\n"
    msg += f"   ⚖️ VERDICT: {verdict_emoji} {verdict_text} | Conviction: {conv_emoji} {conv_label}\n"
    msg += f"   🎯 ENTRY: ${format_price(entry)}\n"
    msg += f"   📦 QUANTITY: {qty} {'shares' if not is_etf else 'units'}\n"
    msg += f"   📈 TAKE-PROFIT: ${format_price(tp)} (+{gain_pct}%)\n"
    msg += f"   🛑 STOP LOSS: ${format_price(sl)} (-{loss_pct}%)\n"
    msg += f"   🔄 TRAILING STOP: ${format_price(trail_price)} → {data['trail_pct']}%\n"
    return msg

# ==================== FONCTION D'ATTENTE ====================
def wait_until_target(target_hour, target_minute):
    now = datetime.now(MONTREAL_TZ)
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(minutes=SCAN_INTERVAL)
    diff = (target - now).total_seconds()
    if diff > 0:
        print(f"⏳ Attente jusqu'à {target.strftime('%H:%M')}... ({diff/60:.1f} min)")
        time.sleep(diff)

# ==================== MAIN ====================
def main():
    now = datetime.now(MONTREAL_TZ)
    heure = now.hour
    minute = now.minute

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

    early_close = is_early_close(now)
    early_hour = get_early_close_hour(now) if early_close else None
    if early_close:
        print(f"⚠️ Fermeture anticipée détectée – Marché ferme à {early_hour}:00 ET.")
        if TELEGRAM_TOKEN:
            msg_early = (
                "⚠️ <b>Early Close Today</b>\n"
                f"Market closes at {early_hour}:00 PM ET.\n"
                "Afternoon session will end at that time."
            )
            send_telegram(msg_early)

    if 9 <= heure <= 11 and (heure < 11 or minute <= 30):
        session = "morning"
        start_hour, start_min = 9, 30
        end_hour, end_min = 11, 30
        print("☀️ Session MATIN détectée.")
    elif 13 <= heure <= 15 and (heure < 15 or minute <= 30):
        session = "afternoon"
        start_hour, start_min = 13, 0
        if early_close and early_hour is not None:
            end_hour = early_hour
            end_min = 0
            print(f"🌙 Session APRÈS-MIDI détectée (EARLY CLOSE – fin à {end_hour:02d}:{end_min:02d} ET).")
        else:
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

    now = datetime.now(MONTREAL_TZ)
    if now.hour < start_hour or (now.hour == start_hour and now.minute < start_min):
        print(f"⏳ Attente du début de session à {start_hour:02d}:{start_min:02d}...")
        wait_until_target(start_hour, start_min)
        now = datetime.now(MONTREAL_TZ)

    while True:
        now = datetime.now(MONTREAL_TZ)
        if now.hour > end_hour or (now.hour == end_hour and now.minute > end_min):
            print(f"⏹️ Fin de session atteinte ({end_hour:02d}:{end_min:02d}) – Arrêt.")
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

        if current_min % SCAN_INTERVAL == 0:
            print(f"\n📊 Scan de prix à {now.strftime('%H:%M')} (session {session})")

            stocks_results = []
            for ticker in STOCK_TICKERS:
                print(f"  - {ticker}:")
                data = analyze_stock(ticker, verbose=True)
                if data:
                    stocks_results.append(data)
                    inst = data.get('inst_interest', 0)
                    vwap = data.get('vwap', 'N/A')
                    poc = data.get('poc', 'N/A')
                    short_r = data.get('short_ratio', 'N/A')
                    print(f"    ✅ Score {data['score']}/7 | {data['direction']} | TP: {data['tp_pct']}% | SL: {data['sl_pct']}% | Inst: {inst}/10 | VWAP: {vwap} | POC: {poc} | Short: {short_r}")
                else:
                    print("    ❌")

            etfs_results = []
            for ticker in ETF_TICKERS:
                print(f"  - {ticker}...", end=" ")
                data = analyze_etf(ticker)
                if data:
                    etfs_results.append(data)
                    inst = data.get('inst_interest', 0)
                    vwap = data.get('vwap', 'N/A')
                    poc = data.get('poc', 'N/A')
                    short_r = data.get('short_ratio', 'N/A')
                    print(f"✅ Score {data['score']}/5 | {data['direction']} | TP: {data['tp_pct']}% | SL: {data['sl_pct']}% | Inst: {inst}/10 | VWAP: {vwap} | POC: {poc} | Short: {short_r}")
                else:
                    print("❌")

            best_stock = max(stocks_results, key=lambda x: (x['score'], x['vol_ratio'])) if stocks_results else None
            best_etf = max(etfs_results, key=lambda x: (x['score'], x['vol_ratio'])) if etfs_results else None

            if best_stock or best_etf:
                msg = "🤖 <b>NorthSentinel CA Only</b>™\n"
                msg += "<i>Canadian intraday trading signals. Long & Short. Manual execution. </i>\n"
                msg += f"📅 {now.strftime('%Y-%m-%d %H:%M')} (Montreal) | Scanned: {len(STOCK_TICKERS)} Stocks, {len(ETF_TICKERS)} ETFs\n"
                msg += f"Capital: ${CAPITAL:,.0f} (Paper Trading Account)\n"
                msg += "═══════════════════════════════════\n"

                if best_stock:
                    msg += "\n🚀 <b>BEST STOCK SETUP</b>\n"
                    msg += build_setup_message(best_stock, is_etf=False, bias="⚪ Neutral")
                else:
                    msg += "\n🚀 <b>BEST STOCK SETUP</b>\n❌ No valid stock setup for this scan.\n"

                if best_etf:
                    msg += "\n🚀 <b>BEST ETF SETUP</b>\n"
                    msg += build_setup_message(best_etf, is_etf=True, bias="⚪ Neutral")
                else:
                    msg += "\n🚀 <b>BEST ETF SETUP</b>\n❌ No valid ETF setup for this scan.\n"

                msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                msg += "<i>Informational automated signal. Not financial or trading advice. </i>"
                send_telegram(msg)
            else:
                print("ℹ️ Aucun setup valide – Pas de message Telegram.")

        next_min = ((current_min // SCAN_INTERVAL) + 1) * SCAN_INTERVAL
        next_hour = current_hour
        if next_min >= 60:
            next_min = 0
            next_hour += 1
        wait_until_target(next_hour, next_min)

if __name__ == "__main__":
    main()
