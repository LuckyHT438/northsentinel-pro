# ============================================================
# NORTHSENTINEL CA ONLY — SCANNER INTRADAY CONTINU (BOUCLE)
# SHORTS + LONGS — 3 SOURCES DE NEWS
# VERSION FINALE AVEC SYNTHETIC L2 (INTERNE) + PAIRES OPPOSÉES CONDITIONNELLES
#
# HORAIRES OPTIMISÉS POUR GITHUB ACTIONS :
# AM : 09:30 → 10:30 (60 min)  → 3 scans
# PM : 14:20 → 15:00 (40 min)  → 2 scans
# Total : 100 min/jour → 2000 min/mois (dans le quota)
#
# SYNTHETIC L2 : utilisé UNIQUEMENT pour le Priority Rank et la conviction.
# Aucun affichage dans le message Telegram.
#
# PRIORITY RANK intègre un bonus/pénalité non linéaire basé sur le score L2.
# Seuils configurables via CONFIG.
#
# SÉLECTION : on cherche une paire stock/ETF de directions opposées si
# les deux setups ont un Priority Score ≥ SEUIL_PRIORITY.
# Sinon, on envoie le meilleur setup global (stock ou ETF).
#
# GESTION COMPLÈTE DES SESSIONS, FERMETURES ANTICIPÉES,
# TRAILING STOP COHÉRENT, MESSAGE DE FIN DE SESSION.
# ============================================================

import requests
import yfinance as yf
import pandas as pd
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

# ============================================================
# CONFIGURATION
# ============================================================

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

    # SYNTHETIC L2 – interne, pas affiché
    "synthetic_l2": {
        "enabled": True,
        "interval": "1m",
        "min_bars": 15,
        "lookback_bars": 30,
        "short_window": 5,
        "medium_window": 15,
        "max_candidates_stocks": 12,
        "max_candidates_etfs": 8,
        "strong_threshold": 75,
        "supportive_threshold": 60,
        "neutral_threshold": 40,
        "weak_threshold": 25,
        "bonus_strong": 3.0,
        "bonus_supportive": 1.5,
        "penalty_weak": -2.0,
        "penalty_bad": -4.0,
        "priority_threshold_for_pair": 12.0
    },

    "tickers": {
        "stocks": [
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
            "TD.TO", "CM.TO", "RY.TO",
            "ENB.TO", "ARX.TO", "VET.TO", "PPL.TO", "TRP.TO",
            "BTO.TO", "FNV.TO", "HBM.TO", "AGI.TO", "NCM.TO",
            "SHOP.TO", "KEEL.TO",
            "WN.TO", "HPS-A.TO",
            "ARTG.V", "TOI.V", "QNC.V",
            "BTE.TO", "MEG.TO", "FR.TO", "SIL.TO", "EQB.TO", "TRI.TO", "GIL.TO"
        ],
        "etfs": [
            "XFN.TO", "ZEB.TO", "XEG.TO", "ZEO.TO", "XGD.TO",
            "XMA.TO", "XIT.TO", "XST.TO", "XRE.TO", "XUT.TO",
            "ZSP.TO", "XIC.TO", "HCLN.TO", "HHIS.TO", "HXS.TO",
            "HXQ.TO", "VFV.TO", "XQQ.TO", "HHL.TO", "TXF.TO",
            "HUTL.TO", "ZDI.TO", "VI.TO", "VRE.TO", "FIE.TO",
            "ZDC.TO", "ZWA.TO",
            "XIU.TO", "ZCN.TO", "HNU.TO", "HOU.TO", "ZUB.TO",
            "ZFL.TO", "DLR.TO", "ZWB.TO", "HXT.TO",
            "XSP.TO", "XEF.TO", "XEC.TO", "ZAG.TO"
        ]
    }
}

# ============================================================
# PARAMÈTRES GLOBAUX
# ============================================================

MONTREAL_TZ = pytz.timezone("America/Toronto")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_CA_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CA_CHAT_ID")

POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
ALPHAVANTAGE_API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY")

GITHUB_EVENT = os.environ.get("GITHUB_EVENT_NAME", "")
IS_MANUAL_RUN = (GITHUB_EVENT == "workflow_dispatch") or sys.stdin.isatty()

CAPITAL = CONFIG["capital"]
RISK_PER_TRADE = CONFIG["risk_per_trade"]
MAX_CAPITAL_PER_POSITION = CONFIG["max_capital_per_position"]
MAX_SPREAD_PCT = CONFIG["max_spread_pct"]
SCORE_MIN_STOCKS = CONFIG["score_min_stocks"]
SCORE_MIN_ETFS = CONFIG["score_min_etfs"]
PRICE_MIN_STOCKS = CONFIG["price_min_stocks"]
PRICE_MAX_STOCKS = CONFIG["price_max_stocks"]
PRICE_MAX_ETFS = CONFIG["price_max_etfs"]
SCAN_INTERVAL = CONFIG["scan_interval_minutes"]
STOCK_TICKERS = CONFIG["tickers"]["stocks"]
ETF_TICKERS = CONFIG["tickers"]["etfs"]
SYNTHETIC_L2_CONFIG = CONFIG["synthetic_l2"]

RSS_FEEDS = [
    "https://www.cbc.ca/webfeed/rss/rss-business",
    "https://business.financialpost.com/feed/"
]

# ============================================================
# SESSION HTTP
# ============================================================

def create_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
        "Accept-Language": "en-US,en;q=0.9"
    })
    return session

HTTP_SESSION = create_session()

# ============================================================
# TELEGRAM
# ============================================================

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
            print(f"❌ Erreur Telegram {r.status_code}: {r.text}")
            return False
    except Exception as e:
        print(f"❌ Exception Telegram: {e}")
        return False

def send_session_end_message(now, session):
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

# ============================================================
# JOURS FÉRIÉS ET EARLY CLOSE
# ============================================================

def _adjust_weekend(d):
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d

def _build_ca_holidays(year):
    from datetime import date
    ca = set()
    ca.add(date(year, 1, 1))
    ca.add(date(year, 7, 1))
    ca.add(date(year, 12, 25))
    ca.add(date(year, 12, 26))
    fam = date(year, 2, 1)
    while fam.weekday() != 0:
        fam += timedelta(days=1)
    ca.add(fam + timedelta(days=7))
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
    vic = date(year, 5, 24)
    while vic.weekday() != 0:
        vic -= timedelta(days=1)
    ca.add(vic)
    civ = date(year, 8, 1)
    while civ.weekday() != 0:
        civ += timedelta(days=1)
    ca.add(civ)
    lab = date(year, 9, 1)
    while lab.weekday() != 0:
        lab += timedelta(days=1)
    ca.add(lab)
    thanks = date(year, 10, 1)
    while thanks.weekday() != 0:
        thanks += timedelta(days=1)
    ca.add(thanks + timedelta(days=7))
    return ca

def is_ca_market_closed(check_date):
    if isinstance(check_date, datetime):
        check_date = check_date.date()
    if check_date.weekday() >= 5:
        return True
    holidays = _build_ca_holidays(check_date.year)
    adjusted = {_adjust_weekend(d) for d in holidays}
    return check_date in adjusted

def _build_early_close_dates(year):
    from datetime import date
    return {date(year, 12, 24): 13, date(year, 12, 31): 13}

def is_early_close(check_date):
    if isinstance(check_date, datetime):
        check_date = check_date.date()
    return check_date in _build_early_close_dates(check_date.year)

def get_early_close_hour(check_date):
    if isinstance(check_date, datetime):
        check_date = check_date.date()
    return _build_early_close_dates(check_date.year).get(check_date)

# ============================================================
# NEWS
# ============================================================

def get_news_for_ticker(ticker):
    all_news = []
    ticker_clean = ticker.replace(".TO", "").replace(".V", "").upper()
    try:
        params = {"q": f"{ticker_clean}+stock", "hl": "en-CA", "gl": "CA"}
        r = requests.get("https://news.google.com/rss/search", params=params, timeout=5)
        soup = BeautifulSoup(r.content, "xml")
        for item in soup.find_all("item")[:5]:
            title = item.find("title").text if item.find("title") else ""
            pub_date_str = item.find("pubDate").text if item.find("pubDate") else ""
            try:
                pub_date = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
                hours_ago = (datetime.now(timezone.utc) - pub_date).total_seconds() / 3600
                if hours_ago < 6:
                    all_news.append({"title": title, "hours_ago": hours_ago})
            except:
                pass
    except:
        pass
    for feed_url in RSS_FEEDS:
        try:
            r = requests.get(feed_url, timeout=5)
            soup = BeautifulSoup(r.content, "xml")
            for item in soup.find_all("item")[:15]:
                title = item.find("title").text if item.find("title") else ""
                description = item.find("description").text if item.find("description") else ""
                if ticker_clean in title.upper() or ticker_clean in description.upper():
                    pub_date_str = item.find("pubDate").text if item.find("pubDate") else ""
                    try:
                        pub_date = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
                        hours_ago = (datetime.now(timezone.utc) - pub_date).total_seconds() / 3600
                        if hours_ago < 6:
                            all_news.append({"title": title, "hours_ago": hours_ago})
                    except:
                        pass
        except:
            pass
    seen = set()
    unique_news = []
    for n in all_news:
        if n["title"] not in seen:
            seen.add(n["title"])
            unique_news.append(n)
    unique_news.sort(key=lambda x: x["hours_ago"])
    return unique_news[:5]

def analyze_sentiment(title):
    text = title.lower()
    bullish_strong = ["fda approval", "partnership", "deal", "acquisition", "buyout", "merger", "earnings beat", "upgraded", "breakthrough", "contract awarded", "drill results", "high-grade", "discovery", "resource estimate", "feasibility study", "permit granted", "commercial production", "joint venture", "bought deal", "flow-through", "positive", "upgrade", "record revenue", "guidance raised"]
    bullish = ["growth", "revenue", "profit", "gain", "surge", "rally", "momentum", "expansion", "launch", "agreement", "assay", "buy rating", "outperform", "overweight", "new contract", "granted", "approved", "commenced", "completed", "successful"]
    bearish_strong = ["dilution", "offering", "bankruptcy", "lawsuit", "sec investigation", "delisting", "fda rejection", "clinical failure", "downgraded", "private placement", "unit offering", "permit denied", "cease trade", "suspension", "default", "going concern", "termination", "insider selling", "ceo departure", "investigation", "guidance lowered", "missed estimates"]
    bearish = ["loss", "decline", "drop", "fall", "warning", "concern", "risk", "delay", "delayed", "suspended", "halted", "reduced", "lowered", "restructuring", "layoff", "impairment", "write-down", "debt"]
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

# ============================================================
# VWAP / POC
# ============================================================

def get_vwap_polygon(ticker):
    if not POLYGON_API_KEY:
        return None
    try:
        clean_ticker = ticker.replace(".TO", "").replace(".V", "")
        url = f"https://api.polygon.io/v1/indicators/vwap/{clean_ticker}?timespan=minute&window=1&adjusted=true&apiKey={POLYGON_API_KEY}"
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            return None
        data = r.json()
        if "results" in data and data["results"] and "values" in data["results"]:
            return data["results"]["values"][-1]["value"]
        return None
    except:
        return None

def get_poc_alphavantage(ticker):
    if not ALPHAVANTAGE_API_KEY:
        return None
    try:
        clean_ticker = ticker.replace(".TO", "").replace(".V", "")
        url = f"https://www.alphavantage.co/query?function=OHLCV&symbol={clean_ticker}&interval=1min&apikey={ALPHAVANTAGE_API_KEY}&outputsize=compact"
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            return None
        data = r.json()
        if "Time Series (1min)" not in data:
            return None
        time_series = data["Time Series (1min)"]
        volume_by_price = {}
        for values in time_series.values():
            price = float(values["4. close"])
            volume = float(values["5. volume"])
            price_rounded = round(price, 2)
            volume_by_price[price_rounded] = volume_by_price.get(price_rounded, 0) + volume
        if not volume_by_price:
            return None
        return max(volume_by_price, key=volume_by_price.get)
    except:
        return None

def get_vwap_poc(ticker):
    vwap = get_vwap_polygon(ticker)
    poc = get_poc_alphavantage(ticker)
    return vwap, poc

# ============================================================
# SYNTHETIC L2 ENGINE (interne, pas affiché)
# ============================================================

def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))

def calculate_candle_flow(df):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    candle_range = (high - low).replace(0, pd.NA)
    clv = ((close - low) - (high - close)) / candle_range
    clv = clv.fillna(0).clip(-1, 1)
    return clv

def calculate_synthetic_l2(ticker, direction, current_price, spread_pct, vwap=None, poc=None, verbose=False):
    neutral_result = {
        "score": 50.0,
        "label": "Neutral",
        "flow": 0.0,
        "volume_acceleration": 1.0,
        "momentum_pct": 0.0,
        "persistence": 0.5,
        "vwap_alignment": 0.0,
        "poc_alignment": 0.0,
        "spread_quality": 0.5,
        "breakout_pressure": 0.0,
        "bars": 0
    }
    if not SYNTHETIC_L2_CONFIG["enabled"]:
        return neutral_result
    try:
        ticker_obj = yf.Ticker(ticker, session=HTTP_SESSION)
        hist = ticker_obj.history(period="1d", interval=SYNTHETIC_L2_CONFIG["interval"], prepost=False, auto_adjust=False)
        if hist is None or hist.empty:
            return neutral_result
        required = ["Open", "High", "Low", "Close", "Volume"]
        if not all(col in hist.columns for col in required):
            return neutral_result
        hist = hist.dropna(subset=required)
        try:
            hist = hist.between_time("09:30", "15:30")
        except:
            pass
        lookback = SYNTHETIC_L2_CONFIG["lookback_bars"]
        hist = hist.tail(lookback)
        if len(hist) < SYNTHETIC_L2_CONFIG["min_bars"]:
            return neutral_result
        close = hist["Close"].astype(float)
        volume = hist["Volume"].astype(float).fillna(0)
        clv = calculate_candle_flow(hist)
        total_volume = volume.sum()
        flow = float((clv * volume).sum() / total_volume) if total_volume > 0 else 0.0
        short_window = SYNTHETIC_L2_CONFIG["short_window"]
        medium_window = SYNTHETIC_L2_CONFIG["medium_window"]
        recent_volume = volume.tail(short_window).mean()
        previous_volume = volume.iloc[-medium_window:-short_window].mean()
        volume_acceleration = recent_volume / previous_volume if previous_volume and previous_volume > 0 else 1.0
        volume_acceleration = clamp(volume_acceleration, 0.0, 5.0)
        momentum_period = min(5, len(close) - 1)
        old_price = close.iloc[-momentum_period - 1] if len(close) > momentum_period else close.iloc[0]
        momentum_pct = ((close.iloc[-1] - old_price) / old_price) * 100 if old_price > 0 else 0.0
        recent_returns = close.pct_change().dropna().tail(8)
        if len(recent_returns) > 0:
            aligned = (recent_returns > 0).mean() if direction == "LONG" else (recent_returns < 0).mean()
            persistence = float(aligned)
        else:
            persistence = 0.5
        vwap_alignment = 0.0
        if vwap and vwap > 0:
            distance_vwap = ((current_price - vwap) / vwap) * 100
            if direction == "LONG":
                vwap_alignment = 1.0 if distance_vwap >= 0.5 else 0.5 if distance_vwap >= 0 else 0.0 if distance_vwap >= -0.5 else -1.0
            else:
                vwap_alignment = 1.0 if distance_vwap <= -0.5 else 0.5 if distance_vwap <= 0 else 0.0 if distance_vwap <= 0.5 else -1.0
        poc_alignment = 0.0
        if poc and poc > 0:
            distance_poc = ((current_price - poc) / poc) * 100
            if direction == "LONG":
                poc_alignment = 1.0 if distance_poc >= 0.5 else 0.5 if distance_poc >= 0 else 0.0 if distance_poc >= -0.5 else -1.0
            else:
                poc_alignment = 1.0 if distance_poc <= -0.5 else 0.5 if distance_poc <= 0 else 0.0 if distance_poc <= 0.5 else -1.0
        if spread_pct <= 0.10:
            spread_quality = 1.0
        elif spread_pct <= 0.25:
            spread_quality = 0.8
        elif spread_pct <= 0.50:
            spread_quality = 0.6
        elif spread_pct <= 1.00:
            spread_quality = 0.3
        else:
            spread_quality = 0.0
        recent_high = hist["High"].tail(10).max()
        recent_low = hist["Low"].tail(10).min()
        range_size = recent_high - recent_low
        position_in_range = (current_price - recent_low) / range_size if range_size > 0 else 0.5
        breakout_pressure = position_in_range if direction == "LONG" else 1.0 - position_in_range
        breakout_pressure = clamp(breakout_pressure, 0.0, 1.0)

        score = 50.0
        directional_flow = flow if direction == "LONG" else -flow
        score += clamp(directional_flow, -1, 1) * 15
        if volume_acceleration >= 2.0:
            score += 10
        elif volume_acceleration >= 1.5:
            score += 7
        elif volume_acceleration >= 1.2:
            score += 4
        elif volume_acceleration < 0.7:
            score -= 5
        directional_momentum = momentum_pct if direction == "LONG" else -momentum_pct
        if directional_momentum >= 1.0:
            score += 10
        elif directional_momentum >= 0.5:
            score += 7
        elif directional_momentum >= 0.2:
            score += 4
        elif directional_momentum < -0.5:
            score -= 10
        elif directional_momentum < -0.2:
            score -= 5
        score += (persistence - 0.5) * 20
        score += vwap_alignment * 7
        score += poc_alignment * 5
        score += spread_quality * 5
        score += breakout_pressure * 8
        score = clamp(score, 0, 100)
        label = "Strong" if score >= 75 else "Supportive" if score >= 60 else "Neutral" if score >= 40 else "Weak"
        return {
            "score": round(score, 1),
            "label": label,
            "flow": round(flow, 3),
            "volume_acceleration": round(volume_acceleration, 2),
            "momentum_pct": round(momentum_pct, 2),
            "persistence": round(persistence, 2),
            "vwap_alignment": round(vwap_alignment, 2),
            "poc_alignment": round(poc_alignment, 2),
            "spread_quality": round(spread_quality, 2),
            "breakout_pressure": round(breakout_pressure, 2),
            "bars": len(hist)
        }
    except Exception as e:
        if verbose:
            print(f"     ⚠️ Synthetic L2 indisponible: {e}")
        return neutral_result

# ============================================================
# SCORE INSTITUTIONNEL
# ============================================================

def calculate_institutional_interest(info, price, vol_ratio, gap, direction):
    score = 0
    details = {}
    held = info.get("heldPercentInstitutions", 0) or 0
    short_ratio = info.get("shortRatio", 0) or 0
    sma50 = info.get("fiftyDayAverage", 0)
    details["held"] = held
    details["short_ratio"] = short_ratio
    details["vol_ratio"] = vol_ratio
    details["sma50"] = sma50
    details["price"] = price
    details["gap"] = gap
    details["direction"] = direction
    if held >= 0.6:
        score += 2
        details["held_bonus"] = 2
    elif held >= 0.4:
        score += 1
        details["held_bonus"] = 1
    else:
        details["held_bonus"] = 0
    if short_ratio > 3 and direction == "LONG" and gap > 3:
        score += 2
        details["short_squeeze_bonus"] = 2
    else:
        details["short_squeeze_bonus"] = 0
    if vol_ratio > 2 and sma50 and price > sma50:
        score += 2
        details["volume_sma_bonus"] = 2
    elif vol_ratio > 1.5 and sma50 and price > sma50:
        score += 1
        details["volume_sma_bonus"] = 1
    else:
        details["volume_sma_bonus"] = 0
    if short_ratio > 4 and direction == "SHORT":
        score += 1
        details["short_high_bonus"] = 1
    else:
        details["short_high_bonus"] = 0
    score = min(score, 10)
    details["total"] = score
    return score, details

# ============================================================
# CONVICTION (utilise le L2 en interne)
# ============================================================

def calculate_conviction(direction, gap, vol_ratio, vwap, entry_price, inst_interest, market_bias, poc=None, synthetic_l2_score=50):
    bias = market_bias.replace("⚪ ", "").replace("🟢 ", "").replace("🔴 ", "").strip()
    green_count = 0
    if direction == "LONG":
        if gap >= 3.0 and vol_ratio >= 1.5:
            green_count += 1
        if vwap is not None and abs(entry_price - vwap) / vwap <= 0.005:
            green_count += 1
        if inst_interest >= 7:
            green_count += 1
        if poc is not None and entry_price >= poc * 0.99:
            green_count += 1
        if synthetic_l2_score >= SYNTHETIC_L2_CONFIG["strong_threshold"]:
            green_count += 1
        if green_count >= 4 and bias in ["Neutral", "Risk-on"]:
            return "High", "🟢"
        elif green_count >= 3 and bias in ["Neutral", "Risk-on"]:
            return "Moderate", "🔵"
        else:
            return "Low", "🟡"
    else:  # SHORT
        if gap <= -3.0 and vol_ratio >= 1.5:
            green_count += 1
        if vwap is not None and entry_price < vwap * 0.998:
            green_count += 1
        if inst_interest >= 7:
            green_count += 1
        if poc is not None and entry_price <= poc * 1.01:
            green_count += 1
        if synthetic_l2_score >= SYNTHETIC_L2_CONFIG["strong_threshold"]:
            green_count += 1
        if green_count >= 4 and bias in ["Neutral", "Risk-off"]:
            return "High", "🟢"
        elif green_count >= 3 and bias == "Neutral":
            return "Moderate", "🔵"
        else:
            return "Low", "🟡"

# ============================================================
# PRIORITY RANK (intègre le L2 en bonus/pénalité non linéaire)
# ============================================================

def get_verdict(confidence):
    if confidence >= 8.5:
        return "Strong", "🟢"
    elif confidence >= 7.5:
        return "Favorable", "🔵"
    else:
        return "Mixed", "🟡"

def l2_confirmation_bonus(l2_score):
    """Bonus/Pénalité non linéaire basé sur le score L2."""
    if l2_score >= SYNTHETIC_L2_CONFIG["strong_threshold"]:
        return SYNTHETIC_L2_CONFIG["bonus_strong"]          # ex: +3.0
    elif l2_score >= SYNTHETIC_L2_CONFIG["supportive_threshold"]:
        return SYNTHETIC_L2_CONFIG["bonus_supportive"]      # ex: +1.5
    elif l2_score >= SYNTHETIC_L2_CONFIG["neutral_threshold"]:
        return 0.0                                           # neutre
    elif l2_score >= SYNTHETIC_L2_CONFIG["weak_threshold"]:
        return SYNTHETIC_L2_CONFIG["penalty_weak"]          # ex: -2.0
    else:
        return SYNTHETIC_L2_CONFIG["penalty_bad"]           # ex: -4.0

def calculate_priority_score(data, market_bias, is_etf=False):
    verdict_text = get_verdict(data["confidence"])[0]
    verdict_map = {"Strong": 3, "Favorable": 2, "Mixed": 1}
    v_score = verdict_map.get(verdict_text, 1)

    l2_score = data.get("synthetic_l2_score", 50)
    conv_label, _ = calculate_conviction(
        data["direction"], data["gap"], data["vol_ratio"],
        data.get("vwap"), data["price"], data["inst_interest"],
        market_bias, data.get("poc"), l2_score
    )
    conv_map = {"High": 3, "Moderate": 2, "Low": 1}
    c_score = conv_map.get(conv_label, 1)

    max_score = 7 if not is_etf else 5
    q_score = data["score"] / max_score
    gap_score = min(abs(data["gap"]), 10.0) / 10.0

    vwap_score = 0.0
    if data.get("vwap") is not None and data["vwap"] > 0:
        diff_pct = abs(data["price"] - data["vwap"]) / data["vwap"] * 100
        vwap_score = max(0.0, 1.0 - diff_pct / 5.0)

    bias_score = 0.0
    clean_bias = market_bias.replace("⚪ ", "").replace("🟢 ", "").replace("🔴 ", "").strip()
    if data["direction"] == "LONG" and clean_bias == "Risk-on":
        bias_score = 0.5
    elif data["direction"] == "SHORT" and clean_bias == "Risk-off":
        bias_score = 0.5
    elif (data["direction"] == "LONG" and clean_bias == "Risk-off") or (data["direction"] == "SHORT" and clean_bias == "Risk-on"):
        bias_score = -0.5

    l2_component = l2_confirmation_bonus(l2_score)

    total = (v_score * 2.5) + (c_score * 2.5) + (q_score * 2.0) + (gap_score * 1.5) + (vwap_score * 1.5) + bias_score + l2_component
    return round(total, 2)

# ============================================================
# FONCTIONS D'ANALYSE (L1)
# ============================================================

def get_market_cap_category(ticker):
    try:
        info = yf.Ticker(ticker).info
        mc = info.get("marketCap", 0)
        if mc == 0:
            return "N/A"
        if mc < 300_000_000:
            return "Micro Cap"
        if mc < 2_000_000_000:
            return "Small Cap"
        if mc < 10_000_000_000:
            return "Mid Cap"
        if mc < 200_000_000_000:
            return "Large Cap"
        return "Mega Cap"
    except:
        return "N/A"

def get_exchange(info):
    ex = info.get("exchange", "")
    map_ex = {"TOR": "TMX", "TSX": "TMX", "TSXV": "TSXV", "CNQ": "CSE", "V": "TSXV"}
    return map_ex.get(ex, ex if ex else "TMX")

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
    if cap_category in ["Large Cap", "Mega Cap"]:
        conf += 0.5
    return min(round(conf, 1), 10.0)

# ============================================================
# GESTION DES RISQUES
# ============================================================

def adjust_risk_with_factors(base_tp_pct, base_sl_pct, spread_pct, vol_ratio, cap_category, gap, held_pct):
    tp_pct = base_tp_pct
    sl_pct = base_sl_pct
    trail_adj = 0.0
    if spread_pct > 0.5:
        sl_pct += 0.2
    if vol_ratio > 2.0:
        sl_pct -= 0.3
        tp_pct += 0.5
    elif vol_ratio < 0.5:
        sl_pct += 0.3
    if cap_category in ["Micro Cap", "Small Cap"]:
        sl_pct += 0.5
        tp_pct += 1.0
    elif cap_category in ["Large Cap", "Mega Cap"]:
        sl_pct -= 0.2
    if abs(gap) > 10:
        tp_pct += 0.5
    if held_pct >= 0.6:
        sl_pct -= 0.2
        tp_pct -= 0.5
        trail_adj -= 0.5
    elif held_pct <= 0.2:
        sl_pct += 0.3
        tp_pct += 1.0
        trail_adj += 1.0
    sl_pct = max(0.5, min(sl_pct, 3.0))
    tp_pct = max(0.5, min(tp_pct, 8.0))
    return round(tp_pct, 2), round(sl_pct, 2), round(trail_adj, 2)

def apply_risk_mandate(tp_pct, sl_pct, min_ratio=2.0):
    required_tp = sl_pct * min_ratio
    if tp_pct < required_tp:
        tp_pct = round(required_tp, 2)
    if sl_pct < 0.5:
        sl_pct = 0.5
    tp_pct = min(tp_pct, 8.0)
    sl_pct = min(sl_pct, 3.0)
    return round(tp_pct, 2), round(sl_pct, 2)

def compute_coherent_trailing(base_trail, trail_adj, sl_final):
    trail = base_trail + trail_adj
    trail = max(1.0, min(trail, 6.0))
    trail = min(trail, sl_final * 0.9)
    trail = max(trail, 0.3)
    return round(trail, 2)

# ============================================================
# ANALYSE STOCK (avec placeholder L2)
# ============================================================

def analyze_stock(ticker, verbose=True):
    try:
        stock = yf.Ticker(ticker, session=HTTP_SESSION)
        info = stock.info
        time.sleep(random.uniform(0.3, 0.6))
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        if not price or price < PRICE_MIN_STOCKS or price > PRICE_MAX_STOCKS:
            if verbose:
                print(f"  ❌ Prix hors limites ({price})")
            return None
        bid = info.get("bid")
        ask = info.get("ask")
        spread_pct = 0.0
        if bid and ask and bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            spread_pct = ((ask - bid) / mid) * 100
            if spread_pct > MAX_SPREAD_PCT:
                if verbose:
                    print(f"  ❌ Spread {spread_pct:.2f}% > {MAX_SPREAD_PCT}%")
                return None
        prev_close = info.get("previousClose")
        if not prev_close or prev_close == 0:
            return None
        gap = ((price - prev_close) / prev_close) * 100

        score = 0
        if 2 <= gap <= 40:
            direction = "LONG"
            score += 1
        elif -40 <= gap <= -2:
            direction = "SHORT"
            score += 1
        else:
            if verbose:
                print(f"  ❌ Gap {gap:.2f}% hors plage")
            return None
        volume = info.get("volume", 0)
        avg_vol = info.get("averageVolume", volume)
        vol_ratio = volume / avg_vol if avg_vol > 0 else 1
        if vol_ratio > 0.8:
            score += 1
        float_shares = info.get("floatShares")
        if float_shares is not None and float_shares < 100_000_000:
            score += 1
        elif float_shares is None:
            score += 1
        beta = info.get("beta")
        if beta is not None and beta > 0.8:
            score += 1
        elif beta is None:
            score += 1
        short_ratio = info.get("shortRatio")
        if short_ratio is not None and short_ratio > 1.5:
            score += 1
        elif short_ratio is None:
            score += 1
        sma50 = info.get("fiftyDayAverage")
        if sma50:
            if (direction == "LONG" and price > sma50) or (direction == "SHORT" and price < sma50):
                score += 1
        news = get_news_for_ticker(ticker)
        if news:
            for n in news[:3]:
                sent = analyze_sentiment(n["title"])
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
        if verbose:
            print(f"  📊 Score: {score}/7 | Gap: {gap:.2f}% | Vol: x{vol_ratio:.2f} | Direction: {direction}")
        if score < SCORE_MIN_STOCKS:
            return None

        inst_score, _ = calculate_institutional_interest(info, price, vol_ratio, gap, direction)
        if verbose:
            print(f"     🏛️ Inst. Interest: {inst_score}/10")

        vwap, poc = get_vwap_poc(ticker)
        if vwap is not None:
            vwap = round(vwap, 2)
        if poc is not None:
            poc = round(poc, 2)

        cap_category = get_market_cap_category(ticker)
        exchange = get_exchange(info)
        confidence = get_confidence_score(score, vol_ratio, gap, cap_category)
        held_pct = info.get("heldPercentInstitutions", 0.5) or 0.5

        if abs(gap) >= 20:
            tp_brut = 2.0 + (score - 4) * 0.6
        elif abs(gap) >= 10:
            tp_brut = 1.5 + (score - 4) * 0.4
        else:
            tp_brut = 0.5 + (score - 4) * 0.2
        sl_brut = 2.0 if score >= 6 else 2.5
        tp_adj, sl_adj, trail_adj = adjust_risk_with_factors(tp_brut, sl_brut, spread_pct, vol_ratio, cap_category, gap, held_pct)
        tp_final, sl_final = apply_risk_mandate(tp_adj, sl_adj, 2.0)
        if direction == "LONG":
            tp_mult = 1 + tp_final / 100
            sl_mult = 1 - sl_final / 100
        else:
            tp_mult = 1 - tp_final / 100
            sl_mult = 1 + sl_final / 100
        trail_base = 2.5 if score >= 8 else 3.0 if score >= 6 else 4.0
        trail = compute_coherent_trailing(trail_base, trail_adj, sl_final)

        return {
            "ticker": ticker,
            "exchange": exchange,
            "price": price,
            "gap": gap,
            "score": score,
            "vol_ratio": vol_ratio,
            "cap_category": cap_category,
            "confidence": confidence,
            "spread_pct": spread_pct,
            "direction": direction,
            "tp_mult": round(tp_mult, 3),
            "sl_mult": round(sl_mult, 3),
            "trail_pct": round(trail, 2),
            "tp_pct": round(tp_final, 2),
            "sl_pct": round(sl_final, 2),
            "inst_interest": inst_score,
            "short_ratio": short_ratio,
            "vwap": vwap,
            "poc": poc,
            "synthetic_l2_score": 50.0,
            "synthetic_l2_label": "Not evaluated"
        }
    except Exception as e:
        if verbose:
            print(f"  ❌ Exception: {e}")
        return None

# ============================================================
# ANALYSE ETF (avec placeholder L2)
# ============================================================

def analyze_etf(ticker):
    try:
        stock = yf.Ticker(ticker, session=HTTP_SESSION)
        info = stock.info
        hist = stock.history(period="1mo")
        time.sleep(random.uniform(0.3, 0.6))
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        if not price:
            if not hist.empty and len(hist) > 0:
                price = hist["Close"].iloc[-1]
            else:
                return None
        if price < PRICE_MIN_STOCKS or price > PRICE_MAX_ETFS:
            return None
        bid = info.get("bid")
        ask = info.get("ask")
        spread_pct = 0.0
        if bid and ask and bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            spread_pct = ((ask - bid) / mid) * 100
            if spread_pct > MAX_SPREAD_PCT:
                return None
        if hist.empty or len(hist) < 2:
            return None
        closes = hist["Close"]
        volumes = hist["Volume"]
        prev_close = closes.iloc[-2]
        if not prev_close:
            return None
        gap = ((price - prev_close) / prev_close) * 100
        volume = info.get("volume", 0)
        avg_vol = volumes.mean() if len(volumes) > 0 else volume
        vol_ratio = volume / avg_vol if avg_vol > 0 else 1
        aum = info.get("totalAssets", 0) or info.get("assetsUnderManagement", 0)

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
        inst_score, _ = calculate_institutional_interest(info, price, vol_ratio, gap, direction)
        vwap, poc = get_vwap_poc(ticker)
        if vwap is not None:
            vwap = round(vwap, 2)
        if poc is not None:
            poc = round(poc, 2)
        short_ratio = info.get("shortRatio", None)

        if abs(gap) >= 6:
            tp_brut = 1.5 + (score - 3) * 0.5
        elif abs(gap) >= 3:
            tp_brut = 1.0 + (score - 3) * 0.5
        else:
            tp_brut = 0.5 + (score - 3) * 0.5
        sl_brut = 2.0
        held_pct = info.get("heldPercentInstitutions", 0.5) or 0.5
        tp_adj, sl_adj, trail_adj = adjust_risk_with_factors(tp_brut, sl_brut, spread_pct, vol_ratio, "Large Cap", gap, held_pct)
        tp_final, sl_final = apply_risk_mandate(tp_adj, sl_adj, 2.0)
        if direction == "LONG":
            tp_mult = 1 + tp_final / 100
            sl_mult = 1 - sl_final / 100
        else:
            tp_mult = 1 - tp_final / 100
            sl_mult = 1 + sl_final / 100
        trail = compute_coherent_trailing(3.0, trail_adj, sl_final)

        return {
            "ticker": ticker,
            "exchange": exchange,
            "price": price,
            "gap": gap,
            "score": score,
            "vol_ratio": vol_ratio,
            "aum_m": round(aum / 1_000_000, 1) if aum else 0,
            "confidence": confidence,
            "spread_pct": spread_pct,
            "direction": direction,
            "tp_mult": round(tp_mult, 3),
            "sl_mult": round(sl_mult, 3),
            "trail_pct": round(trail, 2),
            "tp_pct": round(tp_final, 2),
            "sl_pct": round(sl_final, 2),
            "inst_interest": inst_score,
            "short_ratio": short_ratio,
            "vwap": vwap,
            "poc": poc,
            "synthetic_l2_score": 50.0,
            "synthetic_l2_label": "Not evaluated"
        }
    except Exception:
        return None

# ============================================================
# ENRICHISSEMENT SYNTHETIC L2 (calculé uniquement sur les meilleurs)
# ============================================================

def enrich_with_synthetic_l2(results, is_etf=False):
    if not results:
        return results
    max_candidates = SYNTHETIC_L2_CONFIG["max_candidates_etfs"] if is_etf else SYNTHETIC_L2_CONFIG["max_candidates_stocks"]
    candidates = sorted(
        results,
        key=lambda x: (x["score"], x["vol_ratio"], abs(x["gap"])),
        reverse=True
    )[:max_candidates]
    candidate_symbols = {x["ticker"] for x in candidates}
    for data in results:
        if data["ticker"] not in candidate_symbols:
            data["synthetic_l2_score"] = 50.0
            data["synthetic_l2_label"] = "Not evaluated"
            continue
        l2 = calculate_synthetic_l2(
            ticker=data["ticker"],
            direction=data["direction"],
            current_price=data["price"],
            spread_pct=data["spread_pct"],
            vwap=data.get("vwap"),
            poc=data.get("poc"),
            verbose=True
        )
        data["synthetic_l2_score"] = l2["score"]
        data["synthetic_l2_label"] = l2["label"]
    return results

# ============================================================
# QUANTITÉ ET FORMATAGE
# ============================================================

def calculate_quantity(entry, stop, capital, risk_pct, max_cap_pct):
    risk_amount = capital * risk_pct
    max_exposure = capital * max_cap_pct
    stop_dist = abs(entry - stop)
    if stop_dist <= 0:
        return 0
    qty_risk = int(risk_amount / stop_dist)
    qty_cap = int(max_exposure / entry)
    return max(0, min(qty_risk, qty_cap))

def format_price(p):
    return f"{p:.2f}"

def build_setup_message(data, is_etf=False, bias="⚪ Neutral", rank="1/1"):
    max_score = 7 if not is_etf else 5
    entry = data["price"]
    direction = data["direction"]
    tp_pct = data.get("tp_pct", 0.0)
    sl_pct = data.get("sl_pct", 0.0)
    trail_pct = data.get("trail_pct", 0.0)

    if direction == "LONG":
        tp = round(entry * (1 + tp_pct / 100), 2)
        sl = round(entry * (1 - sl_pct / 100), 2)
        trail_price = round(entry * (1 - trail_pct / 100), 2)
        gain_display = f"+{tp_pct:.1f}%"
        loss_display = f"-{sl_pct:.1f}%"
    else:
        tp = round(entry * (1 - tp_pct / 100), 2)
        sl = round(entry * (1 + sl_pct / 100), 2)
        trail_price = round(entry * (1 + trail_pct / 100), 2)
        gain_display = f"-{tp_pct:.1f}%"
        loss_display = f"+{sl_pct:.1f}%"

    qty = calculate_quantity(entry, sl, CAPITAL, RISK_PER_TRADE, MAX_CAPITAL_PER_POSITION)

    spread_display = ""
    if data["spread_pct"] > 0:
        spread_usd = round((data["spread_pct"] / 100) * entry, 2)
        spread_display = f" | Spread: {data['spread_pct']:.2f}% (${spread_usd:.2f})"

    verdict_text, verdict_emoji = get_verdict(data["confidence"])
    direction_emoji = "📈 LONG" if direction == "LONG" else "📉 SHORT"
    gap_display = f"+{data['gap']:.2f}%" if data["gap"] >= 0 else f"{data['gap']:.2f}%"

    inst = data.get("inst_interest", 0)
    inst_label = "High" if inst >= 7 else "Moderate" if inst >= 4 else "Low"

    vwap_display = f"${data['vwap']:.2f}" if data.get("vwap") is not None else "N/A"
    poc_display = f"${data['poc']:.2f}" if data.get("poc") is not None else "N/A"
    cap_display = data["cap_category"] if not is_etf and "cap_category" in data else ""
    short_ratio = data.get("short_ratio")
    short_display = f"{short_ratio:.1f}" if short_ratio is not None else "N/A"

    l2_score = data.get("synthetic_l2_score", 50)
    conv_label, conv_emoji = calculate_conviction(
        direction, data["gap"], data["vol_ratio"], data.get("vwap"), entry, inst,
        bias, data.get("poc"), l2_score
    )

    msg = f"🔹 <b>{data['ticker']}</b> ({data['exchange']}){spread_display}\n"
    msg += f"   Direction: <b>{direction_emoji}</b>\n"
    msg += f"   Quality: <b>{data['score']}/{max_score}</b> | Confidence: <b>{data['confidence']}/10</b>\n"
    msg += f"   GAP: {gap_display} | Volume: x{data['vol_ratio']:.2f} | Short ratio: {short_display}\n"
    msg += f"   VWAP: {vwap_display} | POC: {poc_display}"
    if is_etf:
        msg += f" | AUM: {data.get('aum_m', 0):.1f}M$"
    if cap_display:
        msg += f" | Cap: {cap_display}"
    msg += "\n"
    msg += f"   Market Bias: {bias}\n"
    msg += f"   🏛️ Institutional Interest: {inst}/10 ({inst_label})\n"
    msg += f"   ⚖️ VERDICT: {verdict_emoji} {verdict_text} | Conviction: {conv_emoji} {conv_label} | Rank: {rank}\n"
    msg += f"   🎯 ENTRY: ${format_price(entry)}\n"
    msg += f"   📦 QUANTITY: {qty} {'shares' if not is_etf else 'units'}\n"
    msg += f"   📈 TAKE-PROFIT: ${format_price(tp)} ({gain_display})\n"
    msg += f"   🛑 STOP LOSS: ${format_price(sl)} ({loss_display})\n"
    msg += f"   🔄 TRAILING STOP: ${format_price(trail_price)} → {trail_pct:.1f}%\n"
    if tp_pct > 0 and sl_pct > 0:
        rr = tp_pct / sl_pct
        msg += f"   📊 R/R: {tp_pct:.1f} / {sl_pct:.1f} = {rr:.1f}:1\n"
    else:
        msg += "   📊 R/R: N/A\n"
    return msg

# ============================================================
# ATTENTE
# ============================================================

def wait_until_target(target_hour, target_minute):
    now = datetime.now(MONTREAL_TZ)
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(minutes=SCAN_INTERVAL)
    diff = (target - now).total_seconds()
    if diff > 0:
        print(f"⏳ Attente jusqu'à {target.strftime('%H:%M')}... ({diff/60:.1f} min)")
        time.sleep(diff)

# ============================================================
# MAIN
# ============================================================

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
                "⏰ Manual run triggered on a closed market day.\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "<i>Informational automated signal. Not financial or trading advice.</i>"
            )
            send_telegram(msg)
        return

    early_close = is_early_close(now)
    early_hour = get_early_close_hour(now) if early_close else None
    if early_close:
        print(f"⚠️ Fermeture anticipée – Marché ferme à {early_hour}:00 ET.")

    # =========================================================
    # HORAIRES OPTIMISÉS POUR GITHUB ACTIONS
    # AM : 09:30 → 10:30 (60 min)  → 3 scans
    # PM : 14:30 → 15:00 (30 min)  → 2 scans
    # Total : 90 min/jour → 1800 min/mois (sous le quota)
    # =========================================================
    if 9 <= heure <= 10 and (heure < 10 or minute <= 30):
        session = "morning"
        start_hour, start_min = 9, 30
        end_hour, end_min = 10, 30
        print("☀️ Session MATIN (09:30-10:30) détectée.")
    elif 14 <= heure <= 15 and (heure == 14 and minute >= 30 or heure == 15 and minute == 0):
        session = "afternoon"
        start_hour, start_min = 14, 30
        end_hour, end_min = 15, 0
        print("🌙 Session APRÈS-MIDI (14:30-15:00) détectée.")
    else:
        print("⏰ Hors des plages horaires (AM: 09:30-10:30, PM: 14:30-15:00) – Arrêt.")
        if IS_MANUAL_RUN:
            msg = (
                "🤖 <b>NorthSentinel CA Only</b>™\n"
                "<i>Canadian intraday trading signals. Long & Short. Manual execution.</i>\n"
                f"<i>📅 {now.strftime('%Y-%m-%d %H:%M')} (Montreal)</i>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "⏰ Manual run triggered outside trading hours.\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "<i>Informational automated signal. Not financial or trading advice.</i>"
            )
            send_telegram(msg)
        return

    now = datetime.now(MONTREAL_TZ)
    if now.hour < start_hour or (now.hour == start_hour and now.minute < start_min):
        wait_until_target(start_hour, start_min)

    while True:
        now = datetime.now(MONTREAL_TZ)

        # Fin de session
        if now.hour > end_hour or (now.hour == end_hour and now.minute > end_min):
            print(f"⏹️ Fin de session ({end_hour:02d}:{end_min:02d}) – Arrêt.")
            send_session_end_message(now, session)
            break

        current_hour, current_min = now.hour, now.minute

        if current_min % SCAN_INTERVAL == 0:
            print(f"\n📊 Scan à {now.strftime('%H:%M')} (session {session})")

            # Stocks
            stocks_results = []
            for ticker in STOCK_TICKERS:
                print(f"  - {ticker}:")
                data = analyze_stock(ticker, verbose=True)
                if data:
                    stocks_results.append(data)
                    print(f"    ✅ Score {data['score']}/7 | {data['direction']} | TP: {data['tp_pct']}% | SL: {data['sl_pct']}%")
                else:
                    print("    ❌")

            # ETFs
            etfs_results = []
            for ticker in ETF_TICKERS:
                print(f"  - {ticker}...", end=" ")
                data = analyze_etf(ticker)
                if data:
                    etfs_results.append(data)
                    print(f"✅ Score {data['score']}/5 | {data['direction']} | TP: {data['tp_pct']}% | SL: {data['sl_pct']}%")
                else:
                    print("❌")

            # SYNTHETIC L2 – calcul sur les meilleurs candidats seulement
            print("\n🧠 ================================")
            print("🧠 SYNTHETIC L2 — STOCKS")
            print("🧠 ================================")
            stocks_results = enrich_with_synthetic_l2(stocks_results, is_etf=False)
            print("\n🧠 ================================")
            print("🧠 SYNTHETIC L2 — ETFs")
            print("🧠 ================================")
            etfs_results = enrich_with_synthetic_l2(etfs_results, is_etf=True)

            # ---- SÉLECTION AVEC PAIRES OPPOSÉES CONDITIONNELLES ----
            stock_long = [s for s in stocks_results if s["direction"] == "LONG"]
            stock_short = [s for s in stocks_results if s["direction"] == "SHORT"]
            etf_long = [e for e in etfs_results if e["direction"] == "LONG"]
            etf_short = [e for e in etfs_results if e["direction"] == "SHORT"]

            def get_best(candidates, is_etf):
                if not candidates:
                    return None
                scored = []
                for cand in candidates:
                    ps = calculate_priority_score(cand, "⚪ Neutral", is_etf)
                    scored.append((ps, cand))
                scored.sort(key=lambda x: x[0], reverse=True)
                return scored[0][1]

            best_stock_long = get_best(stock_long, False)
            best_stock_short = get_best(stock_short, False)
            best_etf_long = get_best(etf_long, True)
            best_etf_short = get_best(etf_short, True)

            possible_pairs = []
            threshold = SYNTHETIC_L2_CONFIG["priority_threshold_for_pair"]

            # Paire 1 : stock LONG + ETF SHORT
            if best_stock_long and best_etf_short:
                score_stock = calculate_priority_score(best_stock_long, "⚪ Neutral", False)
                score_etf = calculate_priority_score(best_etf_short, "⚪ Neutral", True)
                if score_stock >= threshold and score_etf >= threshold:
                    possible_pairs.append((best_stock_long, best_etf_short, score_stock + score_etf))

            # Paire 2 : stock SHORT + ETF LONG
            if best_stock_short and best_etf_long:
                score_stock = calculate_priority_score(best_stock_short, "⚪ Neutral", False)
                score_etf = calculate_priority_score(best_etf_long, "⚪ Neutral", True)
                if score_stock >= threshold and score_etf >= threshold:
                    possible_pairs.append((best_stock_short, best_etf_long, score_stock + score_etf))

            selected_stock = None
            selected_etf = None

            if possible_pairs:
                best_pair = max(possible_pairs, key=lambda x: x[2])
                selected_stock, selected_etf = best_pair[0], best_pair[1]
            else:
                all_stocks = [s for s in stocks_results]
                all_etfs = [e for e in etfs_results]
                selected_stock = get_best(all_stocks, False)
                selected_etf = get_best(all_etfs, True)

            # Construction du message (structure inchangée)
            msg = "🤖 <b>NorthSentinel CA Only</b>™\n"
            msg += "<i>Canadian intraday trading signals. Long & Short. Manual execution.</i>\n"
            msg += f"📅 {now.strftime('%Y-%m-%d %H:%M')} (Montreal) | Scanned: {len(STOCK_TICKERS)} Stocks, {len(ETF_TICKERS)} ETFs\n"
            msg += f"Capital: ${CAPITAL:,.0f} (Paper Trading Account)\n"
            msg += "═══════════════════════════════════\n"

            msg += "\n🚀 <b>BEST STOCK SETUP</b>\n"
            if selected_stock:
                rank = "1/2" if selected_etf else "1/1"
                msg += build_setup_message(selected_stock, is_etf=False, bias="⚪ Neutral", rank=rank)
            else:
                msg += "   <i>Aucun setup STOCK valide trouvé.</i>\n"

            msg += "\n🚀 <b>BEST ETF SETUP</b>\n"
            if selected_etf:
                rank = "2/2" if selected_stock else "1/1"
                msg += build_setup_message(selected_etf, is_etf=True, bias="⚪ Neutral", rank=rank)
            else:
                msg += "   <i>Aucun setup ETF valide trouvé.</i>\n"

            msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            msg += "<i>Informational automated signal. Not financial or trading advice.</i>"
            send_telegram(msg)

        # Prochaine cible
        next_min = ((current_min // SCAN_INTERVAL) + 1) * SCAN_INTERVAL
        next_hour = current_hour
        if next_min >= 60:
            next_min = 0
            next_hour += 1

        # Arrêt immédiat si la prochaine cible est après la fin
        if next_hour > end_hour or (next_hour == end_hour and next_min > end_min):
            print("⏹️ Prochaine cible après la fin de session – Arrêt.")
            send_session_end_message(now, session)
            break

        wait_until_target(next_hour, next_min)

if __name__ == "__main__":
    main()
