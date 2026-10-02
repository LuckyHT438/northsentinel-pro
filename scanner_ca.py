# ============================================================
# NORTHSENTINEL CA ONLY — SCANNER INTRADAY CONTINU (BOUCLE)
# SHORTS + LONGS — 3 SOURCES DE NEWS
# VERSION TP UNIQUE ANCRÉ STRUCTURELLEMENT
#
# 2 CRONS EXTERNES :
#   - AM : déclenché à 09:30 ET → scans 09:45, 10:30, 11:15
#   - PM : déclenché à 14:00 ET → scans 14:00, 15:00
#
# SYNTHETIC L2 : utilisé pour la confirmation / Priority Rank / conviction.
# Aucun affichage dans le message Telegram.
#
# >>> TP UNIQUE STRUCTUREL (2026-10-02) <<<
# Le TP est désormais TOUJOURS ancré sur un niveau de marché réel.
#   - L'ATR quotidien fournit une distance de référence
#   - Le script cherche un niveau structurel dans la fenêtre
#     [0.7 × ATR_ref, 1.5 × ATR_ref]
#   - Contrainte de R/R minimum (du régime) appliquée
#   - Si aucun niveau valide → REJET du setup (plus de fallback arbitraire)
#   - Le message affiche la source du TP entre crochets : [VWAP], [ORB-H], etc.
#
# >>> DÉTECTION DE RÉGIME DE MARCHÉ <<<
# >>> CORRECTIFS ASYMÉTRIQUES SHORT <<<
# >>> AMÉLIORATIONS #2 / #7 <<<
# >>> FERMETURE IMMÉDIATE APRÈS LE DERNIER SCAN <<<
# >>> HEARTBEAT ANTI-TIMEOUT <<<
# >>> GARDE-FOUS DIRECTIONNELS (DÉSACTIVÉS PAR DÉFAUT) <<<
# ============================================================

import requests
import yfinance as yf
import pandas as pd
import time
import random
import os
import sys
import re
import logging
import warnings
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import pytz
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore")

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
    "scan_interval_minutes": 60,

    "position_management": {
        "qty1_pct": 100.0,
        "qty2_pct": 0.0,
        "ibkr_pricing_model": "tiered",
        "ibkr_tiered_commission_per_share": 0.008,
        "ibkr_fixed_commission_per_share": 0.010,
        "ibkr_min_commission_per_order": 1.00,
        "ibkr_clearing_per_share": 0.00017,
        "ibkr_clearing_cap_per_order": 2.00,
        "ibkr_regulatory_per_share": 0.00011,
        "ibkr_regulatory_cap_per_order": 3.30,
        "fee_safety_buffer_per_order": 1.00,
        "fee_safe_trailing": True
    },

    "technical_structure": {
        "enabled": True,
        "intraday_period": "5d",
        "intraday_interval": "5m",
        "lookback_bars": 48,
        "swing_window": 3,
        "structure_buffer_atr": 0.35,
        "min_sl_atr": 0.70,
        "max_sl_atr": 3.00,
        "min_sl_pct": 0.50,
        "max_sl_pct": 3.00,
        "breakout_tolerance_pct": 0.35,
        "support_resistance_tolerance_pct": 0.50,
        "reject_if_structure_unavailable": True,
        "require_room_to_tp": True
    },

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

    "direction_control": {
        "enable_longs": True,
        "enable_shorts": True,
    },

    "short_adjustment": {
        "sl_widening_pct": 0.4,
        "trail_widening_pct": 0.2,
        "gap_min_short": -2.5,
        "vol_ratio_min_short": 0.9,
        "etf_gap_min_short": -0.75,
        "price_max_short_stock": 999.0,
        "price_max_short_etf": 999.0,
    },

    "regime": {
        "enabled": True,
        "benchmark_ticker": "^GSPTSE",
        "lookback_period": "6mo",
        "adx_period": 14,
        "atr_period": 14,
        "atr_percentile_window": 60,
        "trend_adx_threshold": 20,
        "high_vol_atr_percentile": 75,
        "low_vol_atr_percentile": 25,
        "counter_trend_gap_penalty": 0.5,
        "choppy_score_penalty": 1,
        "sl_mult_high_vol": 1.25,
        "sl_mult_low_vol": 0.90,
        "tp_mult_ranging": 0.90,
        "min_rr_by_regime": {
            "Trending-Up": 1.6,
            "Trending-Down": 1.6,
            "Ranging": 2.0,
            "Choppy-Volatile": 2.5,
            "Unknown": 2.0
        },
        "min_rr_default": 2.0
    },

    "intraday_filters": {
        "timing_penalty_windows": [
            {"start_min": 570, "end_min": 585, "penalty": 1},   # 09:30–09:45
        ],

        "rvol_enabled": True,
        "rvol_strong_threshold": 2.0,
        "rvol_moderate_threshold": 1.2,
        "rvol_weak_threshold": 0.8,
        "rvol_reject_below": 0.5,
        "rvol_bonus_strong": 1.5,
        "rvol_bonus_moderate": 0.5,
        "rvol_penalty_weak": -1.0,
        "rvol_apply_reject_after_min": 585,

        "structural_tp_enabled": True,
        "structural_tp_atr_lower_mult": 0.7,
        "structural_tp_atr_upper_mult": 1.5,
    },

    "tickers": {
        "stocks": [
            "MFC.TO", "GWO.TO", "POW.TO", "SU.TO", "CNQ.TO",
            "WCP.TO", "CCO.TO", "ATH.TO", "ABX.TO", "K.TO",
            "LUN.TO", "FM.TO", "T.TO", "BCE.TO", "RCI-B.TO",
            "BB.TO", "LSPD.TO", "AC.TO", "CAE.TO",
            "BNS.TO",
            "ATZ.TO", "GRGD.TO", "SPCX.TO", "ATD.TO",
            "MRU.TO", "L.TO", "EMP-A.TO", "CP.TO", "CNR.TO",
            "TFII.TO", "MDA.TO", "BBD-B.TO", "CGO.TO", "QBR-B.TO",
            "IFC.TO", "SLF.TO", "RBA.TO",
            "NA.TO",
            "WELL.TO",
            "GIB-A.TO", "OTEX.TO", "DSG.TO", "CS.TO",
            "KTN.V",
            "AEM.TO", "WPM.TO", "EQX.TO", "LUG.TO", "FSV.TO",
            "BEP-UN.TO", "BAM.TO", "BN.TO", "NTR.TO",
            "TD.TO", "CM.TO", "AQN.TO",
            "ENB.TO", "ARX.TO", "VET.TO", "BB.TO", "TCW.TO",
            "BTO.TO", "IVN.TO", "HBM.TO", "AGI.TO", "NCM.TO",
            "SHOP.TO", "KEEL.TO",
            "WN.TO", "HPS-A.TO",
            "ARTG.V", "TOI.V", "ZDC.V", "QNC.V",
            "BTE.TO", "FR.TO", "SIL.TO", "EQB.TO", "TRI.TO", "GIL.TO"
        ],
        "etfs": [
            "XFN.TO", "ZEB.TO", "XEG.TO", "ZEO.TO", "XGD.TO",
            "XMA.TO", "XIT.TO", "XST.TO", "XRE.TO", "XUT.TO",
            "ZSP.TO", "XIC.TO", "HCLN.TO", "HHIS.TO", "HXS.TO",
            "HXQ.TO", "VFV.TO", "XQQ.TO", "HHL.TO", "TXF.TO",
            "HUTL.TO", "ZDI.TO", "VI.TO", "VRE.TO", "FIE.TO",
            "FBTC.TO", "ZWA.TO",
            "XIU.TO", "ZCN.TO", "HNU.TO", "HOU.TO", "ZUB.TO",
            "ZFL.TO", "DLR.TO", "ZWB.TO", "HXT.TO",
            "BTCC.TO", "XEF.TO", "XEC.TO", "ZAG.TO"
        ]
    }
}

MONTREAL_TZ = pytz.timezone("America/Toronto")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_CA_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CA_CHAT_ID")

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

POSITION_CONFIG = CONFIG["position_management"]
QTY1_PCT = float(POSITION_CONFIG["qty1_pct"])
QTY2_PCT = float(POSITION_CONFIG["qty2_pct"])
IBKR_PRICING_MODEL = POSITION_CONFIG["ibkr_pricing_model"].lower()
IBKR_TIERED_COMMISSION = float(POSITION_CONFIG["ibkr_tiered_commission_per_share"])
IBKR_FIXED_COMMISSION = float(POSITION_CONFIG["ibkr_fixed_commission_per_share"])
IBKR_MIN_COMMISSION = float(POSITION_CONFIG["ibkr_min_commission_per_order"])
IBKR_CLEARING_PER_SHARE = float(POSITION_CONFIG["ibkr_clearing_per_share"])
IBKR_CLEARING_CAP = float(POSITION_CONFIG["ibkr_clearing_cap_per_order"])
IBKR_REGULATORY_PER_SHARE = float(POSITION_CONFIG["ibkr_regulatory_per_share"])
IBKR_REGULATORY_CAP = float(POSITION_CONFIG["ibkr_regulatory_cap_per_order"])
IBKR_FEE_BUFFER = float(POSITION_CONFIG["fee_safety_buffer_per_order"])
FEE_SAFE_TRAILING = bool(POSITION_CONFIG["fee_safe_trailing"])
TECH_STRUCTURE_CONFIG = CONFIG["technical_structure"]

if QTY1_PCT <= 0 or QTY2_PCT < 0 or abs((QTY1_PCT + QTY2_PCT) - 100.0) > 1e-9:
    raise ValueError("position_management.qty1_pct + qty2_pct doit être égal à 100%.")
if IBKR_PRICING_MODEL not in {"tiered", "fixed"}:
    raise ValueError("ibkr_pricing_model doit être 'tiered' ou 'fixed'.")
STOCK_TICKERS = CONFIG["tickers"]["stocks"]
ETF_TICKERS = CONFIG["tickers"]["etfs"]
SYNTHETIC_L2_CONFIG = CONFIG["synthetic_l2"]
REGIME_CONFIG = CONFIG["regime"]
INTRADAY_FILTERS = CONFIG["intraday_filters"]
DIRECTION_CONTROL = CONFIG["direction_control"]

SHORT_ADJ = CONFIG["short_adjustment"]
SHORT_SL_WIDENING = SHORT_ADJ["sl_widening_pct"]
SHORT_TRAIL_WIDENING = SHORT_ADJ["trail_widening_pct"]
SHORT_GAP_MIN = SHORT_ADJ["gap_min_short"]
SHORT_VOL_MIN = SHORT_ADJ["vol_ratio_min_short"]
SHORT_ETF_GAP_MIN = SHORT_ADJ["etf_gap_min_short"]
SHORT_PRICE_MAX_STOCK = SHORT_ADJ.get("price_max_short_stock", 999.0)
SHORT_PRICE_MAX_ETF = SHORT_ADJ.get("price_max_short_etf", 999.0)

_TP_SOURCE_ABBR = {
    "VWAP": "VWAP",
    "POC": "POC",
    "ORB-High": "ORB-H",
    "ORB-Low": "ORB-L",
    "PriorHigh": "PDH",
    "PriorLow": "PDL",
    "SwingHigh": "SwH",
    "SwingLow": "SwL",
    "Structure": "Struct",
    "Round0.10": "R0.10",
    "Round0.25": "R0.25",
    "Round0.50": "R0.50",
    "Round1.00": "R1.00",
    "Round5.00": "R5.00",
    "Round10.00": "R10.00",
}

RSS_FEEDS = [
    "https://www.cbc.ca/webfeed/rss/rss-business",
    "https://business.financialpost.com/feed/"
]

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

def send_telegram(message):
    if not TELEGRAM_TOKEN:
        print("⚠️ Token Telegram manquant", flush=True)
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("✅ Telegram envoyé", flush=True)
            return True
        else:
            print(f"❌ Erreur Telegram {r.status_code}: {r.text}", flush=True)
            return False
    except Exception as e:
        print(f"❌ Exception Telegram: {e}", flush=True)
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

from pro_volume_profile import get_volume_profile

def get_vwap_poc(ticker, current_price, direction="LONG"):
    profile = get_volume_profile(ticker, current_price, direction)
    return profile.get("vwap"), profile.get("poc")

def calculate_adx_atr(df, period=14):
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr.replace(0, pd.NA))
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr.replace(0, pd.NA))

    di_sum = (plus_di + minus_di).replace(0, pd.NA)
    dx = 100 * (plus_di - minus_di).abs() / di_sum
    adx = dx.rolling(period).mean()

    adx_val = adx.dropna().iloc[-1] if len(adx.dropna()) > 0 else None
    atr_val = atr.dropna().iloc[-1] if len(atr.dropna()) > 0 else None
    return adx_val, atr_val

def _default_regime():
    return {
        "regime": "Unknown",
        "bias": "⚪ Neutral",
        "volatility": "Normal",
        "adx": None,
        "atr_pct": None,
        "atr_percentile": None,
        "trend_direction": "Flat",
        "score_min_stock_adj": 0,
        "score_min_etf_adj": 0,
        "gap_min_long_adj": 0.0,
        "gap_min_short_adj": 0.0,
        "sl_mult_adj": 1.0,
        "tp_mult_adj": 1.0
    }

def detect_market_regime(verbose=True):
    default = _default_regime()
    if not REGIME_CONFIG.get("enabled", True):
        return default
    try:
        idx = yf.Ticker(REGIME_CONFIG["benchmark_ticker"], session=HTTP_SESSION)
        hist = idx.history(period=REGIME_CONFIG["lookback_period"], interval="1d")
        if hist is None or hist.empty or len(hist) < 30:
            if verbose:
                print("⚠️ Régime: historique indice insuffisant, fallback Neutral.", flush=True)
            return default

        close = hist["Close"].astype(float)
        adx, atr = calculate_adx_atr(hist, REGIME_CONFIG["adx_period"])

        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean() if len(close) >= 50 else None
        current_price = close.iloc[-1]

        atr_pct_series = ((hist["High"] - hist["Low"]).rolling(REGIME_CONFIG["atr_period"]).mean() / close) * 100
        atr_pct_series = atr_pct_series.dropna()
        current_atr_pct = atr_pct_series.iloc[-1] if len(atr_pct_series) > 0 else None
        atr_percentile = None
        if current_atr_pct is not None and len(atr_pct_series) >= REGIME_CONFIG["atr_percentile_window"]:
            window = atr_pct_series.tail(REGIME_CONFIG["atr_percentile_window"])
            atr_percentile = float((window < current_atr_pct).mean() * 100)

        trend_direction = "Flat"
        if sma50 is not None and not sma50.isna().iloc[-1] and not sma20.isna().iloc[-1]:
            if current_price > sma20.iloc[-1] > sma50.iloc[-1]:
                trend_direction = "Up"
            elif current_price < sma20.iloc[-1] < sma50.iloc[-1]:
                trend_direction = "Down"

        if atr_percentile is not None:
            if atr_percentile >= REGIME_CONFIG["high_vol_atr_percentile"]:
                volatility = "High"
            elif atr_percentile <= REGIME_CONFIG["low_vol_atr_percentile"]:
                volatility = "Low"
            else:
                volatility = "Normal"
        else:
            volatility = "Normal"

        is_trending = adx is not None and adx >= REGIME_CONFIG["trend_adx_threshold"]
        if is_trending and trend_direction == "Up":
            regime = "Trending-Up"
            bias = "🟢 Risk-on"
        elif is_trending and trend_direction == "Down":
            regime = "Trending-Down"
            bias = "🔴 Risk-off"
        elif volatility == "High":
            regime = "Choppy-Volatile"
            bias = "⚪ Neutral"
        else:
            regime = "Ranging"
            bias = "⚪ Neutral"

        gap_penalty = REGIME_CONFIG["counter_trend_gap_penalty"]
        score_min_stock_adj = 0
        score_min_etf_adj = 0
        gap_min_long_adj = 0.0
        gap_min_short_adj = 0.0
        sl_mult_adj = 1.0
        tp_mult_adj = 1.0

        if regime == "Trending-Up":
            gap_min_short_adj = gap_penalty
        elif regime == "Trending-Down":
            gap_min_long_adj = gap_penalty
        elif regime == "Choppy-Volatile":
            score_min_stock_adj = REGIME_CONFIG["choppy_score_penalty"]
            score_min_etf_adj = REGIME_CONFIG["choppy_score_penalty"]
        elif regime == "Ranging":
            tp_mult_adj = REGIME_CONFIG["tp_mult_ranging"]

        if volatility == "High":
            sl_mult_adj = max(sl_mult_adj, REGIME_CONFIG["sl_mult_high_vol"])
        elif volatility == "Low":
            sl_mult_adj = min(sl_mult_adj, REGIME_CONFIG["sl_mult_low_vol"])

        result = {
            "regime": regime,
            "bias": bias,
            "volatility": volatility,
            "adx": round(float(adx), 1) if adx is not None else None,
            "atr_pct": round(float(current_atr_pct), 2) if current_atr_pct is not None else None,
            "atr_percentile": round(atr_percentile, 0) if atr_percentile is not None else None,
            "trend_direction": trend_direction,
            "score_min_stock_adj": score_min_stock_adj,
            "score_min_etf_adj": score_min_etf_adj,
            "gap_min_long_adj": gap_min_long_adj,
            "gap_min_short_adj": gap_min_short_adj,
            "sl_mult_adj": round(sl_mult_adj, 2),
            "tp_mult_adj": round(tp_mult_adj, 2)
        }
        if verbose:
            print(
                f"🧭 RÉGIME: {result['regime']} | Bias: {result['bias']} | "
                f"Vol: {result['volatility']} | ADX: {result['adx']} | "
                f"ATR%: {result['atr_pct']} (percentile: {result['atr_percentile']})",
                flush=True
            )
        return result
    except Exception as e:
        if verbose:
            print(f"⚠️ Régime indisponible, fallback Neutral: {e}", flush=True)
        return default

def get_timing_penalty():
    now = datetime.now(MONTREAL_TZ)
    total = now.hour * 60 + now.minute
    penalty = 0
    for w in INTRADAY_FILTERS.get("timing_penalty_windows", []):
        if w["start_min"] <= total < w["end_min"]:
            penalty += w["penalty"]
    return penalty

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
        "score": 50.0, "label": "Neutral", "flow": 0.0,
        "volume_acceleration": 1.0, "momentum_pct": 0.0,
        "persistence": 0.5, "vwap_alignment": 0.0,
        "poc_alignment": 0.0, "spread_quality": 0.5,
        "breakout_pressure": 0.0, "bars": 0
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
        hist = hist.tail(SYNTHETIC_L2_CONFIG["lookback_bars"])
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
            "score": round(score, 1), "label": label,
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
            print(f"     ⚠️ Synthetic L2 indisponible: {e}", flush=True)
        return neutral_result

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
    else:
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

def get_verdict(confidence):
    if confidence >= 8.5:
        return "Strong", "🟢"
    elif confidence >= 7.5:
        return "Favorable", "🔵"
    else:
        return "Mixed", "🟡"

def l2_confirmation_bonus(l2_score):
    if l2_score >= SYNTHETIC_L2_CONFIG["strong_threshold"]:
        return SYNTHETIC_L2_CONFIG["bonus_strong"]
    elif l2_score >= SYNTHETIC_L2_CONFIG["supportive_threshold"]:
        return SYNTHETIC_L2_CONFIG["bonus_supportive"]
    elif l2_score >= SYNTHETIC_L2_CONFIG["neutral_threshold"]:
        return 0.0
    elif l2_score >= SYNTHETIC_L2_CONFIG["weak_threshold"]:
        return SYNTHETIC_L2_CONFIG["penalty_weak"]
    else:
        return SYNTHETIC_L2_CONFIG["penalty_bad"]

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

    rvol = data.get("rvol_intraday")
    rvol_adj = 0.0
    if rvol is not None and INTRADAY_FILTERS.get("rvol_enabled", True):
        if rvol >= INTRADAY_FILTERS["rvol_strong_threshold"]:
            rvol_adj = INTRADAY_FILTERS["rvol_bonus_strong"]
        elif rvol >= INTRADAY_FILTERS["rvol_moderate_threshold"]:
            rvol_adj = INTRADAY_FILTERS["rvol_bonus_moderate"]
        elif rvol < INTRADAY_FILTERS["rvol_weak_threshold"]:
            rvol_adj = INTRADAY_FILTERS["rvol_penalty_weak"]

    total += rvol_adj
    return round(total, 2)

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

def calculate_atr_pct_from_ohlc(high, low, close, period=14):
    try:
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_series = tr.rolling(period).mean().dropna()
        if len(atr_series) == 0:
            return None
        last_close = close.iloc[-1]
        if not last_close or last_close <= 0:
            return None
        return float(atr_series.iloc[-1] / last_close * 100)
    except Exception:
        return None

def _prior_day_hl_from_daily(hist):
    if hist is None or len(hist) < 2:
        return None, None
    try:
        today = datetime.now(MONTREAL_TZ).date()
        last_bar_date = hist.index[-1].date() if hasattr(hist.index[-1], "date") else None
        idx = -2 if last_bar_date == today else -1
        if abs(idx) > len(hist):
            return None, None
        return float(hist["High"].iloc[idx]), float(hist["Low"].iloc[idx])
    except Exception:
        return None, None

def get_daily_context(ticker, period=14, verbose=False):
    try:
        hist = yf.Ticker(ticker, session=HTTP_SESSION).history(period="2mo", interval="1d")
        if hist is None or hist.empty or len(hist) < period + 1:
            return None
        atr_pct = calculate_atr_pct_from_ohlc(
            hist["High"].astype(float), hist["Low"].astype(float), hist["Close"].astype(float), period
        )
        prior_high, prior_low = _prior_day_hl_from_daily(hist)
        return {"atr_pct": atr_pct, "prior_high": prior_high, "prior_low": prior_low}
    except Exception as e:
        if verbose:
            print(f"     ⚠️ Contexte daily indisponible pour {ticker}: {e}", flush=True)
        return None

def estimate_tp_pct_from_atr(atr_pct, gap, score, tp_mult_adj):
    if atr_pct is None or atr_pct <= 0:
        return None
    if abs(gap) >= 20:
        k_gap = 2.2
    elif abs(gap) >= 10:
        k_gap = 1.6
    else:
        k_gap = 1.1
    quality_adj = clamp(1 + 0.05 * (score - 4), 0.7, 1.3)
    return atr_pct * k_gap * quality_adj * tp_mult_adj

def estimate_tp_pct_fallback(gap, score, tp_mult_adj):
    if abs(gap) >= 20:
        tp_brut = 2.0 + (score - 4) * 0.6
    elif abs(gap) >= 10:
        tp_brut = 1.5 + (score - 4) * 0.4
    else:
        tp_brut = 0.5 + (score - 4) * 0.2
    return tp_brut * tp_mult_adj

def get_min_rr_for_regime(regime):
    regime_name = regime.get("regime", "Unknown")
    table = REGIME_CONFIG.get("min_rr_by_regime", {})
    return table.get(regime_name, REGIME_CONFIG.get("min_rr_default", 2.0))

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

def compute_coherent_trailing(base_trail, trail_adj, sl_final):
    trail = base_trail + trail_adj
    trail = max(1.0, min(trail, 6.0))
    trail = min(trail, sl_final * 0.9)
    trail = max(trail, 0.3)
    return round(trail, 2)

def fetch_intraday_structure(ticker, period=None, interval=None):
    if not TECH_STRUCTURE_CONFIG.get("enabled", True):
        return None
    try:
        period = period or TECH_STRUCTURE_CONFIG["intraday_period"]
        interval = interval or TECH_STRUCTURE_CONFIG["intraday_interval"]
        hist = yf.Ticker(ticker, session=HTTP_SESSION).history(
            period=period, interval=interval, prepost=False, auto_adjust=False
        )
        if hist is None or hist.empty:
            return None
        required = ["Open", "High", "Low", "Close", "Volume"]
        if not all(c in hist.columns for c in required):
            return None
        hist = hist.dropna(subset=required).copy()
        if hist.empty:
            return None
        try:
            hist = hist.between_time("09:30", "16:00")
        except Exception:
            pass
        return hist.tail(TECH_STRUCTURE_CONFIG["lookback_bars"])
    except Exception:
        return None

def _intraday_atr(hist, period=14):
    if hist is None or len(hist) < period + 1:
        return None
    try:
        h = hist["High"].astype(float)
        l = hist["Low"].astype(float)
        c = hist["Close"].astype(float)
        tr = pd.concat([(h-l), (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().dropna()
        return float(atr.iloc[-1]) if len(atr) else None
    except Exception:
        return None

def detect_setup_structure(hist, price, direction, gap, vwap=None, poc=None):
    if hist is None or len(hist) < 10 or price <= 0:
        return None
    look = hist.tail(TECH_STRUCTURE_CONFIG.get("lookback_bars", 48))
    high_n = float(look["High"].tail(20).max())
    low_n = float(look["Low"].tail(20).min())
    high_10 = float(look["High"].tail(10).max())
    low_10 = float(look["Low"].tail(10).min())
    recent_high = float(look["High"].tail(6).max())
    recent_low = float(look["Low"].tail(6).min())
    atr = _intraday_atr(look)
    if atr is None or atr <= 0:
        return None

    tol = TECH_STRUCTURE_CONFIG.get("breakout_tolerance_pct", 0.35) / 100.0
    sr_tol = TECH_STRUCTURE_CONFIG.get("support_resistance_tolerance_pct", 0.50) / 100.0

    if direction == "LONG":
        if price >= high_10 * (1 - tol):
            setup_type = "BREAKOUT"
            structure = min(high_10, recent_low if recent_low < price else high_10)
            invalidation = recent_low
        elif vwap and price >= vwap and abs(price-vwap)/price <= sr_tol:
            setup_type = "PULLBACK / CONTINUATION"
            invalidation = recent_low
            structure = vwap
        elif poc and price >= poc and abs(price-poc)/price <= sr_tol:
            setup_type = "SUPPORT / CONTINUATION"
            invalidation = recent_low
            structure = poc
        else:
            setup_type = "GAP CONTINUATION"
            invalidation = recent_low
            structure = low_n
        return {
            "setup_type": setup_type,
            "structure_level": float(structure),
            "invalidation_level": float(invalidation),
            "recent_high": high_n,
            "recent_low": low_n,
            "atr": atr,
        }
    else:
        if price <= low_10 * (1 + tol):
            setup_type = "BREAKDOWN"
            structure = max(low_10, recent_high if recent_high > price else low_10)
            invalidation = recent_high
        elif vwap and price <= vwap and abs(price-vwap)/price <= sr_tol:
            setup_type = "PULLBACK / CONTINUATION"
            invalidation = recent_high
            structure = vwap
        elif poc and price <= poc and abs(price-poc)/price <= sr_tol:
            setup_type = "RESISTANCE / CONTINUATION"
            invalidation = recent_high
            structure = poc
        else:
            setup_type = "GAP CONTINUATION"
            invalidation = recent_high
            structure = high_n
        return {
            "setup_type": setup_type,
            "structure_level": float(structure),
            "invalidation_level": float(invalidation),
            "recent_high": high_n,
            "recent_low": low_n,
            "atr": atr,
        }

def calculate_structural_sl(entry, direction, structure):
    if not structure or entry <= 0:
        return None
    invalidation = structure.get("invalidation_level")
    atr = structure.get("atr")
    if invalidation is None or atr is None or atr <= 0:
        return None
    buffer = atr * float(TECH_STRUCTURE_CONFIG.get("structure_buffer_atr", 0.35))
    if direction == "LONG":
        stop = float(invalidation) - buffer
        if stop <= 0 or stop >= entry:
            return None
    else:
        stop = float(invalidation) + buffer
        if stop <= entry:
            return None
    sl_dist = abs(entry-stop)
    sl_pct = sl_dist / entry * 100.0
    sl_atr = sl_dist / atr if atr > 0 else None
    return {
        "sl_price": round(stop, 4),
        "sl_pct": sl_pct,
        "sl_atr": sl_atr,
        "buffer": buffer,
    }

def validate_sl_bounds_only(structural_sl):
    if not structural_sl:
        return None
    sl_pct = float(structural_sl["sl_pct"])
    sl_atr = structural_sl.get("sl_atr")
    min_sl = float(TECH_STRUCTURE_CONFIG.get("min_sl_pct", 0.50))
    max_sl = float(TECH_STRUCTURE_CONFIG.get("max_sl_pct", 3.00))
    min_atr = float(TECH_STRUCTURE_CONFIG.get("min_sl_atr", 0.70))
    max_atr = float(TECH_STRUCTURE_CONFIG.get("max_sl_atr", 3.00))
    if sl_pct < min_sl or sl_pct > max_sl:
        return None
    if sl_atr is not None and (sl_atr < min_atr or sl_atr > max_atr):
        return None
    return round(sl_pct, 2)

def _build_tp_candidates(entry, direction, vwap, poc, structure_hist,
                         structure, daily_ctx):
    candidates = []

    if vwap and vwap > 0:
        candidates.append((float(vwap), "VWAP"))
    if poc and poc > 0:
        candidates.append((float(poc), "POC"))

    if daily_ctx:
        if daily_ctx.get("prior_high"):
            candidates.append((float(daily_ctx["prior_high"]), "PriorHigh"))
        if daily_ctx.get("prior_low"):
            candidates.append((float(daily_ctx["prior_low"]), "PriorLow"))

    if structure_hist is not None and len(structure_hist) >= 6:
        try:
            orb = structure_hist.head(6)
            candidates.append((float(orb["High"].max()), "ORB-High"))
            candidates.append((float(orb["Low"].min()), "ORB-Low"))
        except Exception:
            pass

    if structure:
        for key, label in (("recent_high", "SwingHigh"),
                           ("recent_low", "SwingLow"),
                           ("structure_level", "Structure")):
            v = structure.get(key)
            if v:
                candidates.append((float(v), label))

    for delta in (0.10, 0.25, 0.50, 1.00, 5.00, 10.00):
        if direction == "LONG":
            c = round(entry / delta) * delta
            if c <= entry:
                c += delta
        else:
            c = round(entry / delta) * delta
            if c >= entry:
                c -= delta
        if c > 0:
            candidates.append((float(c), f"Round{delta}"))

    return candidates

def compute_structural_tp(entry, sl_price, direction, atr_tp_pct, candidates,
                          min_rr, lower_mult=0.7, upper_mult=1.5, verbose=False):
    if atr_tp_pct is None or atr_tp_pct <= 0 or entry <= 0 or sl_price <= 0:
        return None, None
    if not candidates:
        return None, None

    sl_pct = abs(entry - sl_price) / entry * 100
    if sl_pct <= 0:
        return None, None

    ref_lo = atr_tp_pct * lower_mult
    ref_hi = atr_tp_pct * upper_mult
    min_dist_pct = sl_pct * min_rr
    max_dist_pct = 8.0

    valid = []
    for price, label in candidates:
        if price is None or price <= 0:
            continue
        if direction == "LONG":
            if price <= entry:
                continue
            dist_pct = (price - entry) / entry * 100
        else:
            if price >= entry:
                continue
            dist_pct = (entry - price) / entry * 100

        if dist_pct < min_dist_pct:
            continue
        if dist_pct > max_dist_pct:
            continue
        if not (ref_lo <= dist_pct <= ref_hi):
            continue

        valid.append((price, label, dist_pct))

    if not valid:
        if verbose:
            print(f"     ❌ Aucun TP structurel dans [{ref_lo:.2f}%, {ref_hi:.2f}%] "
                  f"avec R/R ≥ {min_rr:.1f}:1 (SL {sl_pct:.2f}%)", flush=True)
        return None, None

    valid.sort(key=lambda x: abs(x[2] - atr_tp_pct))
    best_price, best_label, best_dist = valid[0]
    return round(best_dist, 2), best_label

def calculate_intraday_rvol_from_hist(hist):
    if hist is None or hist.empty or not isinstance(hist.index, pd.DatetimeIndex):
        return None
    try:
        h = hist.copy()
        try:
            h = h.between_time("09:30", "16:00")
        except Exception:
            pass
        if h.empty:
            return None
        h["date"] = h.index.date
        dates = sorted(h["date"].unique())
        if len(dates) < 2:
            return None

        today = dates[-1]
        today_bars = h[h["date"] == today]
        if today_bars.empty:
            return None

        cutoff = today_bars.index[-1].time()
        today_vol = float(today_bars["Volume"].sum())

        prior_vols = []
        for d in dates[:-1]:
            day_bars = h[h["date"] == d]
            before = day_bars[day_bars.index.time <= cutoff]
            if not before.empty:
                prior_vols.append(float(before["Volume"].sum()))

        if len(prior_vols) < 2:
            return None
        avg_prior = sum(prior_vols) / len(prior_vols)
        if avg_prior <= 0:
            return None
        return today_vol / avg_prior
    except Exception:
        return None

def analyze_stock(ticker, regime=None, verbose=True):
    if regime is None:
        regime = _default_regime()
    try:
        stock = yf.Ticker(ticker, session=HTTP_SESSION)
        info = stock.info
        time.sleep(random.uniform(0.3, 0.6))
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        if not price or price < PRICE_MIN_STOCKS or price > PRICE_MAX_STOCKS:
            if verbose:
                print(f"  ❌ Prix hors limites ({price})", flush=True)
            return None
        bid = info.get("bid")
        ask = info.get("ask")
        spread_pct = 0.0
        if bid and ask and bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            spread_pct = ((ask - bid) / mid) * 100
            if spread_pct > MAX_SPREAD_PCT:
                if verbose:
                    print(f"  ❌ Spread {spread_pct:.2f}% > {MAX_SPREAD_PCT}%", flush=True)
                return None
        prev_close = info.get("previousClose")
        if not prev_close or prev_close == 0:
            return None
        gap = ((price - prev_close) / prev_close) * 100

        gap_min_long = 2 + regime.get("gap_min_long_adj", 0.0)
        gap_max_short = SHORT_GAP_MIN - regime.get("gap_min_short_adj", 0.0)

        score = 0
        if gap_min_long <= gap <= 40:
            direction = "LONG"
            score += 1
        elif -40 <= gap <= gap_max_short:
            direction = "SHORT"
            score += 1
        else:
            if verbose:
                print(f"  ❌ Gap {gap:.2f}% hors plage (régime: {regime.get('regime')})", flush=True)
            return None

        if direction == "LONG" and not DIRECTION_CONTROL.get("enable_longs", True):
            if verbose:
                print("  ❌ LONG désactivé via direction_control", flush=True)
            return None
        if direction == "SHORT" and not DIRECTION_CONTROL.get("enable_shorts", True):
            if verbose:
                print("  ❌ SHORT désactivé via direction_control", flush=True)
            return None
        if direction == "SHORT" and price > SHORT_PRICE_MAX_STOCK:
            if verbose:
                print(f"  ❌ SHORT: prix {price:.2f}$ > {SHORT_PRICE_MAX_STOCK:.0f}$ (limite absolue)", flush=True)
            return None

        volume = info.get("volume", 0)
        avg_vol = info.get("averageVolume", volume)
        vol_ratio = volume / avg_vol if avg_vol > 0 else 1

        vol_threshold = SHORT_VOL_MIN if direction == "SHORT" else 0.8
        if vol_ratio > vol_threshold:
            score += 1
        else:
            if verbose and direction == "SHORT":
                print(f"  ❌ SHORT: vol_ratio {vol_ratio:.2f} < {SHORT_VOL_MIN}", flush=True)
            return None if direction == "SHORT" else None

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

        structure_hist = fetch_intraday_structure(ticker)
        rvol = calculate_intraday_rvol_from_hist(structure_hist) \
               if INTRADAY_FILTERS.get("rvol_enabled", True) else None

        now_min = datetime.now(MONTREAL_TZ).hour * 60 + datetime.now(MONTREAL_TZ).minute
        if rvol is not None and now_min >= INTRADAY_FILTERS.get("rvol_apply_reject_after_min", 585):
            if rvol < INTRADAY_FILTERS.get("rvol_reject_below", 0.5):
                if verbose:
                    print(f"  ❌ RVOL intraday x{rvol:.2f} trop faible — rejet", flush=True)
                return None

        if verbose:
            rvol_display = f"x{rvol:.2f}" if rvol is not None else "N/A"
            print(f"  📊 Score: {score}/7 | Gap: {gap:.2f}% | Vol: x{vol_ratio:.2f} | RVOL: {rvol_display} | Direction: {direction}", flush=True)

        timing_pen = get_timing_penalty()
        effective_score_min = min(7, SCORE_MIN_STOCKS + regime.get("score_min_stock_adj", 0) + timing_pen)
        if score < effective_score_min:
            return None

        inst_score, _ = calculate_institutional_interest(info, price, vol_ratio, gap, direction)
        if verbose:
            print(f"     🏛️ Inst. Interest: {inst_score}/10", flush=True)

        vwap, poc = get_vwap_poc(ticker, price, direction)
        if vwap is not None:
            vwap = round(vwap, 2)
        if poc is not None:
            poc = round(poc, 2)

        cap_category = get_market_cap_category(ticker)
        exchange = get_exchange(info)
        confidence = get_confidence_score(score, vol_ratio, gap, cap_category)
        held_pct = info.get("heldPercentInstitutions", 0.5) or 0.5

        daily_ctx = get_daily_context(ticker, verbose=verbose)
        atr_pct = daily_ctx.get("atr_pct") if daily_ctx else None

        tp_ref = estimate_tp_pct_from_atr(atr_pct, gap, score, regime.get("tp_mult_adj", 1.0))
        if tp_ref is None:
            tp_ref = estimate_tp_pct_fallback(gap, score, regime.get("tp_mult_adj", 1.0))
            if verbose:
                print(f"     ⚠️ ATR indisponible — référence de distance via gap/score", flush=True)

        structure = detect_setup_structure(structure_hist, price, direction, gap, vwap, poc)
        structural_sl = calculate_structural_sl(price, direction, structure)
        if structural_sl is None:
            if verbose:
                print("     ❌ SL structurel indisponible/invalide", flush=True)
            return None

        tp_ref_adj, _, trail_adj = adjust_risk_with_factors(
            tp_ref, structural_sl["sl_pct"], spread_pct, vol_ratio, cap_category, gap, held_pct
        )
        if direction == "SHORT":
            trail_adj += SHORT_TRAIL_WIDENING

        sl_final = validate_sl_bounds_only(structural_sl)
        if sl_final is None:
            if verbose:
                print(
                    f"     ❌ SL structurel hors bornes : {structural_sl['sl_pct']:.2f}% "
                    f"({structural_sl.get('sl_atr', 0):.2f} ATR)", flush=True
                )
            return None

        min_rr = get_min_rr_for_regime(regime)
        tp_candidates = _build_tp_candidates(
            entry=price, direction=direction,
            vwap=vwap, poc=poc,
            structure_hist=structure_hist,
            structure=structure,
            daily_ctx=daily_ctx,
        )
        tp_final, tp_source_label = compute_structural_tp(
            entry=price,
            sl_price=structural_sl["sl_price"],
            direction=direction,
            atr_tp_pct=tp_ref_adj,
            candidates=tp_candidates,
            min_rr=min_rr,
            lower_mult=INTRADAY_FILTERS.get("structural_tp_atr_lower_mult", 0.7),
            upper_mult=INTRADAY_FILTERS.get("structural_tp_atr_upper_mult", 1.5),
            verbose=verbose,
        )
        if tp_final is None:
            if verbose:
                print("     ❌ Setup rejeté : aucun TP structurel valide", flush=True)
            return None

        if tp_final <= 0 or sl_final <= 0 or tp_final / sl_final < min_rr:
            if verbose:
                print(
                    f"     ❌ R/R final {tp_final/sl_final:.2f}:1 < min {min_rr:.1f}:1",
                    flush=True
                )
            return None

        if direction == "LONG":
            tp_mult = 1 + tp_final / 100
            sl_mult = 1 - sl_final / 100
        else:
            tp_mult = 1 - tp_final / 100
            sl_mult = 1 + sl_final / 100
        trail_base = 2.5 if score >= 8 else 3.0 if score >= 6 else 4.0
        trail = compute_coherent_trailing(trail_base, trail_adj, sl_final)

        if verbose:
            print(
                f"     🎯 TP structurel : {tp_final:.2f}% [{tp_source_label}] "
                f"| SL : {sl_final:.2f}% | R/R : {tp_final/sl_final:.2f}:1",
                flush=True
            )

        return {
            "ticker": ticker, "exchange": exchange, "price": price, "gap": gap,
            "score": score, "vol_ratio": vol_ratio, "cap_category": cap_category,
            "confidence": confidence, "spread_pct": spread_pct, "direction": direction,
            "tp_mult": round(tp_mult, 3), "sl_mult": round(sl_mult, 3),
            "trail_pct": round(trail, 2), "tp_pct": round(tp_final, 2),
            "sl_pct": round(sl_final, 2), "inst_interest": inst_score,
            "short_ratio": short_ratio, "vwap": vwap, "poc": poc,
            "synthetic_l2_score": 50.0, "synthetic_l2_label": "Not evaluated",
            "atr_pct": round(atr_pct, 2) if atr_pct is not None else None,
            "rvol_intraday": round(rvol, 2) if rvol is not None else None,
            "min_rr_regime": min_rr,
            "tp_source": tp_source_label,
            "setup_type": (structure or {}).get("setup_type", "N/A"),
            "structure_level": (structure or {}).get("structure_level"),
            "invalidation_level": (structure or {}).get("invalidation_level"),
            "sl_atr": round(structural_sl.get("sl_atr"), 2) if structural_sl else None
        }
    except Exception as e:
        if verbose:
            print(f"  ⚠️ Ticker indisponible: {e}", flush=True)
        return None

def analyze_etf(ticker, regime=None):
    if regime is None:
        regime = _default_regime()
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

        gap_min_long = 0.5 + regime.get("gap_min_long_adj", 0.0)
        gap_max_short = SHORT_ETF_GAP_MIN - regime.get("gap_min_short_adj", 0.0)

        score = 0
        if gap_min_long <= gap <= 8:
            direction = "LONG"
            score += 1
        elif -8 <= gap <= gap_max_short:
            direction = "SHORT"
            score += 1
        else:
            return None

        if direction == "LONG" and not DIRECTION_CONTROL.get("enable_longs", True):
            print(f"  ❌ ETF {ticker}: LONG désactivé via direction_control", flush=True)
            return None
        if direction == "SHORT" and not DIRECTION_CONTROL.get("enable_shorts", True):
            print(f"  ❌ ETF {ticker}: SHORT désactivé via direction_control", flush=True)
            return None
        if direction == "SHORT" and price > SHORT_PRICE_MAX_ETF:
            print(f"  ❌ ETF {ticker}: SHORT prix {price:.2f}$ > {SHORT_PRICE_MAX_ETF:.0f}$ (limite absolue)", flush=True)
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

        structure_hist = fetch_intraday_structure(ticker)
        rvol = calculate_intraday_rvol_from_hist(structure_hist) \
               if INTRADAY_FILTERS.get("rvol_enabled", True) else None

        now_min = datetime.now(MONTREAL_TZ).hour * 60 + datetime.now(MONTREAL_TZ).minute
        if rvol is not None and now_min >= INTRADAY_FILTERS.get("rvol_apply_reject_after_min", 585):
            if rvol < INTRADAY_FILTERS.get("rvol_reject_below", 0.5):
                print(f"  ❌ ETF {ticker}: RVOL intraday x{rvol:.2f} trop faible", flush=True)
                return None

        timing_pen = get_timing_penalty()
        effective_score_min = min(5, SCORE_MIN_ETFS + regime.get("score_min_etf_adj", 0) + timing_pen)
        if score < effective_score_min:
            return None

        exchange = get_exchange(info)
        confidence = get_confidence_score(score, vol_ratio, gap, "Large Cap")
        inst_score, _ = calculate_institutional_interest(info, price, vol_ratio, gap, direction)
        vwap, poc = get_vwap_poc(ticker, price, direction)
        if vwap is not None:
            vwap = round(vwap, 2)
        if poc is not None:
            poc = round(poc, 2)
        short_ratio = info.get("shortRatio", None)

        prior_high, prior_low = _prior_day_hl_from_daily(hist)
        daily_ctx = {"atr_pct": None, "prior_high": prior_high, "prior_low": prior_low}

        if len(hist) >= 15:
            daily_ctx["atr_pct"] = calculate_atr_pct_from_ohlc(
                hist["High"].astype(float), hist["Low"].astype(float), hist["Close"].astype(float), 14
            )
        atr_pct = daily_ctx["atr_pct"]

        tp_ref = estimate_tp_pct_from_atr(atr_pct, gap, score, regime.get("tp_mult_adj", 1.0))
        if tp_ref is None:
            if abs(gap) >= 6:
                tp_ref = 1.5 + (score - 3) * 0.5
            elif abs(gap) >= 3:
                tp_ref = 1.0 + (score - 3) * 0.5
            else:
                tp_ref = 0.5 + (score - 3) * 0.5
            tp_ref *= regime.get("tp_mult_adj", 1.0)

        structure = detect_setup_structure(structure_hist, price, direction, gap, vwap, poc)
        structural_sl = calculate_structural_sl(price, direction, structure)
        if structural_sl is None:
            print(f"  ❌ ETF {ticker}: SL structurel indisponible/invalide", flush=True)
            return None

        held_pct = info.get("heldPercentInstitutions", 0.5) or 0.5
        tp_ref_adj, _, trail_adj = adjust_risk_with_factors(
            tp_ref, structural_sl["sl_pct"], spread_pct, vol_ratio, "Large Cap", gap, held_pct
        )
        if direction == "SHORT":
            trail_adj += SHORT_TRAIL_WIDENING

        sl_final = validate_sl_bounds_only(structural_sl)
        if sl_final is None:
            print(
                f"  ❌ ETF {ticker}: SL structurel hors bornes "
                f"{structural_sl['sl_pct']:.2f}% ({structural_sl.get('sl_atr', 0):.2f} ATR)", flush=True
            )
            return None

        min_rr = get_min_rr_for_regime(regime)
        tp_candidates = _build_tp_candidates(
            entry=price, direction=direction,
            vwap=vwap, poc=poc,
            structure_hist=structure_hist,
            structure=structure,
            daily_ctx=daily_ctx,
        )
        tp_final, tp_source_label = compute_structural_tp(
            entry=price,
            sl_price=structural_sl["sl_price"],
            direction=direction,
            atr_tp_pct=tp_ref_adj,
            candidates=tp_candidates,
            min_rr=min_rr,
            lower_mult=INTRADAY_FILTERS.get("structural_tp_atr_lower_mult", 0.7),
            upper_mult=INTRADAY_FILTERS.get("structural_tp_atr_upper_mult", 1.5),
            verbose=False,
        )
        if tp_final is None:
            print(f"  ❌ ETF {ticker}: aucun TP structurel valide", flush=True)
            return None

        if tp_final <= 0 or sl_final <= 0 or tp_final / sl_final < min_rr:
            print(
                f"  ❌ ETF {ticker}: R/R final {tp_final/sl_final:.2f}:1 < min {min_rr:.1f}:1",
                flush=True
            )
            return None

        if direction == "LONG":
            tp_mult = 1 + tp_final / 100
            sl_mult = 1 - sl_final / 100
        else:
            tp_mult = 1 - tp_final / 100
            sl_mult = 1 + sl_final / 100
        trail = compute_coherent_trailing(3.0, trail_adj, sl_final)

        return {
            "ticker": ticker, "exchange": exchange, "price": price, "gap": gap,
            "score": score, "vol_ratio": vol_ratio,
            "aum_m": round(aum / 1_000_000, 1) if aum else 0,
            "confidence": confidence, "spread_pct": spread_pct, "direction": direction,
            "tp_mult": round(tp_mult, 3), "sl_mult": round(sl_mult, 3),
            "trail_pct": round(trail, 2), "tp_pct": round(tp_final, 2),
            "sl_pct": round(sl_final, 2), "inst_interest": inst_score,
            "atr_pct": round(atr_pct, 2) if atr_pct is not None else None,
            "rvol_intraday": round(rvol, 2) if rvol is not None else None,
            "min_rr_regime": min_rr,
            "tp_source": tp_source_label,
            "short_ratio": short_ratio, "vwap": vwap, "poc": poc,
            "synthetic_l2_score": 50.0, "synthetic_l2_label": "Not evaluated",
            "setup_type": (structure or {}).get("setup_type", "N/A"),
            "structure_level": (structure or {}).get("structure_level"),
            "invalidation_level": (structure or {}).get("invalidation_level"),
            "sl_atr": round(structural_sl.get("sl_atr"), 2) if structural_sl else None
        }
    except Exception as e:
        print(f"  ⚠️ ETF indisponible ({ticker}): {e}", flush=True)
        return None

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
            ticker=data["ticker"], direction=data["direction"],
            current_price=data["price"], spread_pct=data["spread_pct"],
            vwap=data.get("vwap"), poc=data.get("poc"), verbose=True
        )
        data["synthetic_l2_score"] = l2["score"]
        data["synthetic_l2_label"] = l2["label"]
    return results

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

def build_setup_message(data, is_etf=False, bias="⚪ Neutral", rank="1/1", regime=None):
    if regime is None:
        regime = _default_regime()

    entry = data["price"]
    direction = data["direction"]
    tp_pct = data.get("tp_pct", 0.0)
    sl_pct = data.get("sl_pct", 0.0)
    trail_pct = data.get("trail_pct", 0.0)
    tp_source = data.get("tp_source", None)

    if direction == "LONG":
        tp = round(entry * (1 + tp_pct / 100), 2)
        sl = round(entry * (1 - sl_pct / 100), 2)
        gain_display = f"+{tp_pct:.1f}%"
        loss_display = f"-{sl_pct:.1f}%"
    else:
        tp = round(entry * (1 - tp_pct / 100), 2)
        sl = round(entry * (1 + sl_pct / 100), 2)
        gain_display = f"-{tp_pct:.1f}%"
        loss_display = f"+{sl_pct:.1f}%"

    qty = calculate_quantity(entry, sl, CAPITAL, RISK_PER_TRADE, MAX_CAPITAL_PER_POSITION)
    unit_label = "shares" if not is_etf else "units"

    if direction == "LONG":
        trail_price = round(entry * 1.005, 2)
    else:
        trail_price = round(entry * 0.995, 2)

    spread_display = ""
    if data.get("spread_pct", 0) > 0:
        spread_usd = round((data["spread_pct"] / 100) * entry, 2)
        spread_display = f" | Spread: {data['spread_pct']:.2f}% (${spread_usd:.2f})"

    gap_display = f"{data.get('gap', 0.0):+.2f}%"

    verdict_text, verdict_emoji = get_verdict(data["confidence"])
    direction_emoji = "📈 LONG" if direction == "LONG" else "📉 SHORT"

    inst = data.get("inst_interest", 0)
    inst_label = "High" if inst >= 7 else "Moderate" if inst >= 4 else "Low"

    conv_label, conv_emoji = calculate_conviction(
        direction,
        data["gap"],
        data["vol_ratio"],
        data.get("vwap"),
        entry,
        inst,
        bias,
        data.get("poc"),
        data.get("synthetic_l2_score", 50),
    )

    regime_name = regime.get("regime", "Unknown")
    volatility = regime.get("volatility", "Normal")
    adx = regime.get("adx")
    adx_display = f"{adx:.1f}" if isinstance(adx, (int, float)) else "N/A"

    heading = "🚀 BEST ETF SETUP" if is_etf else "🚀 BEST STOCK SETUP"

    rr_tp = tp_pct / sl_pct if sl_pct > 0 else 0.0
    min_rr = data.get("min_rr_regime", get_min_rr_for_regime(regime))

    if tp_source:
        abbr = _TP_SOURCE_ABBR.get(tp_source, tp_source)
        tp_tag = f" [{abbr}]"
    else:
        tp_tag = ""

    msg = f"{heading}\n"
    msg += f"🔹 {data['ticker']} ({data['exchange']}){spread_display} | GAP: {gap_display}\n"
    msg += f"  Direction: {direction_emoji}\n"
    msg += f"  🧭 Regime: {regime_name} | Vol: {volatility} | ADX: {adx_display}\n"
    msg += f"  Market Bias: {bias}\n"
    msg += f"  🏛️ Institutional Interest: {inst}/10 ({inst_label})\n"
    msg += f"  ⚖️ VERDICT: {verdict_emoji} {verdict_text} | CONVICTION: {conv_emoji} {conv_label} | RANK: {rank}\n"
    msg += f"  🎯 ENTRY: ${format_price(entry)}\n"
    msg += f"  📦 QUANTITY: {qty} {unit_label}\n"
    msg += f"  🏁 TP: ${format_price(tp)} ({gain_display}){tp_tag}\n"
    msg += f"  🛑 STOP LOSS: ${format_price(sl)} ({loss_display})\n"
    msg += f"  🔄 TRAILING STOP: ${format_price(trail_price)} → {trail_pct:.1f}%\n"
    msg += f"  📊 R/R (TP2) → {rr_tp:.1f}:1 | Min. régime: {min_rr:.1f}:1\n"

    return msg

def wait_until_target(target_hour, target_minute):
    target = datetime.now(MONTREAL_TZ).replace(
        hour=target_hour, minute=target_minute, second=0, microsecond=0
    )
    if target <= datetime.now(MONTREAL_TZ):
        target += timedelta(minutes=SCAN_INTERVAL)

    diff_init = (target - datetime.now(MONTREAL_TZ)).total_seconds()
    print(f"⏳ Attente jusqu'à {target.strftime('%H:%M')}... ({diff_init/60:.1f} min)", flush=True)

    last_heartbeat = datetime.now(MONTREAL_TZ)

    while True:
        now = datetime.now(MONTREAL_TZ)
        if now >= target:
            break
        time.sleep(30)
        now = datetime.now(MONTREAL_TZ)
        if now >= target:
            break
        if (now - last_heartbeat).total_seconds() >= 300:
            remaining = (target - now).total_seconds()
            print(f"💤 ... encore {remaining/60:.1f} min avant {target.strftime('%H:%M')}", flush=True)
            last_heartbeat = now

def main():
    now = datetime.now(MONTREAL_TZ)
    heure = now.hour
    minute = now.minute

    if is_ca_market_closed(now):
        print("🏖️ Marché CA fermé – Arrêt.", flush=True)
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
        print(f"⚠️ Fermeture anticipée – Marché ferme à {early_hour}:00 ET.", flush=True)

    if 9 <= heure <= 11 and (heure < 11 or minute <= 35):
        session = "morning"
        start_hour, start_min = 9, 30
        end_hour, end_min = 11, 20
        scan_hours = [9, 10, 11]
        scan_minutes = [45, 30, 15]
        print("☀️ Session MATIN détectée – Scans à 09:45, 10:30, 11:15.", flush=True)
    elif 14 <= heure <= 15 and (heure < 15 or minute <= 5):
        session = "afternoon"
        start_hour, start_min = 14, 0
        end_hour, end_min = 15, 0
        if early_close and early_hour is not None and early_hour <= 14:
            print(f"🌙 Session PM annulée – early close à {early_hour}:00 ET.", flush=True)
            if IS_MANUAL_RUN:
                msg = (
                    "🤖 <b>NorthSentinel CA Only</b>™\n"
                    "<i>Early close at " + str(early_hour) + ":00 ET – No PM session today.</i>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "<i>Informational automated signal. Not financial or trading advice.</i>"
                )
                send_telegram(msg)
            return
        scan_hours = [14, 15]
        scan_minutes = [0, 0]
        print("🌙 Session APRÈS-MIDI détectée – Scans à 14:00, 15:00.", flush=True)
    else:
        print(f"⏰ Hors plage horaire ({now.strftime('%H:%M')}) – Arrêt.", flush=True)
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

        if now.hour > end_hour or (now.hour == end_hour and now.minute > end_min):
            print(f"⏹️ Fin de session ({end_hour:02d}:{end_min:02d}) – Arrêt.", flush=True)
            send_session_end_message(now, session)
            break

        current_hour, current_min = now.hour, now.minute

        is_scan_time = False
        current_total = current_hour * 60 + current_min
        for h, m in zip(scan_hours, scan_minutes):
            slot_total = h * 60 + m
            if 0 <= current_total - slot_total <= 5:
                is_scan_time = True
                break

        if is_scan_time:
            print(f"\n📊 Scan à {now.strftime('%H:%M')} (session {session})", flush=True)

            print("\n🧭 ================================", flush=True)
            print("🧭 DÉTECTION DE RÉGIME DE MARCHÉ", flush=True)
            print("🧭 ================================", flush=True)
            regime = detect_market_regime(verbose=True)
            market_bias = regime["bias"]

            stocks_results = []
            for ticker in STOCK_TICKERS:
                print(f"  - {ticker}:", flush=True)
                data = analyze_stock(ticker, regime=regime, verbose=True)
                if data:
                    stocks_results.append(data)
                    print(f"    ✅ Score {data['score']}/7 | {data['direction']} | TP: {data['tp_pct']}% [{data.get('tp_source','')}] | SL: {data['sl_pct']}% | RVOL: {data.get('rvol_intraday')}", flush=True)
                else:
                    print("    ❌", flush=True)

            etfs_results = []
            for ticker in ETF_TICKERS:
                print(f"  - {ticker}...", end=" ", flush=True)
                data = analyze_etf(ticker, regime=regime)
                if data:
                    etfs_results.append(data)
                    print(f"✅ Score {data['score']}/5 | {data['direction']} | TP: {data['tp_pct']}% [{data.get('tp_source','')}] | SL: {data['sl_pct']}% | RVOL: {data.get('rvol_intraday')}", flush=True)
                else:
                    print("❌", flush=True)

            print("\n🧠 ================================", flush=True)
            print("🧠 SYNTHETIC L2 — STOCKS", flush=True)
            print("🧠 ================================", flush=True)
            stocks_results = enrich_with_synthetic_l2(stocks_results, is_etf=False)
            print("\n🧠 ================================", flush=True)
            print("🧠 SYNTHETIC L2 — ETFs", flush=True)
            print("🧠 ================================", flush=True)
            etfs_results = enrich_with_synthetic_l2(etfs_results, is_etf=True)

            stock_long = [s for s in stocks_results if s["direction"] == "LONG"]
            stock_short = [s for s in stocks_results if s["direction"] == "SHORT"]
            etf_long = [e for e in etfs_results if e["direction"] == "LONG"]
            etf_short = [e for e in etfs_results if e["direction"] == "SHORT"]

            def get_best(candidates, is_etf):
                if not candidates:
                    return None
                scored = []
                for cand in candidates:
                    ps = calculate_priority_score(cand, market_bias, is_etf)
                    scored.append((ps, cand))
                scored.sort(key=lambda x: x[0], reverse=True)
                return scored[0][1]

            selected_stock = None
            selected_etf = None

            pair_candidates = []
            threshold = SYNTHETIC_L2_CONFIG["priority_threshold_for_pair"]
            for s in stocks_results:
                for e in etfs_results:
                    if s["direction"] != e["direction"]:
                        ps = calculate_priority_score(s, market_bias, False)
                        pe = calculate_priority_score(e, market_bias, True)
                        if ps >= threshold and pe >= threshold:
                            pair_candidates.append((ps + pe, ps, pe, s, e))
            if pair_candidates:
                pair_candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
                _, _, _, selected_stock, selected_etf = pair_candidates[0]
            else:
                all_candidates = []
                for cand in stocks_results:
                    all_candidates.append((calculate_priority_score(cand, market_bias, False), cand, False))
                for cand in etfs_results:
                    all_candidates.append((calculate_priority_score(cand, market_bias, True), cand, True))
                all_candidates.sort(key=lambda x: x[0], reverse=True)
                if all_candidates:
                    _, best, is_etf = all_candidates[0]
                    if is_etf:
                        selected_etf = best
                    else:
                        selected_stock = best

            selected_items = []
            if selected_stock:
                selected_items.append((selected_stock, False))
            if selected_etf:
                selected_items.append((selected_etf, True))

            if selected_items:
                now_scan = datetime.now(MONTREAL_TZ)
                header = (
                    "🤖 NorthSentinel CA Only™\n"
                    "Canadian intraday trading signals. Long & Short. Manual execution.\n"
                    f"📅 {now_scan.strftime('%Y-%m-%d %H:%M')} (Montreal) | Scanned: {len(STOCK_TICKERS)} Stocks, {len(ETF_TICKERS)} ETFs\n"
                    f"Capital: ${CAPITAL:,.0f} (Paper Trading Account)\n"
                    "═══════════════════════\n\n"
                )
                msg = header
                total_selected = len(selected_items)
                for idx, (selected, is_etf) in enumerate(selected_items, start=1):
                    rank = f"{idx}/{total_selected}"
                    msg += build_setup_message(
                        selected, is_etf=is_etf, bias=market_bias, rank=rank, regime=regime
                    )
                    if idx < total_selected:
                        msg += "\n"
                msg += "━━━━━━━━━━━━━━━━━\n\n"
                msg += "Informational automated signal. Not financial or trading advice."
                send_telegram(msg)
            else:
                print("  ℹ️ Aucun setup validé — aucun message Telegram envoyé.", flush=True)

        next_scan_time = None
        for h, m in zip(scan_hours, scan_minutes):
            if h > current_hour or (h == current_hour and m > current_min):
                next_scan_time = (h, m)
                break

        if next_scan_time is None:
            print("⏹️ Dernier scan effectué – Fin de session immédiate.", flush=True)
            send_session_end_message(now, session)
            break

        target_hour, target_min = next_scan_time

        if target_hour > end_hour or (target_hour == end_hour and target_min > end_min):
            print("⏹️ Prochaine cible après la fin de session – Arrêt.", flush=True)
            send_session_end_message(now, session)
            break

        wait_until_target(target_hour, target_min)

if __name__ == "__main__":
    main()
