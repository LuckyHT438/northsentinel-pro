# ============================================================
# NORTHSENTINEL PRO — ADVANCED SCALPING & OVERNIGHT SIGNALS
# ============================================================
import requests
import yfinance as yf
import time
import random
import json
from datetime import datetime, timezone, timedelta, date
from bs4 import BeautifulSoup
import re
import pytz
import os
import subprocess
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# === MODULES PRO ===
from pro_volume_profile import get_volume_profile
from pro_confidence import calculate_confidence_score
from pro_macro_context import get_macro_context

# Récupération depuis les secrets GitHub
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_PRO_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_PRO_CHAT_ID")
PUBLIC_CHANNEL_ID = os.environ.get("PUBLIC_CHANNEL_ID", "")  # Gardé pour info, mais non utilisé pour les signaux
MONTREAL_TZ = pytz.timezone('America/Toronto')
DATA_REPO_TOKEN = os.environ.get("DATA_REPO_TOKEN")

# === CONFIGURATION DÉPÔT DE DONNÉES ===
DATA_REPO_URL = "https://x-access-token:{}@github.com/LuckyHT438/northsentinel-data.git".format(DATA_REPO_TOKEN) if DATA_REPO_TOKEN else None

# === SEUIL DE SPREAD MAXIMUM (5%) ===
MAX_SPREAD_PCT = 5.0

def push_signals_to_repo():
    """
    Clone le dépôt, fusionne les signaux locaux avec ceux du dépôt,
    et pousse le résultat.
    """
    if not DATA_REPO_TOKEN:
        print("⚠️ DATA_REPO_TOKEN manquant — impossible de pousser vers le dépôt de données")
        return False
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    local_file = os.path.join(script_dir, "pro_signals_today.json")
    
    if not os.path.exists(local_file):
        print("ℹ️ Aucun fichier local à pousser")
        return False
    
    try:
        repo_dir = "northsentinel-data"
        repo_file = os.path.join(repo_dir, "pro_signals_today.json")
        
        if not os.path.exists(repo_dir):
            print("📥 Clonage du dépôt de données...")
            subprocess.run(["git", "clone", DATA_REPO_URL, repo_dir], check=True, capture_output=True)
        else:
            os.chdir(repo_dir)
            subprocess.run(["git", "pull", "origin", "main"], check=True, capture_output=True)
            os.chdir("..")
        
        with open(local_file, 'r') as f:
            local_signals = json.load(f)
        
        repo_signals = []
        if os.path.exists(repo_file):
            with open(repo_file, 'r') as f:
                repo_signals = json.load(f)
                if not isinstance(repo_signals, list):
                    repo_signals = []
        
        existing_keys = set()
        for s in repo_signals:
            key = (s.get('ticker'), s.get('type'), s.get('timestamp'))
            existing_keys.add(key)
        
        for s in local_signals:
            key = (s.get('ticker'), s.get('type'), s.get('timestamp'))
            if key not in existing_keys:
                repo_signals.append(s)
                existing_keys.add(key)
        
        with open(repo_file, 'w') as f:
            json.dump(repo_signals, f, indent=2)
        
        os.chdir(repo_dir)
        subprocess.run(["git", "config", "user.name", "NorthSentinel Bot"], check=True)
        subprocess.run(["git", "config", "user.email", "bot@northsentinel.com"], check=True)
        subprocess.run(["git", "add", "pro_signals_today.json"], check=True)
        subprocess.run(["git", "commit", "-m", f"Mise à jour des signaux Pro - {datetime.now(MONTREAL_TZ).strftime('%Y-%m-%d %H:%M')}"], check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", "main"], check=True, capture_output=True)
        os.chdir("..")
        
        print(f"✅ Signaux Pro fusionnés et poussés vers le dépôt (total: {len(repo_signals)})")
        return True
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Erreur Git: {e.stderr.decode() if e.stderr else e}")
        os.chdir(script_dir)
        return False
    except Exception as e:
        print(f"❌ Erreur lors du push: {e}")
        return False

# === PARAMÈTRES ACTIONS ===
CAPITAL = 1_000_000
RISK_PER_TRADE = 0.02
MAX_CAPITAL_PER_POSITION = 0.10
SCORE_MIN_ACTIONS = 5
SCORE_MIN_OVERNIGHT_ACTIONS = 6
PRICE_MAX_ACTIONS = 300
PRICE_MIN_ACTIONS = 2.00

# === PARAMÈTRES FNB ===
SCORE_MIN_FNB = 5
SCORE_MIN_OVERNIGHT_FNB = 5
PRICE_MAX_FNB = 9999

# === CALENDRIER JOURS FÉRIÉS US/CANADA ===
def _build_us_holidays(year):
    us_holidays = set()
    us_holidays.add(date(year, 1, 1))
    us_holidays.add(date(year, 6, 19))
    us_holidays.add(date(year, 7, 4))
    us_holidays.add(date(year, 12, 25))

    mlk = date(year, 1, 1)
    while mlk.weekday() != 0:
        mlk = date(year, 1, mlk.day + 1)
    mlk = date(year, 1, mlk.day + 14)
    us_holidays.add(mlk)

    pres = date(year, 2, 1)
    while pres.weekday() != 0:
        pres = date(year, 2, pres.day + 1)
    pres = date(year, 2, pres.day + 14)
    us_holidays.add(pres)

    mem = date(year, 5, 31)
    while mem.weekday() != 0:
        mem = date(year, 5, mem.day - 1)
    us_holidays.add(mem)

    lab = date(year, 9, 1)
    while lab.weekday() != 0:
        lab = date(year, 9, lab.day + 1)
    us_holidays.add(lab)

    thanks = date(year, 11, 1)
    while thanks.weekday() != 3:
        thanks = date(year, 11, thanks.day + 1)
    thanks = date(year, 11, thanks.day + 21)
    us_holidays.add(thanks)

    return us_holidays


def _build_ca_holidays(year):
    ca_holidays = set()
    ca_holidays.add(date(year, 1, 1))
    ca_holidays.add(date(year, 7, 1))
    ca_holidays.add(date(year, 12, 25))
    ca_holidays.add(date(year, 12, 26))

    fam = date(year, 2, 1)
    while fam.weekday() != 0:
        fam = date(year, 2, fam.day + 1)
    fam = date(year, 2, fam.day + 14)
    ca_holidays.add(fam)

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
    good_friday = easter - timedelta(days=2)
    ca_holidays.add(good_friday)

    vic = date(year, 5, 24)
    while vic.weekday() != 0:
        vic = date(year, 5, vic.day - 1)
    ca_holidays.add(vic)

    civ = date(year, 8, 1)
    while civ.weekday() != 0:
        civ = date(year, 8, civ.day + 1)
    ca_holidays.add(civ)

    lab = date(year, 9, 1)
    while lab.weekday() != 0:
        lab = date(year, 9, lab.day + 1)
    ca_holidays.add(lab)

    ca_thanks = date(year, 10, 1)
    while ca_thanks.weekday() != 0:
        ca_thanks = date(year, 10, ca_thanks.day + 1)
    ca_thanks = date(year, 10, ca_thanks.day + 7)
    ca_holidays.add(ca_thanks)

    return ca_holidays


def _adjust_weekend(d):
    if d.weekday() == 5:
        return d - timedelta(days=1)
    elif d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def is_us_market_closed(check_date=None):
    if check_date is None:
        check_date = datetime.now(MONTREAL_TZ).date()
    elif isinstance(check_date, datetime):
        check_date = check_date.date()

    year = check_date.year
    us_holidays = _build_us_holidays(year)
    adjusted_us = set()
    for d in us_holidays:
        adjusted_us.add(_adjust_weekend(d))

    return check_date in adjusted_us


def is_ca_market_closed(check_date=None):
    if check_date is None:
        check_date = datetime.now(MONTREAL_TZ).date()
    elif isinstance(check_date, datetime):
        check_date = check_date.date()

    year = check_date.year
    ca_holidays = _build_ca_holidays(year)
    adjusted_ca = set()
    for d in ca_holidays:
        adjusted_ca.add(_adjust_weekend(d))

    return check_date in adjusted_ca


def is_market_closed(check_date=None):
    if check_date is None:
        check_date = datetime.now(MONTREAL_TZ).date()
    elif isinstance(check_date, datetime):
        check_date = check_date.date()

    year = check_date.year
    early_close_dates = {date(year, 11, 28), date(year, 12, 24), date(year, 12, 31)}

    if check_date in early_close_dates:
        return 'early_close'

    us_closed = is_us_market_closed(check_date)
    ca_closed = is_ca_market_closed(check_date)

    if us_closed and ca_closed:
        return 'closed'
    elif us_closed:
        return 'us_closed'
    elif ca_closed:
        return 'ca_closed'
    else:
        return 'open'

# === SESSION HTTP UNIFIÉE ===
def create_session():
    session = requests.Session()
    retry = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    return session

HTTP_SESSION = create_session()

canadian_symbols = {
    "TD.TO", "BMO.TO", "BNS.TO", "NA.TO",
    "ENB.TO", "SU.TO", "CNQ.TO", "SOBO.TO",
    "FTS.TO", "AQN.TO", "H.TO", "BEP-UN.TO",
    "SHOP.TO", "LSPD.TO", "OTEX.TO", "SPCX.TO",
    "CAE.TO", "MDA.TO", "BBD-B.TO",
    "L.TO", "MRU.TO", "CCO.TO", "DOL.TO",
    "CNR.TO", "CP.TO", "T.TO", "BCE.TO",
    "BHC.TO", "CSH-UN.TO", "AND.TO",
    "AEM.TO", "ABX.TO", "WPM.TO",
    "GRDG.TO", "IFC.TO", "SLF.TO", "GWO.TO",
    "MG.TO", "RBA.TO", "TFII.TO"
}

# ============================================================
# FONCTION send_telegram (accepte plusieurs destinataires)
# ============================================================
def send_telegram(message, chat_ids=None):
    if not TELEGRAM_TOKEN:
        print("⚠️ Telegram token missing")
        return False

    # Si aucun destinataire n'est fourni, on utilise le propriétaire (comportement actuel)
    if chat_ids is None:
        chat_ids = [TELEGRAM_CHAT_ID]

    # Si chat_ids est un entier, on le convertit en liste
    if not isinstance(chat_ids, list):
        chat_ids = [chat_ids]

    success = True
    for chat_id in chat_ids:
        if not chat_id:
            continue
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                print(f"✅ Message envoyé à {chat_id}")
            else:
                print(f"❌ Échec pour {chat_id}: {r.status_code} - {r.text}")
                success = False
        except Exception as e:
            print(f"❌ Erreur pour {chat_id}: {e}")
            success = False

    return success

def get_exchange_from_info(info):
    exchange = info.get('exchange', '')
    exchange_map = {
        'NMS': 'NASDAQ', 'NGM': 'NASDAQ', 'NCM': 'NASDAQ',
        'NYQ': 'NYSE', 'NYM': 'NYSE', 'PCX': 'ARCA',
        'BTS': 'BATS', 'ASE': 'AMEX', 'PSE': 'NYSE ARCA',
        'TOR': 'TMX', 'TSX': 'TMX', 'TRV': 'TSXV', 'CNQ': 'CSE'
    }
    return exchange_map.get(exchange, exchange if exchange else 'US')

# === MARCHÉS SPÉCIFIQUES POUR LE BIAS ===
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
}

def _get_sector_performance(ticker):
    """Return today's performance for a sector ETF"""
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

def _get_market_bias(ticker):
    """
    Return market bias (Risk-on / Risk-off / Neutral) for the relevant market
    (US or CA) based on the ticker's exchange.
    """
    is_ca = ticker.endswith('.TO')
    market_etfs = MARKET_ETFS_CA if is_ca else MARKET_ETFS_US
    
    performances = {}
    up_count = 0
    down_count = 0
    
    for etf, name in market_etfs.items():
        change = _get_sector_performance(etf)
        if change is not None:
            performances[name] = {"ticker": etf, "change": change}
            if change > 0.3:
                up_count += 1
            elif change < -0.3:
                down_count += 1
    
    if not performances:
        return "⚪ Neutral (N/A)"
    
    market_label = "CA" if is_ca else "US"
    if up_count > down_count:
        return f"🟢 Risk-on ({market_label})"
    elif down_count > up_count:
        return f"🔴 Risk-off ({market_label})"
    else:
        return f"⚪ Neutral ({market_label})"

def get_global_market_bias():
    """
    Calcule le biais global du marché (US + CA) en analysant les secteurs ETF.
    Retourne 'Risk-on', 'Risk-off' ou 'Neutral'.
    """
    all_etfs = {**MARKET_ETFS_US, **MARKET_ETFS_CA}
    up_count = 0
    down_count = 0

    for ticker, _ in all_etfs.items():
        change = _get_sector_performance(ticker)
        if change is not None:
            if change > 0.3:
                up_count += 1
            elif change < -0.3:
                down_count += 1

    if up_count == 0 and down_count == 0:
        return "Neutral"

    if up_count > down_count:
        return "Risk-on"
    elif down_count > up_count:
        return "Risk-off"
    else:
        return "Neutral"

def get_market_bias_adjustment(bias_text):
    """
    Retourne les ajustements pour TP, SL et Trailing en fonction du biais.
    Risk-on → TP augmenté de 0.5%, SL réduit de 0.5% (plus serré), trailing réduit de 0.5%
    Risk-off → TP réduit de 0.5%, SL augmenté de 0.5% (plus large), trailing augmenté de 0.5%
    """
    if "Risk-on" in bias_text:
        return {"tp": 0.005, "sl": -0.005, "trail": -0.5}
    elif "Risk-off" in bias_text:
        return {"tp": -0.005, "sl": 0.005, "trail": 0.5}
    else:
        return {"tp": 0.0, "sl": 0.0, "trail": 0.0}

# === FONCTION DE CATÉGORIE DE CAPITALISATION ===
def get_market_cap_category(ticker):
    """
    Retourne la catégorie de capitalisation boursière d'un ticker
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        market_cap = info.get('marketCap', 0)
        
        if market_cap == 0:
            return "N/A"
        elif market_cap < 300_000_000:
            return "Micro Cap"
        elif market_cap < 2_000_000_000:
            return "Small Cap"
        elif market_cap < 10_000_000_000:
            return "Mid Cap"
        elif market_cap < 200_000_000_000:
            return "Large Cap"
        else:
            return "Mega Cap"
    except:
        return "N/A"

# === AJUSTEMENTS SELON LA CAPITALISATION (HARMONISÉ AVEC CORE) ===
def get_cap_adjustment(cap_category):
    adjustments = {
        "Mega Cap": {"tp": 0.0, "sl": 0.0, "trail": 0.0},
        "Large Cap": {"tp": 0.0, "sl": 0.0, "trail": 0.0},
        "Mid Cap": {"tp": -0.002, "sl": 0.002, "trail": 0.005},
        "Small Cap": {"tp": -0.005, "sl": 0.005, "trail": 0.010},
        "Micro Cap": {"tp": -0.010, "sl": 0.010, "trail": 0.015},
        "N/A": {"tp": 0.0, "sl": 0.0, "trail": 0.0}
    }
    return adjustments.get(cap_category, {"tp": 0.0, "sl": 0.0, "trail": 0.0})

# 🔧 PRO ADJUSTMENT: Ajustement basé sur le Confidence Score
def get_confidence_adjustment(confidence):
    """
    Retourne les ajustements pour TP, SL et Trailing en fonction du Confidence Score.
    Confidence > 8.5 → on peut viser plus large et resserrer les stops
    Confidence < 5.5 → on réduit l’ambition et on élargit les stops
    """
    if confidence >= 8.5:
        return {"tp": 0.010, "sl": -0.005, "trail": -0.5}   # TP +1%, SL -0.5%, trailing -0.5%
    elif confidence >= 7.5:
        return {"tp": 0.005, "sl": -0.002, "trail": -0.2}
    elif confidence >= 5.5:
        return {"tp": 0.0, "sl": 0.0, "trail": 0.0}
    elif confidence >= 3.5:
        return {"tp": -0.005, "sl": 0.010, "trail": 0.5}
    else:
        return {"tp": -0.010, "sl": 0.015, "trail": 1.0}

def get_trail_percent(score, is_fnb=False, cap_category="Large Cap", market_bias=None, confidence=None, spread_pct=0.0):
    if is_fnb:
        if score >= 5:
            base = 2.5
        elif score == 4:
            base = 3.0
        elif score == 3:
            base = 3.5
        else:
            base = 4.0
    else:
        if score >= 9:
            base = 2.5
        elif score == 8:
            base = 3.0
        elif score == 7:
            base = 3.5
        elif score == 6:
            base = 4.0
        elif score == 5:
            base = 4.5
        else:
            base = 5.0
    cap_adj = get_cap_adjustment(cap_category)
    bias_adj = get_market_bias_adjustment(market_bias) if market_bias else {"trail": 0.0}
    conf_adj = get_confidence_adjustment(confidence) if confidence is not None else {"trail": 0.0}
    # Augmenter le trailing de 0.5 * spread_pct pour les marchés illiquides
    spread_adj = spread_pct * 0.5
    return round(base + cap_adj["trail"] + bias_adj["trail"] + conf_adj["trail"] + spread_adj, 2)

def get_tp_multiplier(score, gap, post_news=False, cap_category="Large Cap", market_bias=None, confidence=None, spread_pct=0.0):
    if score < 6:
        if score == 5:
            base = 1.010
        else:
            base = 1.005
    elif gap >= 20:
        base = 1.02 + (score - 4) * 0.006
    elif gap >= 10:
        base = 1.015 + (score - 4) * 0.004
    else:
        base = 1.005 + (score - 4) * 0.002
    cap_adj = get_cap_adjustment(cap_category)
    bias_adj = get_market_bias_adjustment(market_bias) if market_bias else {"tp": 0.0}
    conf_adj = get_confidence_adjustment(confidence) if confidence is not None else {"tp": 0.0}
    # Réduire le TP du spread_pct/100 (coût de sortie au bid)
    spread_adj = spread_pct / 100.0
    base = round(base + cap_adj["tp"] + bias_adj["tp"] + conf_adj["tp"] - spread_adj, 3)
    if post_news:
        base = round(1.0 + (base - 1.0) * 0.833, 3)
    return round(base, 3)

def get_fnb_tp_multiplier(score, gap, post_news=False, market_bias=None, confidence=None, spread_pct=0.0):
    if score < 4:
        base = 1.005
    elif gap >= 6:
        base = 1.015 + (score - 3) * 0.005
    elif gap >= 3:
        base = 1.01 + (score - 3) * 0.005
    else:
        base = 1.005 + (score - 3) * 0.005
    bias_adj = get_market_bias_adjustment(market_bias) if market_bias else {"tp": 0.0}
    conf_adj = get_confidence_adjustment(confidence) if confidence is not None else {"tp": 0.0}
    spread_adj = spread_pct / 100.0
    base = round(base + bias_adj["tp"] + conf_adj["tp"] - spread_adj, 3)
    if post_news:
        base = round(1.0 + (base - 1.0) * 0.833, 3)
    return round(base, 3)

def get_sl_multiplier(score, cap_category="Large Cap", market_bias=None, confidence=None, spread_pct=0.0):
    if score >= 8:
        base = 0.97
    elif score >= 6:
        base = 0.96
    else:
        base = 0.95
    cap_adj = get_cap_adjustment(cap_category)
    bias_adj = get_market_bias_adjustment(market_bias) if market_bias else {"sl": 0.0}
    conf_adj = get_confidence_adjustment(confidence) if confidence is not None else {"sl": 0.0}
    # Élargir le stop (diminuer le multiplicateur) de spread_pct/200 pour éviter d'être stoppé par le spread
    spread_adj = spread_pct / 200.0
    return round(base - cap_adj["sl"] - bias_adj["sl"] - conf_adj["sl"] - spread_adj, 3)

def calculate_quantity(entry_price, stop_price, capital, risk_per_trade, max_capital_per_position):
    risk_amount = capital * risk_per_trade
    max_exposure = capital * max_capital_per_position
    stop_distance = entry_price - stop_price
    if stop_distance <= 0:
        return 0
    qty_risk = int(risk_amount / stop_distance)
    qty_cap = int(max_exposure / entry_price)
    return max(0, min(qty_risk, qty_cap))

# ============================================================
# FONCTION DE GESTION DES RISQUES (MANDAT STRICT AVEC TRAILING CORRIGÉ)
# IDENTIQUE À CELLE DU SCRIPT CORE
# ============================================================
def apply_risk_mandate(tp_mult, sl_mult, trail_pct, min_ratio=2.0, max_tp=5.0, max_sl=2.5, min_sl=0.5):
    """
    Applique les règles strictes NorthSentinel :
    - TP ≤ max_tp (%)
    - SL ≤ max_sl (%)
    - Ratio R/R ≥ min_ratio (1:2 par défaut)
    - SL min absolu = min_sl (en dessous -> rejet)
    - Trailing Stop : doit être plus serré que le SL (pourcentage plus petit)
      On le limite à 80% du SL, avec un plancher de 0.3% et un plafond de 5%.
    Retourne (tp_mult, sl_mult, trail_pct) ou (None, None, None) si rejet.
    """
    tp_pct = round((tp_mult - 1) * 100, 2)
    sl_pct = round((1 - sl_mult) * 100, 2)

    # 1. Plafonds
    tp_pct = min(tp_pct, max_tp)
    sl_pct = min(sl_pct, max_sl)

    # 2. Ratio 1:2 (on réduit le SL si nécessaire)
    required_sl = tp_pct / min_ratio
    if required_sl < sl_pct:
        sl_pct = round(required_sl, 2)

    # 3. SL minimum absolu -> rejet si trop serré
    if sl_pct < min_sl:
        print(f"❌ Trade REJETÉ : SL trop serré ({sl_pct:.2f}%)")
        return None, None, None

    # 4. Multiplicateurs finaux
    final_tp_mult = round(1 + tp_pct / 100, 3)
    final_sl_mult = round(1 - sl_pct / 100, 3)

    # 5. Trailing Stop : doit être plus serré que le SL (max 80% du SL)
    max_allowed_trail = sl_pct * 0.8  # par exemple SL 2% -> trail max 1.6%
    if trail_pct > max_allowed_trail:
        trail_pct = round(max_allowed_trail, 2)
    # Plancher de sécurité (pour éviter d'être trop serré)
    if trail_pct < 0.3:
        trail_pct = 0.3
    # Plafond absolu
    if trail_pct > 5.0:
        trail_pct = 5.0

    return final_tp_mult, final_sl_mult, trail_pct

# ============================================================

def get_exit_time():
    now_mtl = datetime.now(MONTREAL_TZ)
    if is_market_closed() == 'early_close':
        exit_time = now_mtl.replace(hour=13, minute=0, second=0, microsecond=0)
        return exit_time.strftime('%H:%M')
    if now_mtl.hour < 12:
        exit_time = now_mtl.replace(hour=11, minute=30, second=0, microsecond=0)
    else:
        exit_time = now_mtl.replace(hour=15, minute=45, second=0, microsecond=0)
    return exit_time.strftime('%H:%M')

# === FONCTION GET_GAP_MIN AVEC PARAMÈTRE BIAS ===
def get_gap_min(bias=None):
    """
    Retourne le gap minimum avec ajustement selon le biais de marché.
    bias : 'Risk-on', 'Risk-off', 'Neutral' ou None.
    """
    now_mtl = datetime.now(MONTREAL_TZ)
    if now_mtl.hour < 12:
        base = 5.0
    else:
        base = 2.0

    if bias == "Risk-on":
        return max(1.0, base - 0.5)
    elif bias == "Risk-off":
        return min(5.0, base + 0.5)
    else:
        return base

def get_news_rss(ticker):
    try:
        if ticker in canadian_symbols:
            base_url = "https://news.google.com/rss/search"
            params = {"q": f"{ticker}+stock", "hl": "en-CA", "gl": "CA"}
        else:
            base_url = "https://news.google.com/rss/search"
            params = {"q": f"{ticker}+stock", "hl": "en-US", "gl": "US", "ceid": "US:en"}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
        r = requests.get(base_url, headers=headers, timeout=5, params=params)
        soup = BeautifulSoup(r.content, 'xml')
        items = soup.find_all('item')[:3]
        news_data = []
        now_utc = datetime.now(timezone.utc)
        for item in items:
            title = item.find('title').text if item.find('title') else ''
            pub_date_str = item.find('pubDate').text if item.find('pubDate') else ''
            try:
                pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %Z').replace(tzinfo=timezone.utc)
                hours_ago = (now_utc - pub_date).total_seconds() / 3600
                if hours_ago < 6:
                    news_data.append({'title': title, 'hours_ago': hours_ago})
            except:
                pass
        return news_data
    except:
        return []

def analyze_news_sentiment(title, summary=""):
    text = f"{title} {summary}".lower()
    bullish_strong = ['fda approval','partnership','deal','acquisition','buyout','merger','earnings beat','upgraded','breakthrough','contract awarded','clinical success','phase 3','drill results','high-grade','discovery','resource estimate','feasibility study','permit granted','commercial production','joint venture','bought deal','flow-through','positive','upgrade','record revenue','guidance raised','beat estimates']
    bullish = ['growth','revenue','profit','gain','surge','rally','momentum','expansion','launch','agreement','assay','PEA','preliminary economic','buy rating','outperform','overweight','new contract','granted','approval','approved','commenced','completed','successful']
    bearish_strong = ['dilution','offering','bankruptcy','lawsuit','sec investigation','delisting','fda rejection','clinical failure','downgraded','private placement','unit offering','permit denied','cease trade','suspension','default','going concern','termination','insider selling','ceo departure','investigation','guidance lowered','missed estimates']
    bearish = ['loss','decline','drop','fall','warning','concern','risk','delay','delayed','suspended','halted','reduced','lowered','restructuring','layoff','impairment','write-down','debt']
    score = 0
    for word in bullish_strong:
        if word in text:
            score += 2
            break
    for word in bullish:
        if word in text:
            score += 1
            break
    for word in bearish_strong:
        if word in text:
            score -= 2
            break
    for word in bearish:
        if word in text:
            score -= 1
            break
    return score

# === MODE POST-NEWS ===
def scrape_forexfactory():
    try:
        url = "https://www.forexfactory.com/calendar"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=3)
        soup = BeautifulSoup(r.content, 'html.parser')
        news_events = []
        rows = soup.find_all('tr', class_='calendar__row')
        for row in rows:
            impact = row.find('td', class_='impact')
            currency = row.find('td', class_='currency')
            event = row.find('td', class_='event')
            time_cell = row.find('td', class_='time')
            if impact and currency and event and time_cell:
                impact_class = impact.find('span', class_='impact')
                if impact_class and 'high' in impact_class.get('class', []):
                    currency_text = currency.text.strip().upper()
                    event_text = event.text.strip()
                    time_text = time_cell.text.strip()
                    if currency_text == 'USD' and any(kw in event_text.lower() for kw in ['fomc statement','fomc press conference','cpi y/y']):
                        news_events.append({'event': event_text, 'time': time_text, 'source': 'ForexFactory'})
        print(f"📰 ForexFactory: {len(news_events)} High Impact news found")
        return news_events
    except Exception as e:
        print(f"❌ ForexFactory error: {e}")
        return None

def scrape_investing():
    try:
        url = "https://www.investing.com/economic-calendar"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=3)
        soup = BeautifulSoup(r.content, 'html.parser')
        news_events = []
        rows = soup.find_all('tr', class_='js-event-item')
        for row in rows[:30]:
            volatility = row.find_all('td')
            if len(volatility) >= 6:
                currency_text = volatility[2].text.strip().upper()
                event_text = volatility[3].text.strip()
                time_text = volatility[0].text.strip()
                volatility_icons = row.find_all('i', class_='grayFullBullishIcon')
                if volatility_icons and currency_text == 'USD':
                    if any(kw in event_text.lower() for kw in ['fomc statement','fomc press conference','cpi y/y']):
                        try:
                            gmt_time = datetime.strptime(time_text, '%H:%M')
                            gmt_time = gmt_time.replace(tzinfo=timezone.utc)
                            et_time = gmt_time.astimezone(MONTREAL_TZ)
                            time_text = et_time.strftime('%H:%M')
                        except:
                            pass
                        news_events.append({'event': event_text, 'time': time_text, 'source': 'Investing.com'})
        print(f"📰 Investing.com: {len(news_events)} High Impact news found")
        return news_events
    except Exception as e:
        print(f"❌ Investing.com error: {e}")
        return None

def is_high_impact_news(for_tomorrow=False):
    all_news = []
    ff_news = scrape_forexfactory()
    if ff_news:
        all_news.extend(ff_news)
    inv_news = scrape_investing()
    if inv_news:
        all_news.extend(inv_news)
    if not all_news:
        return False, None
    unique_news = []
    seen_events = set()
    for news in all_news:
        key = news['event'].lower().strip()
        if key not in seen_events:
            seen_events.add(key)
            unique_news.append(news)
    if for_tomorrow:
        tomorrow_news = []
        for news in unique_news:
            try:
                news_time = datetime.strptime(news['time'], '%H:%M').time()
                if news_time >= datetime.strptime('07:30', '%H:%M').time() and news_time <= datetime.strptime('11:00', '%H:%M').time():
                    tomorrow_news.append(news)
            except:
                pass
        unique_news = tomorrow_news
        if not unique_news:
            return False, None
    print(f"📰 News check: {len(unique_news)} High Impact news | POST-NEWS ACTIVE")
    for n in unique_news:
        print(f"   • {n['event']} — {n['time']} ({n['source']})")
    return True, unique_news

# ============================================================
# 🔥 SOURCES DYNAMIQUES (copiées de Core)
# ============================================================

def get_tickers_canada():
    tickers = ["TD.TO","BMO.TO","BNS.TO","NA.TO","ENB.TO","SU.TO","CNQ.TO","SOBO.TO","FTS.TO","AQN.TO","H.TO","BEP-UN.TO","SHOP.TO","LSPD.TO","OTEX.TO","SPCX.TO","CAE.TO","MDA.TO","BBD-B.TO","L.TO","MRU.TO","CCO.TO","DOL.TO","CNR.TO","CP.TO","T.TO","BCE.TO","BHC.TO","CSH-UN.TO","AND.TO","AEM.TO","ABX.TO","WPM.TO","GRDG.TO","IFC.TO","SLF.TO","GWO.TO","MG.TO","RBA.TO","TFII.TO"]
    random.shuffle(tickers)
    selected = tickers[:20]
    print(f"📊 Canada: {len(selected)} tickers (out of 40)")
    return selected

def get_dynamic_us_tickers():
    """Retourne une liste de tickers US dynamiques (top gainers, losers, most-active)"""
    tickers = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # 1. Yahoo Finance - Gainers
    try:
        url = "https://finance.yahoo.com/gainers"
        r = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(r.content, 'html.parser')
        for a in soup.find_all('a', href=re.compile(r'/quote/')):
            t = a.text.strip()
            if t and t.isalpha() and 2 <= len(t) <= 5:
                tickers.append(t.upper())
    except:
        pass
    
    # 2. Yahoo Finance - Losers
    try:
        url = "https://finance.yahoo.com/losers"
        r = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(r.content, 'html.parser')
        for a in soup.find_all('a', href=re.compile(r'/quote/')):
            t = a.text.strip()
            if t and t.isalpha() and 2 <= len(t) <= 5:
                tickers.append(t.upper())
    except:
        pass
    
    # 3. Yahoo Finance - Most Active
    try:
        url = "https://finance.yahoo.com/most-active"
        r = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(r.content, 'html.parser')
        for a in soup.find_all('a', href=re.compile(r'/quote/')):
            t = a.text.strip()
            if t and t.isalpha() and 2 <= len(t) <= 5:
                tickers.append(t.upper())
    except:
        pass
    
    # 4. Alpha Vantage - Top Gainers (démo key)
    try:
        url = "https://www.alphavantage.co/query?function=TOP_GAINERS_LOSERS&apikey=demo"
        r = requests.get(url, timeout=8)
        data = r.json()
        for item in data.get('top_gainers', [])[:30]:
            t = item.get('ticker', '')
            if t and t.isalpha() and 2 <= len(t) <= 5:
                tickers.append(t.upper())
    except:
        pass
    
    # Déduplication et limitation
    tickers = list(dict.fromkeys(tickers))[:40]
    print(f"📊 Dynamic US: {len(tickers)} tickers")
    return tickers

def get_dynamic_etfs():
    """Retourne une liste d'ETFs dynamiques (top volume) + liste fixe CA"""
    tickers = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # 1. Yahoo Finance - ETFs (top volume)
    try:
        url = "https://finance.yahoo.com/etfs"
        r = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(r.content, 'html.parser')
        for a in soup.find_all('a', href=re.compile(r'/quote/')):
            t = a.text.strip()
            if t and t.isalpha() and 2 <= len(t) <= 5:
                tickers.append(t.upper())
    except:
        pass
    
    # 2. ETFs canadiens fixes (pour garantir une couverture CA)
    ca_etfs = ["VMO.TO", "XMA.TO", "CHPS.TO", "VI.TO", "XGD.TO", "SOXU.TO", "XFN.TO", "ZUT.TO"]
    tickers.extend(ca_etfs)
    
    # Déduplication
    tickers = list(dict.fromkeys(tickers))
    
    # Séparer US et CA
    us_etfs = [t for t in tickers if not t.endswith('.TO')]
    ca_etfs_final = [t for t in tickers if t.endswith('.TO')]
    
    # Limiter à 15 US et 15 CA (garantir au moins 15 CA)
    us_etfs = us_etfs[:15]
    ca_etfs_final = ca_etfs_final[:15]
    
    # Fusionner et mélanger
    result = us_etfs + ca_etfs_final
    print(f"📊 Dynamic ETFs: {len(result)} tickers (US: {len(us_etfs)}, CA: {len(ca_etfs_final)})")
    return result

def clean_ticker(t):
    t_upper = t.upper()
    if t_upper.endswith('W') or t_upper.endswith('+') or t_upper.endswith('R'):
        return None
    if t.count('.') > 1 or '/' in t:
        return None
    if len(t) > 6:
        return None
    return t_upper

def get_all_tickers(exclude_ca=False, exclude_us=False):
    ca_clean = []
    us_clean = []

    if not exclude_ca:
        ca_tickers = get_tickers_canada()
        for t in ca_tickers:
            if t not in ca_clean:
                ca_clean.append(t)

    if not exclude_us:
        us_tickers = get_dynamic_us_tickers()
        for t in us_tickers:
            clean = clean_ticker(t)
            if clean and clean not in ca_clean and clean not in us_clean:
                us_clean.append(clean)

    result = ca_clean + us_clean[:25]
    print(f"🎯 TOTAL STOCKS: {len(result)} tickers (CA: {len(ca_clean)}, US: {min(len(us_clean), 25)})")
    return result

def get_fnb_list(exclude_ca=False, exclude_us=False):
    all_fnb = get_dynamic_etfs()
    
    if exclude_ca:
        all_fnb = [f for f in all_fnb if not f.endswith('.TO')]
    if exclude_us:
        all_fnb = [f for f in all_fnb if f.endswith('.TO')]
    
    print(f"🎯 TOTAL ETFs: {len(all_fnb)} tickers")
    return all_fnb

# === FIN DES SOURCES DYNAMIQUES ===
# ============================================================

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if len(rsi) > 0 else None

def get_stock_data(ticker, rate_limited_flag):
    now_mtl = datetime.now(MONTREAL_TZ)
    market_status = is_market_closed()
    
    if ticker not in canadian_symbols and market_status in ('closed', 'us_closed'):
        return None
    if ticker in canadian_symbols and market_status in ('closed', 'ca_closed'):
        return None
    
    try:
        stock = yf.Ticker(ticker, session=HTTP_SESSION)
        info = stock.info
        time.sleep(random.uniform(0.3, 0.5))
        if not info or (info.get('regularMarketPrice') is None and info.get('currentPrice') is None):
            if info.get('message') and 'rate' in str(info.get('message','')).lower():
                print(f"\n⚠️ RATE LIMIT detected - Pausing")
                rate_limited_flag[0] = True
                return None
        
        # Récupérer bid / ask
        bid = info.get('bid')
        ask = info.get('ask')
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        
        # Si bid/ask disponibles et différents de zéro, calculer le spread
        spread_pct = 0.0
        if bid and ask and bid > 0 and ask > 0:
            mid = (bid + ask) / 2.0
            spread_pct = ((ask - bid) / mid) * 100.0
            if spread_pct > MAX_SPREAD_PCT:
                print(f"❌ Spread trop élevé: {spread_pct:.2f}% (limite {MAX_SPREAD_PCT}%)")
                return None
            # Pour un ordre d'achat, on utilise le ask comme prix d'entrée
            if spread_pct > 0.3:
                price = ask
        
        if not price:
            return None
        
        if now_mtl.hour == 9 and now_mtl.minute < 30:
            pre_market = info.get('preMarketPrice')
            if pre_market and pre_market > 0:
                price = pre_market
        
        if not price or price < PRICE_MIN_ACTIONS or price > PRICE_MAX_ACTIONS:
            return None
        prev_close = info.get('previousClose')
        if not prev_close:
            return None
        gap = ((price - prev_close) / prev_close * 100)
        # 🔧 Utilisation de la variable GAP_MIN définie dans main (portée globale)
        GAP_MIN = get_gap_min()  # sera écrasée par la valeur calculée dans main
        if gap > 50 or gap < GAP_MIN:
            return None
        volume = info.get('volume', 0)
        is_canadian = ticker in canadian_symbols
        vol_min = 100_000 if is_canadian else 500_000
        if volume < vol_min:
            return None
        avg_volume = info.get('averageVolume', volume)
        vol_ratio = volume / avg_volume if avg_volume > 0 else 1

        # === CALCUL DU SCORE AVEC CRITÈRE N°9 ===
        score = 0
        # 1. Gap
        if 5 <= gap <= 40:
            score += 1
        # 2. Volume ratio
        if vol_ratio > 1.5:
            score += 1
        # 3. Float (avec bonus si manquant)
        float_shares = info.get('floatShares')
        if float_shares is not None:
            if float_shares < 50_000_000:
                score += 1
        else:
            score += 1  # Bonus car donnée manquante (Critère n°9)
        # 4. Bêta (avec bonus si manquant)
        beta = info.get('beta')
        if beta is not None:
            if beta > 1.0:
                score += 1
        else:
            score += 1  # Bonus car donnée manquante (Critère n°9)
        # 5. Short ratio (avec bonus si manquant)
        short_ratio = info.get('shortRatio')
        if short_ratio is not None:
            if short_ratio > 2:
                score += 1
        else:
            score += 1  # Bonus car donnée manquante (Critère n°9)
        # 6. Prix vs SMA50
        rsi_50 = info.get('fiftyDayAverage', 0)
        current_close = info.get('regularMarketPreviousClose', price)
        if rsi_50 > 0 and current_close > rsi_50:
            score += 1
        # 7. News (positive ou négative)
        news = get_news_rss(ticker)
        if news:
            for n in news[:3]:
                sentiment = analyze_news_sentiment(n.get('title',''))
                if sentiment >= 1:
                    score += 1
                    break
                elif sentiment <= -2:
                    score -= 1
                    break
        # === FIN CALCUL SCORE ===

        if score < SCORE_MIN_ACTIONS:
            return None
        exchange = get_exchange_from_info(info)
        cap_category = get_market_cap_category(ticker)
        market_bias = _get_market_bias(ticker)
        # On appelle get_trail_percent avec spread_pct, mais il sera recalculé dans le main avec confidence
        trail_percent = get_trail_percent(score, is_fnb=False, cap_category=cap_category, market_bias=market_bias, spread_pct=spread_pct)
        
        return {
            'ticker': ticker,
            'exchange': exchange,
            'price': price,
            'gap': gap,
            'score': score,
            'vol_ratio': vol_ratio,
            'trail_percent': trail_percent,
            'cap_category': cap_category,
            'market_bias': market_bias,
            'spread_pct': spread_pct
        }
    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "Too Many Requests" in err_str:
            print(f"\n⚠️ RATE LIMIT YF - Pausing")
            rate_limited_flag[0] = True
        return None

def analyze_fnb(ticker):
    now_mtl = datetime.now(MONTREAL_TZ)
    market_status = is_market_closed()
    
    if not ticker.endswith('.TO') and market_status in ('closed', 'us_closed'):
        return None
    if ticker.endswith('.TO') and market_status in ('closed', 'ca_closed'):
        return None
    
    try:
        stock = yf.Ticker(ticker, session=HTTP_SESSION)
        info = stock.info
        hist = stock.history(period="1mo")
        time.sleep(random.uniform(0.3, 0.5))
        if hist.empty or len(hist) < 2:
            return None
        closes = hist['Close']
        volumes = hist['Volume']
        price = closes.iloc[-1]
        
        # bid/ask pour ETF
        bid = info.get('bid')
        ask = info.get('ask')
        spread_pct = 0.0
        if bid and ask and bid > 0 and ask > 0:
            mid = (bid + ask) / 2.0
            spread_pct = ((ask - bid) / mid) * 100.0
            if spread_pct > MAX_SPREAD_PCT:
                print(f"❌ Spread trop élevé pour ETF: {spread_pct:.2f}% (limite {MAX_SPREAD_PCT}%)")
                return None
            if spread_pct > 0.3:
                price = ask
        
        if now_mtl.hour == 9 and now_mtl.minute < 30:
            pre_market = info.get('preMarketPrice')
            if pre_market and pre_market > 0:
                price = pre_market
        
        if not price or price < 0.5 or price > PRICE_MAX_FNB:
            return None
        prev_close = closes.iloc[-2]
        volume = volumes.iloc[-1] if len(volumes) > 0 else 0
        avg_volume = volumes.mean() if len(volumes) > 0 else volume
        if not prev_close:
            return None
        gap = ((price - prev_close) / prev_close * 100)
        # Utilisation du gap_min pour les ETFs (on utilise la même fonction)
        GAP_MIN = get_gap_min()
        # Pour les ETFs, on utilise le critère 0.5 <= gap <= 8 (pas de gap min ajusté par bias)
        # On garde cette logique.
        crit_gap = 0.5 <= gap <= 8
        vol_ratio = volume / avg_volume if avg_volume > 0 else 1
        crit_vol = vol_ratio > 0.9
        aum = info.get('totalAssets', 0) or info.get('assetsUnderManagement', 0)
        crit_aum = aum > 50_000_000 if aum else True
        rsi = None
        crit_rsi = False
        sma20 = None
        crit_sma = False
        if len(closes) > 14:
            rsi = calculate_rsi(closes)
            crit_rsi = 35 <= rsi <= 80 if rsi else False
        if len(closes) >= 20:
            sma20 = closes.rolling(20).mean().iloc[-1]
            crit_sma = price > 0.70 * sma20
        score = sum([crit_gap, crit_vol, crit_aum, crit_rsi, crit_sma])
        if score < SCORE_MIN_FNB:
            return None
        exchange = get_exchange_from_info(info)
        market_bias = _get_market_bias(ticker)
        trail_percent = get_trail_percent(score, is_fnb=True, market_bias=market_bias, spread_pct=spread_pct)
        
        return {
            'ticker': ticker,
            'exchange': exchange,
            'price': price,
            'gap': gap,
            'score': score,
            'vol_ratio': vol_ratio,
            'aum_m': aum/1_000_000 if aum else 0,
            'rsi': rsi,
            'sma20': sma20,
            'trail_percent': trail_percent,
            'market_bias': market_bias,
            'spread_pct': spread_pct
        }
    except:
        return None

def format_capital(amount):
    if amount >= 1_000_000:
        return f"{amount/1_000_000:.1f}M$"
    elif amount >= 1_000:
        return f"{amount/1_000:.0f}k$"
    else:
        return f"{amount}$"

# === FONCTION DE SAUVEGARDE INCRÉMENTALE ===
def save_pro_signal(ticker, signal_type, price, score, gap, vol_ratio, trail_percent, cap_category=None, aum_m=None, market_bias=None, spread_pct=None):
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(script_dir, 'pro_signals_today.json')
        
        today = datetime.now(MONTREAL_TZ).strftime('%Y-%m-%d')
        timestamp = datetime.now(MONTREAL_TZ).strftime('%Y-%m-%d %H:%M')
        
        signals = []
        try:
            with open(filepath, 'r') as f:
                signals = json.load(f)
                if not isinstance(signals, list):
                    signals = []
        except FileNotFoundError:
            pass
        
        new_signal = {
            "ticker": str(ticker),
            "type": str(signal_type),
            "entry_price": float(round(price, 2)),
            "score": int(score),
            "gap": float(round(gap, 1)),
            "vol_ratio": float(round(vol_ratio, 1)),
            "trail_percent": float(trail_percent),
            "timestamp": str(timestamp),
            "date": str(today)
        }
        if cap_category:
            new_signal["cap_category"] = str(cap_category)
        if aum_m is not None:
            new_signal["aum_m"] = float(round(aum_m, 1))
        if market_bias:
            new_signal["market_bias"] = str(market_bias)
        if spread_pct is not None:
            new_signal["spread_pct"] = float(round(spread_pct, 2))
        
        signals.append(new_signal)
        
        with open(filepath, 'w') as f:
            json.dump(signals, f, indent=2)
        
        print(f"💾 Signal Pro sauvegardé localement: {ticker} ({signal_type}) — Score: {score} at {timestamp}")
        push_signals_to_repo()
        return True
    except Exception as e:
        print(f"❌ Erreur sauvegarde Pro: {e}")
        return False

def should_save_signal(heure, minute):
    if heure == 10 and 0 <= minute <= 2:
        return True
    elif heure == 10 and 30 <= minute <= 32:
        return True
    elif heure == 14 and 55 <= minute <= 57:
        return True
    elif heure == 15 and 55 <= minute <= 57:
        return True
    elif os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        return True
    return False

# === MAIN ===
def main():
    START_TIME = time.time()
    now_mtl = datetime.now(MONTREAL_TZ)
    jour = now_mtl.weekday()
    heure = now_mtl.hour
    minute = now_mtl.minute
    
    market_status = is_market_closed()
    if market_status == 'closed':
        print(f"🏖️ Both markets closed (holiday) - No execution")
        return
    elif market_status == 'us_closed':
        print(f"🇺🇸 US market closed today")
    elif market_status == 'ca_closed':
        print(f"🇨🇦 CA market closed today")
    elif market_status == 'early_close':
        print(f"⏰ Early close today (1:00 PM ET)")
    
    if jour >= 5:
        print("🔧 Weekend — Manual run authorized")
    
    # === CALCUL DU BIAS GLOBAL ===
    global_bias = get_global_market_bias()
    print(f"🌍 Global Market Bias: {global_bias}")
    
    # === MODE OVERNIGHT CHECK ===
    if jour in [0,1,2,3] and heure == 15 and minute >= 55:
        tomorrow = now_mtl.date() + timedelta(days=1)
        tomorrow_dt = datetime(tomorrow.year, tomorrow.month, tomorrow.day)
        tomorrow_status = is_market_closed(tomorrow_dt)
        
        if tomorrow_status == 'closed':
            print(f"🏖️ Both markets closed tomorrow - No Overnight Check")
            return
        
        exclude_ca = (market_status == 'ca_closed') or (tomorrow_status == 'ca_closed')
        exclude_us = (market_status == 'us_closed') or (tomorrow_status == 'us_closed')
        
        if exclude_ca:
            print(f"🇨🇦 CA market closed tomorrow — scanning US only")
        elif exclude_us:
            print(f"🇺🇸 US market closed tomorrow — scanning CA only")
        
        print("=" * 50)
        print(f"🤖 NorthSentinel Pro™ — Overnight Check - {now_mtl.strftime('%Y-%m-%d %H:%M:%S')} (Montreal)")
        print("=" * 50)
        
        post_news_tomorrow, news_tomorrow = is_high_impact_news(for_tomorrow=True)
        
        # 🔧 Gap minimum avec bias
        GAP_MIN = get_gap_min(global_bias)
        
        tickers_actions = get_all_tickers(exclude_ca=exclude_ca, exclude_us=exclude_us)
        print(f"\n🔍 Phase 1: Analyzing {len(tickers_actions)} stocks for Overnight...\n")
        
        rate_limited_flag = [False]
        buys_actions = []
        analysed_actions = 0
        
        for i, ticker in enumerate(tickers_actions):
            if time.time() - START_TIME > 120:
                print(f"\n⚠️ TIMEOUT 120s - {i}/{len(tickers_actions)} stocks processed")
                break
            print(f"[STOCK {i+1}/{len(tickers_actions)}] {ticker}...", end=" ")
            data = get_stock_data(ticker, rate_limited_flag)
            analysed_actions = i + 1
            if data and data['score'] >= SCORE_MIN_OVERNIGHT_ACTIONS:
                buys_actions.append(data)
                print(f"✅ Score: {data['score']}/9")
            elif data:
                print(f"❌ Score insufficient: {data['score']}/9")
            else:
                print("❌")
            if rate_limited_flag[0]:
                print("⏸️ Rate limit pause 15s...")
                time.sleep(15)
                rate_limited_flag[0] = False
        
        tickers_fnb = get_fnb_list(exclude_ca=exclude_ca, exclude_us=exclude_us)
        print(f"\n🔍 Phase 2: Analyzing {len(tickers_fnb)} ETFs for Overnight...\n")
        
        buys_fnb = []
        analysed_fnb = 0
        
        for i, ticker in enumerate(tickers_fnb):
            if time.time() - START_TIME > 180:
                print(f"\n⚠️ TIMEOUT 180s - {i}/{len(tickers_fnb)} ETFs processed")
                break
            print(f"[ETF {i+1}/{len(tickers_fnb)}] {ticker}...", end=" ")
            data = analyze_fnb(ticker)
            analysed_fnb = i + 1
            if data and data['score'] >= SCORE_MIN_OVERNIGHT_FNB:
                buys_fnb.append(data)
                print(f"✅ Score: {data['score']}/5")
            elif data:
                print(f"❌ Score insufficient: {data['score']}/5")
            else:
                print("❌")
        
        elapsed = time.time() - START_TIME
        
        # === TELEGRAM MESSAGE - PRO OVERNIGHT (EN-TÊTE HARMONISÉ) ===
        scope_label = "US/CA"
        if exclude_ca:
            scope_label = "US Only"
        elif exclude_us:
            scope_label = "CA Only"
        
        message = f"🤖 <b>NorthSentinel Pro</b>™\n"
        message += f"<i>{scope_label} advanced intraday & overnight hold trading signals. Manual execution. Post-market recap.</i>\n"
        if exclude_ca:
            message += f"🇨🇦 CA market closed — US setups only\n"
        elif exclude_us:
            message += f"🇺🇸 US market closed — CA setups only\n"
        message += f"📅 {now_mtl.strftime('%Y-%m-%d %H:%M')} (Montreal)\n"
        message += f"💰 Capital: {format_capital(CAPITAL)} | Min Gap: {GAP_MIN}%\n"
        if market_status == 'early_close':
            message += f"⚠️ EARLY CLOSE TODAY (1:00 PM ET)\n"
        message += "═" * 35 + "\n"
        
        if post_news_tomorrow and news_tomorrow:
            message += f"\n⚠️ <b>HIGH IMPACT NEWS TOMORROW</b>\n"
            for news in news_tomorrow:
                sentiment = analyze_news_sentiment(news['event'])
                if sentiment >= 1:
                    direction = "📈"
                elif sentiment <= -1:
                    direction = "📉"
                else:
                    direction = "➡️"
                message += f"📅 {news['event']} — {news['time']} ({news['source']}) {direction}\n"
            message += f"💡 Critical window: 7:30 AM-11:00 AM (Montreal time)\n"
            message += "═" * 35 + "\n"
        
        message += f"\n🚀 <b>STOCK — Overnight Setup</b>\n"
        message += f"📊 Scanned: {analysed_actions}/{len(tickers_actions)} | Min Score: {SCORE_MIN_OVERNIGHT_ACTIONS}/9\n"
        if buys_actions:
            best_action = sorted(buys_actions, key=lambda x: (x['score'], x['vol_ratio']), reverse=True)[0]
            b = best_action
            buy_price = round(b['price'], 2)
            
            vol_profile = get_volume_profile(b['ticker'], b['price'])
            confidence = calculate_confidence_score(b, vol_profile)
            sector_context = get_macro_context(b['ticker'])
            
            spread_pct = b.get('spread_pct', 0.0)
            # --- Spread display avec montant en dollars (harmonisé avec Core) ---
            if spread_pct > 0:
                spread_usd = round((spread_pct / 100) * b['price'], 2)
                spread_display = f" | Spread: {spread_pct:.2f}% (${spread_usd:.2f})"
            else:
                spread_display = ""
            
            # Calculs bruts
            tp_mult_brut = get_tp_multiplier(b['score'], b['gap'], post_news_tomorrow, b.get('cap_category', 'Large Cap'), b.get('market_bias'), confidence['total'], spread_pct)
            sl_mult_brut = get_sl_multiplier(b['score'], b.get('cap_category', 'Large Cap'), b.get('market_bias'), confidence['total'], spread_pct)
            trail_pct_brut = get_trail_percent(b['score'], is_fnb=False, cap_category=b.get('cap_category', 'Large Cap'), market_bias=b.get('market_bias'), confidence=confidence['total'], spread_pct=spread_pct)
            
            # Application du mandat strict
            tp_mult, sl_mult, trail_pct = apply_risk_mandate(tp_mult_brut, sl_mult_brut, trail_pct_brut)
            if tp_mult is None:
                message += f"❌ No Valid Stock for Overnight (rejected: SL too tight)\n"
                message += f"⏰ Until next time!\n"
            else:
                sell_price = round(buy_price * tp_mult, 2)
                stop = round(buy_price * sl_mult, 2)
                trail_price = round(buy_price * (1 - trail_pct/100), 2)
                quantity = calculate_quantity(buy_price, stop, CAPITAL, RISK_PER_TRADE, MAX_CAPITAL_PER_POSITION)
                
                market_bias = b.get('market_bias', '⚪ Neutral (N/A)')
                cap_display = f" | {b.get('cap_category', 'N/A')}" if 'cap_category' in b else ""
                
                if confidence['total'] >= 8.5:
                    verdict_line = f"  ⚖️ <b>VERDICT: Strong setup</b> 🟢\n"
                elif confidence['total'] >= 7.5:
                    verdict_line = f"  ⚖️ <b>VERDICT: Favorable setup</b> 🟢\n"
                elif confidence['total'] >= 5.5:
                    verdict_line = f"  ⚖️ <b>VERDICT: Mixed setup</b> 🟡\n"
                elif confidence['total'] >= 3.5:
                    verdict_line = f"  ⚖️ <b>VERDICT: Weak setup</b> 🟠\n"
                else:
                    verdict_line = f"  ⚖️ <b>VERDICT: Poor setup</b> 🔴\n"
                
                message += f"\n🔹 <b>{b['ticker']}</b> ({b['exchange']}){cap_display}{spread_display} | Quality: <b>{b['score']}/9</b> | 🎯 Confidence: <b>{confidence['total']}/10</b> | {market_bias}\n"
                message += f"  📊 GAP: {b['gap']:.1f}% | VOL: x{b['vol_ratio']:.1f}\n"
                if sector_context['line']:
                    message += sector_context['line']
                message += f"  💵 CUR. PRICE: ${b['price']}\n"
                if vol_profile['line']:
                    message += vol_profile['line']
                message += verdict_line
                message += (
                    f"  🎯 ENTRY PRICE: ${buy_price}\n"
                    f"  📦 QTY TO BUY: {quantity} shares\n"
                    f"  📈 TAKE-PROFIT: ${sell_price} (+{round((tp_mult - 1) * 100, 1)}%)\n"
                    f"  🛑 STOP LOSS: ${stop} ({round((1 - sl_mult) * 100, 1)}%)\n"
                    f"  🔄 TRAILING STOP: ${trail_price} → {trail_pct}%\n"
                )
                save_pro_signal(
                    ticker=b['ticker'],
                    signal_type="STOCK",
                    price=b['price'],
                    score=b['score'],
                    gap=b['gap'],
                    vol_ratio=b['vol_ratio'],
                    trail_percent=trail_pct,
                    cap_category=b.get('cap_category', None),
                    market_bias=b.get('market_bias'),
                    spread_pct=spread_pct
                )
        else:
            message += f"❌ No Valid Stock for Overnight\n"
            message += f"⏰ Until next time!\n"
        
        message += f"\n🚀 <b>ETF — Overnight Setup</b>\n"
        message += f"📊 Scanned: {analysed_fnb}/{len(tickers_fnb)} | Min Score: {SCORE_MIN_OVERNIGHT_FNB}/5\n"
        if buys_fnb:
            best_fnb = sorted(buys_fnb, key=lambda x: (x['score'], x['vol_ratio']), reverse=True)[0]
            b = best_fnb
            buy_price = round(b['price'], 2)
            
            vol_profile_etf = get_volume_profile(b['ticker'], b['price'])
            confidence_etf = calculate_confidence_score(b, vol_profile_etf)
            sector_context_etf = get_macro_context(b['ticker'])
            
            spread_pct = b.get('spread_pct', 0.0)
            if spread_pct > 0:
                spread_usd = round((spread_pct / 100) * b['price'], 2)
                spread_display = f" | Spread: {spread_pct:.2f}% (${spread_usd:.2f})"
            else:
                spread_display = ""
            
            tp_mult_brut = get_fnb_tp_multiplier(b['score'], b['gap'], post_news_tomorrow, b.get('market_bias'), confidence_etf['total'], spread_pct)
            sl_mult_brut = get_sl_multiplier(b['score'], "Large Cap", b.get('market_bias'), confidence_etf['total'], spread_pct)
            trail_pct_brut = get_trail_percent(b['score'], is_fnb=True, market_bias=b.get('market_bias'), confidence=confidence_etf['total'], spread_pct=spread_pct)
            
            tp_mult, sl_mult, trail_pct = apply_risk_mandate(tp_mult_brut, sl_mult_brut, trail_pct_brut, max_sl=2.5, max_tp=5.0, min_sl=0.5)
            if tp_mult is None:
                message += f"❌ No Valid ETF for Overnight (rejected: SL too tight)\n"
                message += f"⏰ Until next time!\n"
            else:
                sell_price = round(buy_price * tp_mult, 2)
                stop = round(buy_price * sl_mult, 2)
                trail_price = round(buy_price * (1 - trail_pct/100), 2)
                quantity = calculate_quantity(buy_price, stop, CAPITAL, RISK_PER_TRADE, MAX_CAPITAL_PER_POSITION)
                
                market_bias = b.get('market_bias', '⚪ Neutral (N/A)')
                aum_display = f" (AUM: {b.get('aum_m', 0):.1f}M$)" if b.get('aum_m', 0) > 0 else ""
                
                if confidence_etf['total'] >= 8.5:
                    verdict_line = f"  ⚖️ <b>VERDICT: Strong setup</b> 🟢\n"
                elif confidence_etf['total'] >= 7.5:
                    verdict_line = f"  ⚖️ <b>VERDICT: Favorable setup</b> 🟢\n"
                elif confidence_etf['total'] >= 5.5:
                    verdict_line = f"  ⚖️ <b>VERDICT: Mixed setup</b> 🟡\n"
                elif confidence_etf['total'] >= 3.5:
                    verdict_line = f"  ⚖️ <b>VERDICT: Weak setup</b> 🟠\n"
                else:
                    verdict_line = f"  ⚖️ <b>VERDICT: Poor setup</b> 🔴\n"
                
                message += f"\n🔹 <b>{b['ticker']}</b> ({b['exchange']}){aum_display}{spread_display} | Quality: <b>{b['score']}/5</b> | 🎯 Confidence: <b>{confidence_etf['total']}/10</b> | {market_bias}\n"
                message += f"  📊 GAP: {b['gap']:.2f}% | VOL: x{b['vol_ratio']:.2f}\n"
                if sector_context_etf['line']:
                    message += sector_context_etf['line']
                message += f"  💵 CUR. PRICE: ${b['price']:.2f}\n"
                if vol_profile_etf['line']:
                    message += vol_profile_etf['line']
                message += verdict_line
                message += (
                    f"  🎯 ENTRY PRICE: ${buy_price}\n"
                    f"  📦 QTY TO BUY: {quantity} units\n"
                    f"  📈 TAKE-PROFIT: ${sell_price} (+{round((tp_mult - 1) * 100, 1)}%)\n"
                    f"  🛑 STOP LOSS: ${stop} ({round((1 - sl_mult) * 100, 1)}%)\n"
                    f"  🔄 TRAILING STOP: ${trail_price} → {trail_pct}%\n"
                )
                save_pro_signal(
                    ticker=b['ticker'],
                    signal_type="ETF",
                    price=b['price'],
                    score=b['score'],
                    gap=b['gap'],
                    vol_ratio=b['vol_ratio'],
                    trail_percent=trail_pct,
                    aum_m=b.get('aum_m', None),
                    market_bias=b.get('market_bias'),
                    spread_pct=spread_pct
                )
        else:
            message += f"❌ No Valid ETF for Overnight\n"
            message += f"⏰ Until next time!\n"
        
        message += "\n\n<i>Automated informational signal. Not financial or trading advice.</i>"
        print("\n" + "=" * 50)
        print(f"⏱️ Total time: {elapsed:.1f}s")
        print("📤 Sending Telegram...")
        
        # 🔧 ENVOI UNIQUEMENT AU PROPRIÉTAIRE (privé)
        send_telegram(message)
        print("=" * 50)
        return
    
    # === MODE NORMAL ===
    post_news = False
    news_info = None
    if (heure == 9 and minute >= 25) or (heure == 14 and minute >= 55):
        post_news, news_info = is_high_impact_news()
    
    current_score_min_actions = SCORE_MIN_ACTIONS
    current_score_min_fnb = SCORE_MIN_FNB
    
    exclude_ca_normal = (market_status == 'ca_closed')
    exclude_us_normal = (market_status == 'us_closed')
    
    # 🔧 Gap minimum avec bias
    GAP_MIN = get_gap_min(global_bias)
    
    print("=" * 50)
    print(f"🤖 NorthSentinel Pro™ - {now_mtl.strftime('%Y-%m-%d %H:%M:%S')} (Montreal)")
    print(f"💰 Capital: {format_capital(CAPITAL)} | Min Gap: {GAP_MIN}% ({global_bias}) | Stock Score: {current_score_min_actions}/9 | ETF: {current_score_min_fnb}/5")
    if market_status in ('us_closed', 'ca_closed'):
        if market_status == 'us_closed':
            print(f"🇺🇸 US market closed — CA only")
        else:
            print(f"🇨🇦 CA market closed — US only")
    if market_status == 'early_close':
        print(f"⏰ EARLY CLOSE 1:00 PM ET")
    print("=" * 50)
    
    tickers_actions = get_all_tickers(exclude_ca=exclude_ca_normal, exclude_us=exclude_us_normal)
    print(f"\n🔍 Phase 1: Analyzing {len(tickers_actions)} stocks...\n")
    
    rate_limited_flag = [False]
    buys_actions = []
    analysed_actions = 0
    
    for i, ticker in enumerate(tickers_actions):
        if time.time() - START_TIME > 120:
            print(f"\n⚠️ TIMEOUT 120s - {i}/{len(tickers_actions)} stocks processed")
            break
        print(f"[STOCK {i+1}/{len(tickers_actions)}] {ticker}...", end=" ")
        data = get_stock_data(ticker, rate_limited_flag)
        analysed_actions = i + 1
        if data:
            if post_news and data['score'] < current_score_min_actions:
                print("❌ (score < post-news min)")
            else:
                buys_actions.append(data)
                print(f"✅ Score: {data['score']}/9")
        else:
            print("❌")
        if rate_limited_flag[0]:
            print("⏸️ Rate limit pause 15s...")
            time.sleep(15)
            rate_limited_flag[0] = False
    
    tickers_fnb = get_fnb_list(exclude_ca=exclude_ca_normal, exclude_us=exclude_us_normal)
    print(f"\n🔍 Phase 2: Analyzing {len(tickers_fnb)} ETFs...\n")
    
    buys_fnb = []
    analysed_fnb = 0
    
    for i, ticker in enumerate(tickers_fnb):
        if time.time() - START_TIME > 180:
            print(f"\n⚠️ TIMEOUT 180s - {i}/{len(tickers_fnb)} ETFs processed")
            break
        print(f"[ETF {i+1}/{len(tickers_fnb)}] {ticker}...", end=" ")
        data = analyze_fnb(ticker)
        analysed_fnb = i + 1
        if data:
            if post_news and data['score'] < current_score_min_fnb:
                print("❌ (score < post-news min)")
            else:
                buys_fnb.append(data)
                print(f"✅ Score: {data['score']}/5")
        else:
            print("❌")
    
    elapsed = time.time() - START_TIME
    
    # === TELEGRAM MESSAGE - PRO NORMAL ===
    scope_label = "US/CA"
    if exclude_ca_normal:
        scope_label = "US Only"
    elif exclude_us_normal:
        scope_label = "CA Only"
    
    message = f"🤖 <b>NorthSentinel Pro</b>™\n"
    message += f"<i>{scope_label} advanced intraday & overnight hold trading signals. Manual execution. Post-market recap.</i>\n"
    if exclude_ca_normal:
        message += f"🇨🇦 CA market closed — US setups only\n"
    elif exclude_us_normal:
        message += f"🇺🇸 US market closed — CA setups only\n"
    message += f"📅 {now_mtl.strftime('%Y-%m-%d %H:%M')} (Montreal)\n"
    message += f"💰 Capital: {format_capital(CAPITAL)} | Min Gap: {GAP_MIN}%\n"
    if market_status == 'early_close':
        message += f"⚠️ EARLY CLOSE TODAY (1:00 PM ET)\n"
    message += "═" * 35 + "\n"
    
    if post_news and news_info:
        message += f"\n⚠️ <b>HIGH IMPACT NEWS DETECTED</b>\n"
        for news in news_info:
            sentiment = analyze_news_sentiment(news['event'])
            if sentiment >= 1:
                direction = "📈"
            elif sentiment <= -1:
                direction = "📉"
            else:
                direction = "➡️"
            message += f"📅 {news['event']} — {news['time']} ({news['source']}) {direction}\n"
        message += "═" * 35 + "\n"
    
    message += f"\n🚀 <b>STOCK</b> - Best Setup\n"
    message += f"📊 Scanned: {analysed_actions}/{len(tickers_actions)} | Min Score: {current_score_min_actions}/9\n"
    if buys_actions:
        best_action = sorted(buys_actions, key=lambda x: (x['score'], x['vol_ratio']), reverse=True)[0]
        b = best_action
        buy_price = round(b['price'], 2)
        
        vol_profile = get_volume_profile(b['ticker'], b['price'])
        confidence = calculate_confidence_score(b, vol_profile)
        sector_context = get_macro_context(b['ticker'])
        
        spread_pct = b.get('spread_pct', 0.0)
        if spread_pct > 0:
            spread_usd = round((spread_pct / 100) * b['price'], 2)
            spread_display = f" | Spread: {spread_pct:.2f}% (${spread_usd:.2f})"
        else:
            spread_display = ""
        
        tp_mult_brut = get_tp_multiplier(b['score'], b['gap'], post_news, b.get('cap_category', 'Large Cap'), b.get('market_bias'), confidence['total'], spread_pct)
        sl_mult_brut = get_sl_multiplier(b['score'], b.get('cap_category', 'Large Cap'), b.get('market_bias'), confidence['total'], spread_pct)
        trail_pct_brut = get_trail_percent(b['score'], is_fnb=False, cap_category=b.get('cap_category', 'Large Cap'), market_bias=b.get('market_bias'), confidence=confidence['total'], spread_pct=spread_pct)
        
        tp_mult, sl_mult, trail_pct = apply_risk_mandate(tp_mult_brut, sl_mult_brut, trail_pct_brut)
        if tp_mult is None:
            message += f"❌ No Valid Stock Identified (rejected: SL too tight)\n"
            message += f"⏰ Until next time!\n"
        else:
            sell_price = round(buy_price * tp_mult, 2)
            stop = round(buy_price * sl_mult, 2)
            trail_price = round(buy_price * (1 - trail_pct/100), 2)
            quantity = calculate_quantity(buy_price, stop, CAPITAL, RISK_PER_TRADE, MAX_CAPITAL_PER_POSITION)
            
            market_bias = b.get('market_bias', '⚪ Neutral (N/A)')
            cap_display = f" | {b.get('cap_category', 'N/A')}" if 'cap_category' in b else ""
            
            if confidence['total'] >= 8.5:
                verdict_line = f"  ⚖️ <b>VERDICT: Strong setup</b> 🟢\n"
            elif confidence['total'] >= 7.5:
                verdict_line = f"  ⚖️ <b>VERDICT: Favorable setup</b> 🟢\n"
            elif confidence['total'] >= 5.5:
                verdict_line = f"  ⚖️ <b>VERDICT: Mixed setup</b> 🟡\n"
            elif confidence['total'] >= 3.5:
                verdict_line = f"  ⚖️ <b>VERDICT: Weak setup</b> 🟠\n"
            else:
                verdict_line = f"  ⚖️ <b>VERDICT: Poor setup</b> 🔴\n"
            
            message += f"\n🔹 <b>{b['ticker']}</b> ({b['exchange']}){cap_display}{spread_display} | Quality: <b>{b['score']}/9</b> | 🎯 Confidence: <b>{confidence['total']}/10</b> | {market_bias}\n"
            message += f"  📊 GAP: {b['gap']:.1f}% | VOL: x{b['vol_ratio']:.1f}\n"
            if sector_context['line']:
                message += sector_context['line']
            message += f"  💵 CUR. PRICE: ${b['price']}\n"
            if vol_profile['line']:
                message += vol_profile['line']
            message += verdict_line
            message += (
                f"  🎯 ENTRY PRICE: ${buy_price}\n"
                f"  📦 QTY TO BUY: {quantity} shares\n"
                f"  📈 TAKE-PROFIT: ${sell_price} (+{round((tp_mult - 1) * 100, 1)}%)\n"
                f"  🛑 STOP LOSS: ${stop} ({round((1 - sl_mult) * 100, 1)}%)\n"
                f"  🔄 TRAILING STOP: ${trail_price} → {trail_pct}%\n"
            )
            if should_save_signal(heure, minute):
                save_pro_signal(
                    ticker=b['ticker'],
                    signal_type="STOCK",
                    price=b['price'],
                    score=b['score'],
                    gap=b['gap'],
                    vol_ratio=b['vol_ratio'],
                    trail_percent=trail_pct,
                    cap_category=b.get('cap_category', None),
                    market_bias=b.get('market_bias'),
                    spread_pct=spread_pct
                )
    else:
        message += f"❌ No Valid Stock Identified\n"
        message += f"⏰ Until next time!\n"
    
    message += f"\n🚀 <b>ETF</b> - Best Setup\n"
    message += f"📊 Scanned: {analysed_fnb}/{len(tickers_fnb)} | Min Score: {current_score_min_fnb}/5\n"
    if buys_fnb:
        best_fnb = sorted(buys_fnb, key=lambda x: (x['score'], x['vol_ratio']), reverse=True)[0]
        b = best_fnb
        buy_price = round(b['price'], 2)
        
        vol_profile_etf = get_volume_profile(b['ticker'], b['price'])
        confidence_etf = calculate_confidence_score(b, vol_profile_etf)
        sector_context_etf = get_macro_context(b['ticker'])
        
        spread_pct = b.get('spread_pct', 0.0)
        if spread_pct > 0:
            spread_usd = round((spread_pct / 100) * b['price'], 2)
            spread_display = f" | Spread: {spread_pct:.2f}% (${spread_usd:.2f})"
        else:
            spread_display = ""
        
        tp_mult_brut = get_fnb_tp_multiplier(b['score'], b['gap'], post_news, b.get('market_bias'), confidence_etf['total'], spread_pct)
        sl_mult_brut = get_sl_multiplier(b['score'], "Large Cap", b.get('market_bias'), confidence_etf['total'], spread_pct)
        trail_pct_brut = get_trail_percent(b['score'], is_fnb=True, market_bias=b.get('market_bias'), confidence=confidence_etf['total'], spread_pct=spread_pct)
        
        tp_mult, sl_mult, trail_pct = apply_risk_mandate(tp_mult_brut, sl_mult_brut, trail_pct_brut, max_sl=2.5, max_tp=5.0, min_sl=0.5)
        if tp_mult is None:
            message += f"❌ No Valid ETF Identified (rejected: SL too tight)\n"
            message += f"⏰ Until next time!\n"
        else:
            sell_price = round(buy_price * tp_mult, 2)
            stop = round(buy_price * sl_mult, 2)
            trail_price = round(buy_price * (1 - trail_pct/100), 2)
            quantity = calculate_quantity(buy_price, stop, CAPITAL, RISK_PER_TRADE, MAX_CAPITAL_PER_POSITION)
            
            market_bias = b.get('market_bias', '⚪ Neutral (N/A)')
            aum_display = f" (AUM: {b.get('aum_m', 0):.1f}M$)" if b.get('aum_m', 0) > 0 else ""
            
            if confidence_etf['total'] >= 8.5:
                verdict_line = f"  ⚖️ <b>VERDICT: Strong setup</b> 🟢\n"
            elif confidence_etf['total'] >= 7.5:
                verdict_line = f"  ⚖️ <b>VERDICT: Favorable setup</b> 🟢\n"
            elif confidence_etf['total'] >= 5.5:
                verdict_line = f"  ⚖️ <b>VERDICT: Mixed setup</b> 🟡\n"
            elif confidence_etf['total'] >= 3.5:
                verdict_line = f"  ⚖️ <b>VERDICT: Weak setup</b> 🟠\n"
            else:
                verdict_line = f"  ⚖️ <b>VERDICT: Poor setup</b> 🔴\n"
            
            message += f"\n🔹 <b>{b['ticker']}</b> ({b['exchange']}){aum_display}{spread_display} | Quality: <b>{b['score']}/5</b> | 🎯 Confidence: <b>{confidence_etf['total']}/10</b> | {market_bias}\n"
            message += f"  📊 GAP: {b['gap']:.2f}% | VOL: x{b['vol_ratio']:.2f}\n"
            if sector_context_etf['line']:
                message += sector_context_etf['line']
            message += f"  💵 CUR. PRICE: ${b['price']:.2f}\n"
            if vol_profile_etf['line']:
                message += vol_profile_etf['line']
            message += verdict_line
            message += (
                f"  🎯 ENTRY PRICE: ${buy_price}\n"
                f"  📦 QTY TO BUY: {quantity} units\n"
                f"  📈 TAKE-PROFIT: ${sell_price} (+{round((tp_mult - 1) * 100, 1)}%)\n"
                f"  🛑 STOP LOSS: ${stop} ({round((1 - sl_mult) * 100, 1)}%)\n"
                f"  🔄 TRAILING STOP: ${trail_price} → {trail_pct}%\n"
            )
            if should_save_signal(heure, minute):
                save_pro_signal(
                    ticker=b['ticker'],
                    signal_type="ETF",
                    price=b['price'],
                    score=b['score'],
                    gap=b['gap'],
                    vol_ratio=b['vol_ratio'],
                    trail_percent=trail_pct,
                    aum_m=b.get('aum_m', None),
                    market_bias=b.get('market_bias'),
                    spread_pct=spread_pct
                )
    else:
        message += f"❌ No Valid ETF Identified\n"
        message += f"⏰ Until next time!\n"
    
    message += "\n\n<i>Automated informational signal. Not financial or trading advice.</i>"
    
    print("\n" + "=" * 50)
    print(f"⏱️ Total time: {elapsed:.1f}s")
    print("📤 Sending Telegram...")
    
    # 🔧 ENVOI UNIQUEMENT AU PROPRIÉTAIRE (privé)
    send_telegram(message)
    print("=" * 50)

if __name__ == "__main__":
    main()
