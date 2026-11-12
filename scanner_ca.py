# ============================================================
# NORTHSENTINEL CA ONLY — SCANNER INTRADAY CONTINU (BOUCLE)
# SHORTS + LONGS — 3 SOURCES DE NEWS
# VERSION TP UNIQUE ANCRÉ STRUCTURELLEMENT
#
# 2 CRONS EXTERNES :
#   - AM : déclenché à 09:30 ET → scans 09:45, 10:30, 11:15
#   - PM : déclenché à 14:00 ET → scans 14:00, 15:00
#
# >>> v4 — CORRECTIFS COHÉRENCE 2026-11-02 (post-diagnostic) <<<
#   P0 — bugs bloquants :
#     C1. return None if SHORT else None → ne rejette plus les LONGs
#     C2. vol_ratio_min_short : 0.9 → 0.3
#     C3. choppy_score_penalty : 1 → 0
#     C4. SL auto-élargi au minimum au lieu d'être rejeté
#     C5. Précision R/R : tolérance 1e-6
#   P1 — calibration / cohérence :
#     C6. weak_setup_max_rr : 3.5 → 4.5 ; lower_mult : 0.55 → 0.40
#     C7. gap_min_long : 1.0 → 0.5 ; gap_min_short : -1.5 → -1.0
#     C8. Synthetic L2 calculé AVANT calibration TP
#     C9. RVOL x0.00 = donnée manquante (pas rejet)
#     C10. rvol_apply_reject_after_min : 585 → 660
#     C11. heldPercentInstitutions manquant → inst_interest neutre (5)
#     C12. Univers nettoyé
#     C13. Compteurs de rejets par scan
#   Application de sl_mult_adj du régime (High Vol élargit le buffer)
#
# >>> v4.1 — CORRECTIFS BIAIS DIRECTIONNEL 2026-11-03 (post-jour 1) <<<
#   F1. vol_ratio_min_short : 0.3 → 0.0
#       Motif : 49 SHORTs tués au volume le 3/11 (LUN, T, LSPD, ATD, L,
#       EMP-A, GIB-A, OTEX, DSG, CS, BAM, BN, NTR, AQN, REI-UN, QSR,
#       GIL, TRI, ABX, K, WN, IFC, AEM, WPM, EQX, CAR-UN…). À 09:45
#       le volume cumulé est ~4% du volume quotidien, un seuil de 0.3
#       exige 8× le volume normal → élimination automatique.
#       Le RVOL intraday reste seul juge de liquidité (correctement
#       normalisé par construction).
#   F2. gap_min_short : -1.0 → -0.5
#       Motif : symétrie avec gap_min_long = +0.5. Avec l'ancien ratio
#       1:2, la probabilité qu'un titre satisfasse la borne SHORT était
#       mécaniquement deux fois plus faible que pour la borne LONG.
#   F3. Sélection finale : best LONG + best SHORT indépendants
#       (remplacé en v4.2/v4.3, voir F4 et F5)
#
# >>> v4.2 — RÈGLE DIVERSITÉ DE TYPE 2026-11-04 <<<
#   F4. Sélection finale stricte top-down :
#       - Scorer top 1 + top 2 (stocks + ETFs confondus par priority_score)
#       - Si top 2 = (1 stock + 1 ETF) ET (LONG + SHORT) → envoyer les 2
#       - Sinon (même type OU même direction) → envoyer UNIQUEMENT top 1
#       Corrige la régression du 04/11 (ZUB.TO ETF LONG + ZEO.TO ETF
#       SHORT = 2 same-type). Remplace l'appel à _select_best_per_direction
#       dans main().
#
# >>> v4.3 — RÈGLE DIVERSITÉ DE TYPE DÉFINITIVE 2026-11-04 <<<
#   F5. _select_top_candidates_with_diversity_rules() est appelée dans
#       main() à la place de _select_best_per_direction().
#       Comportement :
#         - 2 same-type + same-direction          → 1 setup
#         - 2 same-type + opposite-direction      → 1 setup (interdit)
#         - 2 different-type + same-direction     → 1 setup
#         - 2 different-type + opposite-direction → 2 setups (seul cas)
#       Les logs de refus indiquent désormais la raison exacte
#       (même type ET même direction / même type / même direction).
#       _select_best_per_direction est conservée (legacy) mais
#       n'est plus appelée.
#
# >>> v4.4 — PERFORMANCE & DIAGNOSTIC (phase 1) <<<
#   P1. Flux RSS (CBC, Financial Post) téléchargés UNE fois par scan
#       (refresh_rss_cache) au lieu d'une fois par ticker.
#   P2. Sortie anticipée : score + 1 < minimum -> rejet avant news et
#       historique 5 min (la news ne peut valoir qu'un point).
#       ETFs : filtre de score avant le téléchargement de structure.
#   P3. get_market_cap_category réutilise `info` (plus de 2e .info).
#   P4. UN seul téléchargement 1 min par ticker (HTTP_SESSION + retry),
#       partagé entre VWAP/POC et Synthetic L2 (3 -> 1 appels).
#       VWAP/POC calculés localement avec les MÊMES formules que
#       pro_volume_profile.py, qui n'est plus importé ni modifié
#       (l'autre bot qui l'utilise n'est pas impacté).
#   P5. Régime : barre quotidienne partielle exclue (flag
#       regime.exclude_partial_bar) ; logs de diagnostic enrichis
#       (tendance, SMA20/50, ADX).
#   P6. Chronométrage par phase + compteur vwap_na (VWAP/POC manquants).
#
# >>> v4.5 — ROBUSTESSE & PLANIFICATION (2026-11-11) <<<
#   R1. Calendrier TSX : un férié tombant un week-end est reporté au prochain
#       jour ouvrable libre (Boxing Day 2026 -> lundi 28/12 ; 2027 -> 27 et
#       28/12). L'ancienne règle (samedi -> vendredi) ouvrait ces jours-là.
#   R2. Conviction SHORT : "Moderate" accepté aussi en biais Risk-off (symétrie LONG).
#   R3. Pannes de données distinguées des rejets (data_missing) ; erreurs
#       réseau comptées par scan (DATA_ERRORS) ; exceptions typées dans les logs.
#   R4. Telegram : 3 tentatives, gestion du 429, repli en texte brut si le HTML
#       est refusé, token + chat_id vérifiés.
#   R5. PLANIFICATION : créneaux traités un à un avec RATTRAPAGE (jusqu'à 12 min
#       de retard) ; créneau manqué signalé sur Telegram ; un scan qui plante
#       n'empêche plus les créneaux suivants (try/except par scan) ; plus de
#       report de +60 min quand un scan déborde ; fin de session = plus aucun
#       créneau à traiter (plus d'heure de fin fixe qui coupait le 11:15).
#   R6. Fraîcheur des cotes : âge loggé et signalé dans les LOGS au-delà de
#       20 min ; re-cotation des setups retenus avant envoi (dérive loggée).
#   R7. Interrupteurs DÉSACTIVÉS par défaut (data_robustness) :
#       rvol_for_volume_signals (RVOL intraday à la place du volume cumulé)
#       missing_data_gives_point=False (donnée absente = 0 point).
#       Comptage des "points gratuits" toujours actif (visibilité).
#   R8. Paramètres sans effet marqués "INACTIF" dans CONFIG (aucun changement).
#
# >>> v4.6 — QUANTITÉ PAR PALIERS (2026-11-11) <<<
#   Q1. QUANTITY = palier x quantité maximale autorisée (10 % du capital),
#       palier = f(VERDICT, CONVICTION, RANK), quels que soient régime, biais
#       de marché et direction :
#           VERDICT   : Strong -> 100 %, Favorable -> 67 %, Mixed -> 33 %
#           CONVICTION: Low retire un cran (plancher 33 %) ; High/Moderate = 0
#       Reprend tes 3 règles (Strong+High/Moderate = 100 % ; Favorable+Moderate
#       = 67 % ; Mixed+Low = 33 %) et comble les 6 autres combinaisons.
#   Q2. RANK 2/2 : palier plafonné à 67 %.
#   Q3. RVOL intraday ACTIVÉ pour les signaux de volume
#       (data_robustness.rvol_for_volume_signals = True) : le volume cumulé du
#       jour sous-estimait mécaniquement le volume le matin et faussait
#       VERDICT/CONVICTION, désormais utilisés pour dimensionner. Le scan loggue
#       la répartition Verdict x Conviction des candidats pour calibrer.
#   Pas de plafond d'exposition par scan : un seul setup est exécuté par message.
#
# >>> v4.7 — MESSAGES TELEGRAM INCHANGÉS (2026-11-11) <<<
#   Structure et contenu des messages Telegram strictement identiques à la v4.4
#   (en-tête, bloc setup, « No valid setup », fin de session). Seule la VALEUR
#   de la ligne QUANTITY résulte des paliers v4.6. Retirés des messages : ligne
#   SIZING, âge de cote, dérive de prix (désormais dans les logs). Messages
#   supplémentaires (créneau manqué, scan en échec) désactivés par défaut :
#   scheduling.notify_missed_slot / notify_scan_failure.
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
    "price_min_stocks": 5.00,
    "price_min_etfs": 10.00,
    "price_max_stocks": 300.00,
    "price_max_etfs": 300.00,
    "scan_interval_minutes": 60,

    "position_management": {
        "qty1_pct": 100.0,
        "qty2_pct": 0.0,
        "ibkr_pricing_model": "fixed",
        "ibkr_tiered_commission_per_share": 0.008,
        "ibkr_fixed_commission_per_share": 0.010,
        "ibkr_min_commission_per_order": 1.00,
        "ibkr_clearing_per_share": 0.0,
        "ibkr_clearing_cap_per_order": 0.0,
        "ibkr_regulatory_per_share": 0.0,
        "ibkr_regulatory_cap_per_order": 0.0,
        "fee_safety_buffer_per_order": 1.00,
        "fee_safe_trailing": True,   # INACTIF : non lu par le code
        "fee_margin_factor": 1.05
    },

    "technical_structure": {
        "enabled": True,
        "intraday_period": "5d",
        "intraday_interval": "5m",
        "lookback_bars": 48,
        "swing_window": 3,                       # INACTIF : non lu par le code
        "structure_buffer_atr": 0.35,
        "min_sl_atr": 0.55,
        "max_sl_atr": 3.00,
        "min_sl_pct": 0.35,
        "max_sl_pct": 3.00,
        "breakout_tolerance_pct": 0.35,
        "support_resistance_tolerance_pct": 0.50,
        "reject_if_structure_unavailable": True,  # INACTIF : non lu par le code
        "require_room_to_tp": True               # INACTIF : non lu par le code
    },

    "synthetic_l2": {
        "enabled": True,
        "interval": "1m",
        "min_bars": 15,
        "lookback_bars": 30,
        "short_window": 5,
        "medium_window": 15,
        "strong_threshold": 75,
        "supportive_threshold": 60,
        "neutral_threshold": 40,
        "weak_threshold": 25,
        "bonus_strong": 3.0,
        "bonus_supportive": 1.5,
        "penalty_weak": -2.0,
        "penalty_bad": -4.0,
        "priority_threshold_for_pair": 12.0      # INACTIF : legacy (v4.1)
    },

    "direction_control": {
        "enable_longs": True,
        "enable_shorts": True,
    },

    "short_adjustment": {
        "sl_widening_pct": 0.4,        # INACTIF : jamais appliqué (le SL des SHORTs n'est pas élargi)
        "trail_widening_pct": 0.2,
        "gap_min_short": -0.5,         # v4.1 — F2 : -1.0 → -0.5 (symétrie LONG)
        "vol_ratio_min_short": 0.0,    # v4.1 — F1 : 0.3 → 0.0 (filtre mort)
        "etf_gap_min_short": -0.75,
        "price_max_short_stock": 999.0,
        "price_max_short_etf": 999.0,
    },

    "regime": {
        "enabled": True,
        "exclude_partial_bar": True,   # v4.4 — P5
        "benchmark_ticker": "^GSPTSE",
        "lookback_period": "6mo",
        "adx_period": 14,
        "atr_period": 14,
        "atr_percentile_window": 60,
        "trend_adx_threshold": 20,
        "high_vol_atr_percentile": 75,
        "low_vol_atr_percentile": 25,
        "counter_trend_gap_penalty": 0.5,
        "choppy_score_penalty": 0,
        "sl_mult_high_vol": 1.25,
        "sl_mult_low_vol": 0.90,
        "tp_mult_ranging": 0.90,
        "min_rr_by_regime": {
            "Trending-Up": 1.6,
            "Trending-Down": 1.6,
            "Ranging": 2.0,
            "Choppy-Volatile": 2.2,
            "Unknown": 2.0
        },
        "min_rr_default": 2.0
    },

    "tp_calibration": {
        "enable": True,
        "counter_trend_regime_mult": {
            "Trending-Down_LONG": 0.80,
            "Trending-Up_SHORT": 0.80,
        },
        "conviction_mult": {
            "Low": 0.85,
            "Moderate": 0.92,
            "High": 1.00,
        },
        "inst_interest_mult": {
            "le3": 0.90,
            "eq4": 0.95,
            "ge5": 1.00,
        },
        "time_caps": [
            {"end_min": 600,  "cap_pct": None, "atr_mult": None},
            {"end_min": 690,  "cap_pct": 5.5,  "atr_mult": 4.5},
            {"end_min": 840,  "cap_pct": 4.5,  "atr_mult": 3.5},
            {"end_min": 1440, "cap_pct": 3.5,  "atr_mult": 3.0},
        ],
        "weak_setup_max_rr": 4.5,
        "atr_hard_cap_mult": 1.5,
    },

    "intraday_filters": {
        "timing_penalty_windows": [
            # INACTIF en pratique : le 1er scan démarre à 09:45 (585), hors de cette fenêtre
            {"start_min": 570, "end_min": 585, "penalty": 1},
        ],

        "rvol_enabled": True,
        "rvol_strong_threshold": 2.0,
        "rvol_moderate_threshold": 1.2,
        "rvol_weak_threshold": 0.8,
        "rvol_reject_below": 0.5,
        "rvol_bonus_strong": 1.5,
        "rvol_bonus_moderate": 0.5,
        "rvol_penalty_weak": -1.0,
        "rvol_apply_reject_after_min": 660,

        "structural_tp_enabled": True,   # INACTIF : le TP structurel est toujours actif
        "structural_tp_atr_lower_mult": 0.40,
        "structural_tp_atr_upper_mult": 1.80,
    },

    "scheduling": {
        "catchup_grace_min": 12,       # un créneau peut démarrer jusqu'à 12 min en retard
        "notify_missed_slot": False,   # True = message Telegram si un créneau est définitivement manqué (log toujours écrit)
        "notify_scan_failure": False,  # True = message Telegram si un scan plante (log toujours écrit)
    },

    "data_robustness": {
        "quote_warn_after_min": 20,    # avertir si la cote a plus de 20 min
        "requote_before_send": True,   # re-coter les setups retenus juste avant l'envoi
        "drift_warn_pct": 0.30,        # avertir si le prix a bougé de plus de 0,30 % depuis le scan
        "rvol_for_volume_signals": True,    # v4.6 : True = RVOL intraday ; False = volume cumulé (historique)
        "missing_data_gives_point": True,   # True = historique (float/beta/shortRatio absents = +1)
    },

    "telegram": {
        "max_attempts": 3,
    },

    "position_sizing": {
        "enabled": True,               # False = quantité maximale pour tous les setups (comportement v4.5)
        "tiers_pct": [33, 67, 100],    # paliers : Mixed, Favorable, Strong
        "low_conviction_notches": 1,   # CONVICTION Low : retire 1 cran (plancher = 1er palier)
        "rank2_cap_pct": 67,           # RANK 2/2 : palier plafonné
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
            "TFII.TO", "MDA.TO", "CGO.TO", "QBR-B.TO",
            "IFC.TO", "SLF.TO", "RBA.TO", "CGY.TO",
            "NA.TO",
            "GIB-A.TO", "OTEX.TO", "DSG.TO", "CS.TO",
            "CAR-UN.TO",
            "AEM.TO", "WPM.TO", "EQX.TO", "LUG.TO",
            "BEP-UN.TO", "BAM.TO", "BN.TO", "NTR.TO",
            "TD.TO", "CM.TO", "AQN.TO",
            "ENB.TO", "ARX.TO", "VET.TO", "REI-UN.TO", "TCW.TO",
            "TSAT.TO", "IVN.TO", "HBM.TO", "MTY.TO", "QSR.TO",
            "SHOP.TO",
            "WN.TO", "HPS-A.TO", "EXE.TO",
            "TOI.V", "ZDC.V", "QNC.V",
            "BTE.TO", "EQB.TO", "TRI.TO", "GIL.TO"
        ],
        "etfs": [
            "XFN.TO", "ZEB.TO", "XEG.TO", "ZEO.TO", "XGD.TO",
            "XMA.TO", "XST.TO", "XRE.TO", "XUT.TO",
            "ZSP.TO", "XIC.TO", "HCLN.TO", "HHIS.TO", "HXS.TO",
            "HXQ.TO", "VFV.TO", "XQQ.TO", "HHL.TO", "TXF.TO",
            "HUTL.TO", "ZDI.TO", "FIE.TO",
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
PRICE_MIN_ETFS = CONFIG["price_min_etfs"]
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
IBKR_FEE_MARGIN = float(POSITION_CONFIG.get("fee_margin_factor", 1.05))
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
TP_CALIBRATION = CONFIG["tp_calibration"]
SCHED_CONFIG = CONFIG["scheduling"]
ROBUST_CONFIG = CONFIG["data_robustness"]
SIZING_CONFIG = CONFIG["position_sizing"]

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

DATA_ERRORS = {}

def _note_error(kind):
    """v4.5 — compte les erreurs réseau/données par type (remis à zéro à chaque scan)."""
    DATA_ERRORS[kind] = DATA_ERRORS.get(kind, 0) + 1

def _reset_data_errors():
    DATA_ERRORS.clear()

def _print_data_errors():
    if DATA_ERRORS:
        detail = " ".join(f"{k}={v}" for k, v in sorted(DATA_ERRORS.items()))
        print(f"  📡 Erreurs réseau/données ce scan : {detail}", flush=True)

def _strip_html(text):
    return re.sub(r"<[^>]+>", "", text)

def send_telegram(message, max_attempts=None):
    """v4.5 — retry, gestion du 429 (retry_after), repli en texte brut si le
    HTML est refusé, token + chat_id vérifiés. Retourne True si envoyé."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Token ou chat_id Telegram manquant", flush=True)
        return False
    attempts = int(max_attempts or CONFIG.get("telegram", {}).get("max_attempts", 3))
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message[:4096], "parse_mode": "HTML"}
    wait = 2
    for attempt in range(1, attempts + 1):
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                suffix = f" (tentative {attempt})" if attempt > 1 else ""
                print(f"✅ Telegram envoyé{suffix}", flush=True)
                return True
            body = r.text or ""
            if r.status_code == 400 and "parse" in body.lower() and payload.get("parse_mode"):
                print("⚠️ Telegram: format HTML refusé — repli en texte brut", flush=True)
                payload = {"chat_id": TELEGRAM_CHAT_ID, "text": _strip_html(message)[:4096]}
                continue
            if r.status_code == 429:
                try:
                    wait = int(r.json().get("parameters", {}).get("retry_after", 5))
                except Exception:
                    wait = 5
                wait = min(max(wait, 1), 30)
            elif r.status_code >= 500:
                wait = 2 * attempt
            else:
                print(f"❌ Erreur Telegram {r.status_code}: {body}", flush=True)
                return False
            print(f"⚠️ Telegram {r.status_code} — nouvelle tentative dans {wait}s ({attempt}/{attempts})", flush=True)
        except Exception as e:
            wait = 2 * attempt
            print(f"⚠️ Exception Telegram ({attempt}/{attempts}): {type(e).__name__}: {e}", flush=True)
        if attempt < attempts:
            time.sleep(wait)
    print("❌ Telegram: échec après toutes les tentatives", flush=True)
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
    ca.add(fam + timedelta(days=14))
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

def _observed_ca_holidays(year):
    """v4.5 — jours fériés TSX observés. Un férié tombant un samedi/dimanche
    est reporté au prochain jour ouvrable libre (lundi, puis mardi si le lundi
    est déjà férié). Ex. : Boxing Day sam. 26/12/2026 -> lun. 28/12 ;
    2027 : Noël sam. -> lun. 27/12, Boxing Day dim. -> mar. 28/12."""
    nominal = sorted(_build_ca_holidays(year))
    observed = {d for d in nominal if d.weekday() < 5}
    for d in nominal:
        if d.weekday() >= 5:
            o = d
            while o.weekday() >= 5 or o in observed:
                o += timedelta(days=1)
            observed.add(o)
    return observed

def is_ca_market_closed(check_date):
    if isinstance(check_date, datetime):
        check_date = check_date.date()
    if check_date.weekday() >= 5:
        return True
    return check_date in _observed_ca_holidays(check_date.year)

def _build_early_close_dates(year):
    from datetime import date
    # À VÉRIFIER auprès de la TSX : seule la veille de Noël (24/12, 13 h) est
    # confirmée par le calendrier officiel consulté ; le 31/12 n'a pas été retrouvé.
    return {date(year, 12, 24): 13, date(year, 12, 31): 13}

def is_early_close(check_date):
    if isinstance(check_date, datetime):
        check_date = check_date.date()
    return check_date in _build_early_close_dates(check_date.year)

def get_early_close_hour(check_date):
    if isinstance(check_date, datetime):
        check_date = check_date.date()
    return _build_early_close_dates(check_date.year).get(check_date)

RSS_CACHE = []

def refresh_rss_cache():
    """v4.4 — P1 : télécharge et parse les flux RSS UNE fois par scan."""
    global RSS_CACHE
    items = []
    for feed_url in RSS_FEEDS:
        try:
            r = requests.get(feed_url, timeout=5)
            soup = BeautifulSoup(r.content, "xml")
            for item in soup.find_all("item")[:15]:
                title = item.find("title").text if item.find("title") else ""
                description = item.find("description").text if item.find("description") else ""
                pub_date_str = item.find("pubDate").text if item.find("pubDate") else ""
                try:
                    pub_date = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
                    hours_ago = (datetime.now(timezone.utc) - pub_date).total_seconds() / 3600
                    if hours_ago < 6:
                        items.append({
                            "title": title,
                            "title_u": title.upper(),
                            "desc_u": description.upper(),
                            "hours_ago": hours_ago,
                        })
                except Exception:
                    pass
        except Exception:
            _note_error("rss")
    RSS_CACHE = items
    return len(items)

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
            except Exception:
                pass
    except Exception:
        _note_error("news_google")
    for it in RSS_CACHE:
        if ticker_clean in it["title_u"] or ticker_clean in it["desc_u"]:
            all_news.append({"title": it["title"], "hours_ago": it["hours_ago"]})
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

def fetch_intraday_1m(ticker):
    """v4.4 — P4 : UN seul téléchargement 1 min (session courante) par ticker,
    via la session HTTP partagée (retry). Réutilisé par VWAP/POC et Synthetic L2."""
    try:
        h = yf.Ticker(ticker, session=HTTP_SESSION).history(
            period="1d", interval="1m", prepost=False, auto_adjust=False
        )
        if h is None or h.empty:
            _note_error("hist_1m")
            return None
        return h
    except Exception:
        _note_error("hist_1m")
        return None

def compute_vwap_poc(hist):
    """v4.4 — P4 : mêmes formules que pro_volume_profile.calculate_vwap /
    calculate_poc (module partagé avec un autre bot, NON modifié) :
      VWAP = somme(prix typique (H+L+C)/3 x volume) / somme(volume)
      POC  = Close arrondi à 0,01 $ ayant le plus de volume cumulé
    Retourne (None, None) si l'un des deux est indisponible (comme le module).
    Seul écart : volume cumulé nul -> (None, None) au lieu de NaN."""
    try:
        if hist is None or hist.empty or len(hist) < 10:
            return None, None
        volume_total = float(hist["Volume"].sum())
        if not volume_total > 0:
            return None, None
        typical_price = (hist["High"] + hist["Low"] + hist["Close"]) / 3
        vwap = round(float((typical_price * hist["Volume"]).sum() / volume_total), 2)
        price_levels = hist["Close"].round(2)
        poc = round(float(hist.groupby(price_levels)["Volume"].sum().idxmax()), 2)
        return vwap, poc
    except Exception:
        return None, None

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
        if REGIME_CONFIG.get("exclude_partial_bar", True) and hist is not None and not hist.empty:
            try:
                today = datetime.now(MONTREAL_TZ).date()
                if hasattr(hist.index[-1], "date") and hist.index[-1].date() == today:
                    hist = hist.iloc[:-1]
            except Exception:
                pass
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
            "is_trending": bool(is_trending),
            "index_price": round(float(current_price), 2),
            "sma20": round(float(sma20.iloc[-1]), 2) if not sma20.isna().iloc[-1] else None,
            "sma50": round(float(sma50.iloc[-1]), 2) if sma50 is not None and not sma50.isna().iloc[-1] else None,
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
            print(
                f"🧭 DIAG: trending={result['is_trending']} (ADX seuil {REGIME_CONFIG['trend_adx_threshold']}) | "
                f"tendance={result['trend_direction']} | indice={result['index_price']} "
                f"SMA20={result['sma20']} SMA50={result['sma50']} | "
                f"barre partielle exclue={REGIME_CONFIG.get('exclude_partial_bar', True)}",
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

def get_counter_trend_tp_mult(direction, regime_name):
    if not TP_CALIBRATION.get("enable", True):
        return 1.0
    if regime_name == "Trending-Down" and direction == "LONG":
        return float(TP_CALIBRATION["counter_trend_regime_mult"].get("Trending-Down_LONG", 0.80))
    if regime_name == "Trending-Up" and direction == "SHORT":
        return float(TP_CALIBRATION["counter_trend_regime_mult"].get("Trending-Up_SHORT", 0.80))
    return 1.0

def get_conviction_tp_mult(conviction_label):
    if not TP_CALIBRATION.get("enable", True):
        return 1.0
    return float(TP_CALIBRATION["conviction_mult"].get(conviction_label, 1.00))

def get_inst_interest_tp_mult(inst_interest):
    if not TP_CALIBRATION.get("enable", True):
        return 1.0
    if inst_interest <= 3:
        return float(TP_CALIBRATION["inst_interest_mult"]["le3"])
    if inst_interest == 4:
        return float(TP_CALIBRATION["inst_interest_mult"]["eq4"])
    return float(TP_CALIBRATION["inst_interest_mult"]["ge5"])

def get_intraday_tp_cap_pct(atr_pct=None):
    if not TP_CALIBRATION.get("enable", True):
        return None
    now = datetime.now(MONTREAL_TZ)
    total = now.hour * 60 + now.minute
    for entry in TP_CALIBRATION.get("time_caps", []):
        if total < entry.get("end_min", 1440):
            caps = []
            cap_abs = entry.get("cap_pct", None)
            atr_mult = entry.get("atr_mult", None)
            if cap_abs is not None:
                caps.append(float(cap_abs))
            if atr_mult is not None and atr_pct is not None and atr_pct > 0:
                caps.append(float(atr_mult) * float(atr_pct))
            if not caps:
                return None
            return min(caps)
    return None

def get_weak_setup_max_rr(conviction_label, inst_interest):
    if not TP_CALIBRATION.get("enable", True):
        return None
    if conviction_label == "Low" and inst_interest <= 3:
        return float(TP_CALIBRATION.get("weak_setup_max_rr", 4.5))
    return None

def apply_tp_calibration(tp_ref_pct, direction, regime_name, conviction_label,
                          inst_interest, atr_pct=None, verbose=False):
    if not TP_CALIBRATION.get("enable", True) or tp_ref_pct is None:
        return tp_ref_pct, {}

    before = float(tp_ref_pct)
    mult_regime = get_counter_trend_tp_mult(direction, regime_name)
    mult_conv = get_conviction_tp_mult(conviction_label)
    mult_inst = get_inst_interest_tp_mult(inst_interest)

    tp_ref_pct = tp_ref_pct * mult_regime
    tp_ref_pct = tp_ref_pct * mult_conv
    tp_ref_pct = tp_ref_pct * mult_inst

    cap = get_intraday_tp_cap_pct(atr_pct=atr_pct)
    cap_applied = False
    if cap is not None and tp_ref_pct > cap:
        tp_ref_pct = cap
        cap_applied = True

    trace = {
        "before": round(before, 3),
        "after": round(tp_ref_pct, 3),
        "mult_regime": mult_regime,
        "mult_conviction": mult_conv,
        "mult_inst": mult_inst,
        "time_cap": cap,
        "atr_pct": round(float(atr_pct), 3) if atr_pct is not None else None,
        "cap_applied": cap_applied,
        "regime_name": regime_name,
        "conviction": conviction_label,
        "inst_interest": inst_interest,
    }
    if verbose:
        cap_str = f"{cap:.2f}%" if cap is not None else "aucun"
        atr_str = f"{atr_pct:.2f}%" if atr_pct is not None else "N/A"
        print(
            f"     🎛️ TP calib: {before:.2f}% "
            f"×{mult_regime:.2f}(régime {regime_name}) "
            f"×{mult_conv:.2f}(conv {conviction_label}) "
            f"×{mult_inst:.2f}(inst {inst_interest}) "
            f"→ cap {cap_str} (ATR titre {atr_str})"
            f"{' [APPLIQUÉ]' if cap_applied else ''} "
            f"= {tp_ref_pct:.2f}%",
            flush=True
        )
    return tp_ref_pct, trace

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

def calculate_synthetic_l2(ticker, direction, current_price, spread_pct, vwap=None, poc=None, verbose=False, hist=None):
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
        # v4.4 — P4 : historique 1 min partagé (évite un 3e téléchargement)
        if hist is not None and SYNTHETIC_L2_CONFIG["interval"] != "1m":
            hist = None
        if hist is None:
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
    raw_held = info.get("heldPercentInstitutions")
    held_missing = raw_held is None
    held = 0.5 if held_missing else raw_held
    short_ratio = info.get("shortRatio", 0) or 0
    sma50 = info.get("fiftyDayAverage", 0)
    details["held"] = held
    details["held_missing"] = held_missing
    details["short_ratio"] = short_ratio
    details["vol_ratio"] = vol_ratio
    details["sma50"] = sma50
    details["price"] = price
    details["gap"] = gap
    details["direction"] = direction
    if held >= 0.6:
        score += 2
    elif held >= 0.4:
        score += 1
    if short_ratio > 3 and direction == "LONG" and gap > 3:
        score += 2
    if vol_ratio > 2 and sma50 and price > sma50:
        score += 2
    elif vol_ratio > 1.5 and sma50 and price > sma50:
        score += 1
    if short_ratio > 4 and direction == "SHORT":
        score += 1
    score = min(score, 10)
    if held_missing:
        score = max(score, 5)
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
        elif green_count >= 3 and bias in ["Neutral", "Risk-off"]:
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

def get_market_cap_category(ticker, info=None):
    try:
        if info is None:
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

def _quote_age_minutes(info):
    """v4.5 — âge de la cote Yahoo en minutes (regularMarketTime), None si inconnu."""
    ts = info.get("regularMarketTime")
    if not ts:
        return None
    try:
        epoch = float(ts) if isinstance(ts, (int, float)) else ts.timestamp()
        return max(0.0, (time.time() - epoch) / 60.0)
    except Exception:
        return None

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
            _note_error("hist_daily")
            return None
        atr_pct = calculate_atr_pct_from_ohlc(
            hist["High"].astype(float), hist["Low"].astype(float), hist["Close"].astype(float), period
        )
        prior_high, prior_low = _prior_day_hl_from_daily(hist)
        return {"atr_pct": atr_pct, "prior_high": prior_high, "prior_low": prior_low}
    except Exception as e:
        _note_error("hist_daily")
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

def adjust_risk_with_factors(base_tp_pct, spread_pct, vol_ratio, cap_category, gap, held_pct):
    tp_pct = base_tp_pct
    trail_adj = 0.0
    if vol_ratio > 2.0:
        tp_pct += 0.5
    if cap_category in ["Micro Cap", "Small Cap"]:
        tp_pct += 1.0
    if abs(gap) > 10:
        tp_pct += 0.5
    if held_pct >= 0.6:
        tp_pct -= 0.5
        trail_adj -= 0.5
    elif held_pct <= 0.2:
        tp_pct += 1.0
        trail_adj += 1.0
    tp_pct = max(0.5, min(tp_pct, 8.0))
    return round(tp_pct, 2), round(trail_adj, 2)

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
            _note_error("hist_5m")
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
        _note_error("hist_5m")
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

def calculate_structural_sl(entry, direction, structure, regime_sl_mult=1.0):
    if not structure or entry <= 0:
        return None
    invalidation = structure.get("invalidation_level")
    atr = structure.get("atr")
    if invalidation is None or atr is None or atr <= 0:
        return None

    buffer = atr * float(TECH_STRUCTURE_CONFIG.get("structure_buffer_atr", 0.35)) * regime_sl_mult

    if direction == "LONG":
        raw_stop = float(invalidation) - buffer
    else:
        raw_stop = float(invalidation) + buffer

    min_sl_pct = float(TECH_STRUCTURE_CONFIG.get("min_sl_pct", 0.35))
    min_sl_atr = float(TECH_STRUCTURE_CONFIG.get("min_sl_atr", 0.55))
    min_dist_price_pct = entry * min_sl_pct / 100.0
    min_dist_price_atr = atr * min_sl_atr
    min_dist = max(min_dist_price_pct, min_dist_price_atr)

    if direction == "LONG":
        stop = min(raw_stop, entry - min_dist)
        if stop <= 0 or stop >= entry:
            return None
    else:
        stop = max(raw_stop, entry + min_dist)
        if stop <= entry:
            return None

    sl_dist = abs(entry - stop)
    sl_pct = sl_dist / entry * 100.0
    sl_atr = sl_dist / atr
    return {
        "sl_price": round(stop, 4),
        "sl_pct": sl_pct,
        "sl_atr": sl_atr,
        "buffer": buffer,
        "widened": abs(stop - raw_stop) > 1e-6,
    }

def validate_sl_bounds_only(structural_sl):
    if not structural_sl:
        return None
    sl_pct = float(structural_sl["sl_pct"])
    sl_atr = structural_sl.get("sl_atr")
    max_sl = float(TECH_STRUCTURE_CONFIG.get("max_sl_pct", 3.00))
    max_atr = float(TECH_STRUCTURE_CONFIG.get("max_sl_atr", 3.00))
    if sl_pct > max_sl:
        return None
    if sl_atr is not None and sl_atr > max_atr:
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

def estimate_ibkr_order_fees(qty, price):
    if qty <= 0 or price <= 0:
        return 0.0

    if IBKR_PRICING_MODEL == "fixed":
        commission = max(IBKR_MIN_COMMISSION, qty * IBKR_FIXED_COMMISSION)
        third_party = 0.0
    else:
        commission = max(IBKR_MIN_COMMISSION, qty * IBKR_TIERED_COMMISSION)
        clearing = min(qty * IBKR_CLEARING_PER_SHARE, IBKR_CLEARING_CAP)
        regulatory = min(qty * IBKR_REGULATORY_PER_SHARE, IBKR_REGULATORY_CAP)
        third_party = clearing + regulatory

    return round(commission + third_party + IBKR_FEE_BUFFER, 4)

def compute_min_tp_pct_for_fees(entry, qty, direction):
    if entry <= 0 or qty <= 0:
        return None

    entry_fees = estimate_ibkr_order_fees(qty, entry)
    if entry_fees <= 0:
        return None

    total_fees = entry_fees * 2.0
    total_fees_with_margin = total_fees * IBKR_FEE_MARGIN

    position_value = qty * entry
    if position_value <= 0:
        return None

    min_pct = total_fees_with_margin / position_value * 100.0
    return round(min_pct, 4)

def compute_structural_tp(entry, sl_price, direction, atr_tp_pct, candidates,
                          min_rr, qty=None, lower_mult=0.7, upper_mult=1.5,
                          max_rr=None, verbose=False):
    if atr_tp_pct is None or atr_tp_pct <= 0 or entry <= 0 or sl_price <= 0:
        return None, None
    if not candidates:
        return None, None

    sl_pct = abs(entry - sl_price) / entry * 100
    if sl_pct <= 0:
        return None, None

    ref_lo = atr_tp_pct * lower_mult
    ref_hi = atr_tp_pct * upper_mult
    min_dist_pct_rr = sl_pct * min_rr
    max_dist_pct = 8.0

    fee_min_dist_pct = 0.0
    if qty is not None and qty > 0:
        fee_min = compute_min_tp_pct_for_fees(entry, qty, direction)
        if fee_min is not None:
            fee_min_dist_pct = fee_min

    effective_min_dist_pct = max(min_dist_pct_rr, fee_min_dist_pct)

    max_dist_pct_rr_cap = None
    if max_rr is not None:
        max_dist_pct_rr_cap = sl_pct * max_rr

    lower_bound = max(effective_min_dist_pct, ref_lo)
    upper_bound = ref_hi
    if max_dist_pct_rr_cap is not None:
        upper_bound = min(upper_bound, max_dist_pct_rr_cap)
    upper_bound = min(upper_bound, max_dist_pct)
    constraints_disjoint = lower_bound > upper_bound

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

        if dist_pct < effective_min_dist_pct:
            continue
        if dist_pct > max_dist_pct:
            continue
        if max_dist_pct_rr_cap is not None and dist_pct > max_dist_pct_rr_cap:
            continue
        if not (ref_lo <= dist_pct <= ref_hi):
            continue

        valid.append((price, label, dist_pct))

    fallback_used = False
    if not valid and constraints_disjoint:
        fallback_used = True
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

            if dist_pct < effective_min_dist_pct:
                continue
            if dist_pct > max_dist_pct:
                continue
            if max_dist_pct_rr_cap is not None and dist_pct > max_dist_pct_rr_cap:
                continue
            valid.append((price, label, dist_pct))

    if not valid:
        if verbose:
            if constraints_disjoint:
                print(
                    f"     ❌ Contraintes R/R et fenêtre ATR disjointes même après fallback — "
                    f"setup structurellement infaisable "
                    f"(plancher effectif {lower_bound:.2f}% > "
                    f"plafond effectif {upper_bound:.2f}% ; "
                    f"SL {sl_pct:.2f}%, min R/R {min_rr:.1f}:1"
                    + (f", plafond R/R {max_rr:.1f}:1" if max_rr is not None else "")
                    + ")",
                    flush=True
                )
            else:
                if fee_min_dist_pct > min_dist_pct_rr:
                    constraint_msg = (
                        f"frais IBKR ({fee_min_dist_pct:.3f}%) > R/R min "
                        f"({min_dist_pct_rr:.2f}%) | SL {sl_pct:.2f}%"
                    )
                else:
                    constraint_msg = (
                        f"R/R ≥ {min_rr:.1f}:1 (SL {sl_pct:.2f}%) "
                        f"| frais IBKR ≥ {fee_min_dist_pct:.3f}%"
                    )
                extra = ""
                if max_dist_pct_rr_cap is not None:
                    extra = f" | plafond R/R {max_rr:.1f}:1 ({max_dist_pct_rr_cap:.2f}%)"
                print(
                    f"     ❌ Aucun TP structurel dans [{ref_lo:.2f}%, {ref_hi:.2f}%] "
                    f"avec {constraint_msg}{extra}",
                    flush=True
                )
        return None, None

    if fallback_used and verbose:
        print(
            f"     ⚠️ Fenêtre ATR/plafond R/R disjoints — fallback: R/R min conservé, "
            f"plancher ATR relâché", flush=True
        )

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

        if today_vol <= 0:
            return None

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

def analyze_stock(ticker, regime=None, verbose=True, reject_stats=None):
    if reject_stats is None:
        reject_stats = {}
    if regime is None:
        regime = _default_regime()
    try:
        stock = yf.Ticker(ticker, session=HTTP_SESSION)
        info = stock.info
        time.sleep(random.uniform(0.3, 0.6))
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        if not price:
            if verbose:
                print("  ❌ Données indisponibles (cote absente — limite de débit ?)", flush=True)
            reject_stats["data_missing"] = reject_stats.get("data_missing", 0) + 1
            return None
        if price < PRICE_MIN_STOCKS or price > PRICE_MAX_STOCKS:
            if verbose:
                print(f"  ❌ Prix hors limites ({price})", flush=True)
            reject_stats["price_limits"] = reject_stats.get("price_limits", 0) + 1
            return None
        quote_age = _quote_age_minutes(info)
        bid = info.get("bid")
        ask = info.get("ask")
        spread_pct = 0.0
        if bid and ask and bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            spread_pct = ((ask - bid) / mid) * 100
            if spread_pct > MAX_SPREAD_PCT:
                if verbose:
                    print(f"  ❌ Spread {spread_pct:.2f}% > {MAX_SPREAD_PCT}%", flush=True)
                reject_stats["spread"] = reject_stats.get("spread", 0) + 1
                return None
        prev_close = info.get("previousClose")
        if not prev_close or prev_close == 0:
            reject_stats["data_missing"] = reject_stats.get("data_missing", 0) + 1
            return None
        gap = ((price - prev_close) / prev_close) * 100

        gap_min_long = 0.5 + regime.get("gap_min_long_adj", 0.0)
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
            reject_stats["gap"] = reject_stats.get("gap", 0) + 1
            return None

        if direction == "LONG" and not DIRECTION_CONTROL.get("enable_longs", True):
            if verbose:
                print("  ❌ LONG désactivé via direction_control", flush=True)
            reject_stats["direction"] = reject_stats.get("direction", 0) + 1
            return None
        if direction == "SHORT" and not DIRECTION_CONTROL.get("enable_shorts", True):
            if verbose:
                print("  ❌ SHORT désactivé via direction_control", flush=True)
            reject_stats["direction"] = reject_stats.get("direction", 0) + 1
            return None
        if direction == "SHORT" and price > SHORT_PRICE_MAX_STOCK:
            if verbose:
                print(f"  ❌ SHORT: prix {price:.2f}$ > {SHORT_PRICE_MAX_STOCK:.0f}$ (limite absolue)", flush=True)
            reject_stats["price_limits"] = reject_stats.get("price_limits", 0) + 1
            return None

        volume = info.get("volume", 0)
        avg_vol = info.get("averageVolume", volume)
        vol_ratio = volume / avg_vol if avg_vol > 0 else 1

        # v4.1 — F1 : plus de rejet volume dur. Le RVOL intraday est le
        # seul juge de liquidité (correctement normalisé par construction).
        # Le point bonus pour vol_ratio > threshold reste attribué aux SHORTs
        # au-dessus de SHORT_VOL_MIN (= 0.0 désormais, donc toujours).
        # v4.5 — R7 : interrupteurs data_robustness (désactivés par défaut)
        vol_point_deferred = bool(ROBUST_CONFIG.get("rvol_for_volume_signals", False))
        free_pts = bool(ROBUST_CONFIG.get("missing_data_gives_point", True))
        if not vol_point_deferred:
            vol_threshold = SHORT_VOL_MIN if direction == "SHORT" else 0.0
            if vol_ratio > vol_threshold:
                score += 1

        float_shares = info.get("floatShares")
        if float_shares is not None and float_shares < 100_000_000:
            score += 1
        elif float_shares is None:
            reject_stats["na_float"] = reject_stats.get("na_float", 0) + 1
            if free_pts:
                score += 1
        beta = info.get("beta")
        if beta is not None and beta > 0.8:
            score += 1
        elif beta is None:
            reject_stats["na_beta"] = reject_stats.get("na_beta", 0) + 1
            if free_pts:
                score += 1
        short_ratio = info.get("shortRatio")
        if short_ratio is not None and short_ratio > 1.5:
            score += 1
        elif short_ratio is None:
            reject_stats["na_short_ratio"] = reject_stats.get("na_short_ratio", 0) + 1
            if free_pts:
                score += 1
        sma50 = info.get("fiftyDayAverage")
        if sma50:
            if (direction == "LONG" and price > sma50) or (direction == "SHORT" and price < sma50):
                score += 1
        # v4.4 — P2 : sortie anticipée. La news ne peut valoir qu'UN point
        # (+1 max) : si score + 1 < minimum, le ticker est perdu d'avance.
        timing_pen = get_timing_penalty()
        effective_score_min = min(7, SCORE_MIN_STOCKS + regime.get("score_min_stock_adj", 0) + timing_pen)
        pending_pts = 1 + (1 if vol_point_deferred else 0)   # news (+1 max) [+ point volume différé]
        if score + pending_pts < effective_score_min:
            if verbose:
                print(f"  📊 Score: {score}/7 (pré-news) < min {effective_score_min} | Gap: {gap:.2f}% | Direction: {direction}", flush=True)
            reject_stats["score"] = reject_stats.get("score", 0) + 1
            return None
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

        if score + (1 if vol_point_deferred else 0) < effective_score_min:
            if verbose:
                print(f"  📊 Score: {score}/7 < min {effective_score_min} | Gap: {gap:.2f}% | Direction: {direction}", flush=True)
            reject_stats["score"] = reject_stats.get("score", 0) + 1
            return None

        structure_hist = fetch_intraday_structure(ticker)
        rvol = calculate_intraday_rvol_from_hist(structure_hist) \
               if INTRADAY_FILTERS.get("rvol_enabled", True) else None

        if rvol is not None and rvol <= 0.01:
            rvol = None

        now_min = datetime.now(MONTREAL_TZ).hour * 60 + datetime.now(MONTREAL_TZ).minute
        if rvol is not None and now_min >= INTRADAY_FILTERS.get("rvol_apply_reject_after_min", 660):
            if rvol < INTRADAY_FILTERS.get("rvol_reject_below", 0.5):
                if verbose:
                    print(f"  ❌ RVOL intraday x{rvol:.2f} trop faible — rejet", flush=True)
                reject_stats["rvol"] = reject_stats.get("rvol", 0) + 1
                return None

        vol_signal = vol_ratio
        if vol_point_deferred:
            if rvol is None or rvol >= INTRADAY_FILTERS.get("rvol_weak_threshold", 0.8):
                score += 1
            vol_signal = rvol if rvol is not None else vol_ratio
            if score < effective_score_min:
                if verbose:
                    print(f"  📊 Score: {score}/7 < min {effective_score_min} (point volume RVOL) | Gap: {gap:.2f}% | Direction: {direction}", flush=True)
                reject_stats["score"] = reject_stats.get("score", 0) + 1
                return None

        if verbose:
            rvol_display = f"x{rvol:.2f}" if rvol is not None else "N/A"
            print(f"  📊 Score: {score}/7 | Gap: {gap:.2f}% | Vol: x{vol_ratio:.2f} | RVOL: {rvol_display} | Direction: {direction}", flush=True)

        inst_score, inst_details = calculate_institutional_interest(info, price, vol_signal, gap, direction)
        if verbose:
            print(f"     🏛️ Inst. Interest: {inst_score}/10", flush=True)

        hist_1m = fetch_intraday_1m(ticker)
        vwap, poc = compute_vwap_poc(hist_1m)
        if vwap is None or poc is None:
            reject_stats["vwap_na"] = reject_stats.get("vwap_na", 0) + 1
            vwap, poc = None, None

        cap_category = get_market_cap_category(ticker, info=info)
        exchange = get_exchange(info)
        confidence = get_confidence_score(score, vol_signal, gap, cap_category)
        held_missing = inst_details.get("held_missing", False)
        held_pct = 0.5 if held_missing else inst_details.get("held", 0.5)

        daily_ctx = get_daily_context(ticker, verbose=verbose)
        atr_pct = daily_ctx.get("atr_pct") if daily_ctx else None

        tp_ref = estimate_tp_pct_from_atr(atr_pct, gap, score, regime.get("tp_mult_adj", 1.0))
        if tp_ref is None:
            tp_ref = estimate_tp_pct_fallback(gap, score, regime.get("tp_mult_adj", 1.0))
            if verbose:
                print(f"     ⚠️ ATR indisponible — référence de distance via gap/score", flush=True)

        structure = detect_setup_structure(structure_hist, price, direction, gap, vwap, poc)
        structural_sl = calculate_structural_sl(
            price, direction, structure, regime_sl_mult=regime.get("sl_mult_adj", 1.0)
        )
        if structural_sl is None:
            if verbose:
                print("     ❌ SL structurel indisponible/invalide", flush=True)
            reject_stats["sl"] = reject_stats.get("sl", 0) + 1
            return None

        tp_ref_adj, trail_adj = adjust_risk_with_factors(
            tp_ref, spread_pct, vol_signal, cap_category, gap, held_pct
        )
        if direction == "SHORT":
            trail_adj += SHORT_TRAIL_WIDENING

        sl_final = validate_sl_bounds_only(structural_sl)
        if sl_final is None:
            if verbose:
                print(
                    f"     ❌ SL structurel hors bornes MAX : {structural_sl['sl_pct']:.2f}% "
                    f"({structural_sl.get('sl_atr', 0):.2f} ATR)", flush=True
                )
            reject_stats["sl"] = reject_stats.get("sl", 0) + 1
            return None

        if verbose and structural_sl.get("widened"):
            print(
                f"     📏 SL élargi au minimum (buffer → {structural_sl['sl_pct']:.2f}%)",
                flush=True
            )

        l2_result = calculate_synthetic_l2(
            ticker=ticker, direction=direction, current_price=price,
            spread_pct=spread_pct, vwap=vwap, poc=poc, verbose=False,
            hist=hist_1m
        )
        l2_score = l2_result["score"]
        l2_label = l2_result["label"]

        conv_label_prelim, _ = calculate_conviction(
            direction, gap, vol_signal, vwap, price, inst_score,
            regime.get("bias", "⚪ Neutral"), poc, l2_score
        )
        tp_ref_adj, tp_calib_trace = apply_tp_calibration(
            tp_ref_adj,
            direction=direction,
            regime_name=regime.get("regime", "Unknown"),
            conviction_label=conv_label_prelim,
            inst_interest=inst_score,
            atr_pct=atr_pct,
            verbose=verbose,
        )
        weak_max_rr = get_weak_setup_max_rr(conv_label_prelim, inst_score)
        if verbose and weak_max_rr is not None:
            print(f"     🔒 R/R plafonné à {weak_max_rr:.1f}:1 (setup faible)", flush=True)

        if direction == "LONG":
            sl_price_for_qty = round(price * (1 - sl_final / 100), 2)
        else:
            sl_price_for_qty = round(price * (1 + sl_final / 100), 2)
        qty_for_fees = calculate_quantity(
            price, sl_price_for_qty, CAPITAL, RISK_PER_TRADE, MAX_CAPITAL_PER_POSITION
        )

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
            qty=qty_for_fees,
            lower_mult=INTRADAY_FILTERS.get("structural_tp_atr_lower_mult", 0.40),
            upper_mult=INTRADAY_FILTERS.get("structural_tp_atr_upper_mult", 1.80),
            max_rr=weak_max_rr,
            verbose=verbose,
        )
        if tp_final is None:
            if verbose:
                print("     ❌ Setup rejeté : aucun TP structurel valide", flush=True)
            reject_stats["tp"] = reject_stats.get("tp", 0) + 1
            return None

        if tp_final <= 0 or sl_final <= 0 or (tp_final / sl_final) < (min_rr - 1e-6):
            if verbose:
                print(
                    f"     ❌ R/R final {tp_final/sl_final:.2f}:1 < min {min_rr:.1f}:1",
                    flush=True
                )
            reject_stats["rr_min"] = reject_stats.get("rr_min", 0) + 1
            return None

        if conv_label_prelim == "Low" and inst_score <= 3:
            atr_hard_cap = (atr_pct * TP_CALIBRATION.get("atr_hard_cap_mult", 1.5)) if atr_pct else 6.0
            if tp_final > atr_hard_cap:
                if verbose:
                    print(
                        f"     🚨 GARDE-FOU COHÉRENCE: TP {tp_final:.2f}% > cap ATR "
                        f"{atr_hard_cap:.2f}% (conv Low, inst {inst_score}) → rejet",
                        flush=True
                    )
                reject_stats["atr_cap"] = reject_stats.get("atr_cap", 0) + 1
                return None

        fee_min_pct = compute_min_tp_pct_for_fees(price, qty_for_fees, direction)
        if fee_min_pct is not None and tp_final < fee_min_pct:
            if verbose:
                print(
                    f"     ❌ TP ({tp_final:.2f}%) < couverture frais IBKR ({fee_min_pct:.3f}%)",
                    flush=True
                )
            reject_stats["fees"] = reject_stats.get("fees", 0) + 1
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
            fee_display = f"{fee_min_pct:.3f}%" if fee_min_pct is not None else "N/A"
            print(
                f"     🎯 TP structurel : {tp_final:.2f}% [{tp_source_label}] "
                f"| SL : {sl_final:.2f}% | R/R : {tp_final/sl_final:.2f}:1 "
                f"| frais min : {fee_display}",
                flush=True
            )

        return {
            "ticker": ticker, "exchange": exchange, "price": price, "gap": gap,
            "score": score, "vol_ratio": vol_signal, "vol_ratio_raw": vol_ratio, "cap_category": cap_category,
            "confidence": confidence, "spread_pct": spread_pct, "direction": direction,
            "tp_mult": round(tp_mult, 3), "sl_mult": round(sl_mult, 3),
            "trail_pct": round(trail, 2), "tp_pct": round(tp_final, 2),
            "sl_pct": round(sl_final, 2), "inst_interest": inst_score,
            "short_ratio": short_ratio, "vwap": vwap, "poc": poc,
            "synthetic_l2_score": l2_score, "synthetic_l2_label": l2_label,
            "atr_pct": round(atr_pct, 2) if atr_pct is not None else None,
            "rvol_intraday": round(rvol, 2) if rvol is not None else None,
            "min_rr_regime": min_rr,
            "fee_min_pct": fee_min_pct,
            "tp_source": tp_source_label,
            "setup_type": (structure or {}).get("setup_type", "N/A"),
            "structure_level": (structure or {}).get("structure_level"),
            "invalidation_level": (structure or {}).get("invalidation_level"),
            "sl_atr": round(structural_sl.get("sl_atr"), 2) if structural_sl else None,
            "sl_widened": structural_sl.get("widened", False),
            "tp_calibration": tp_calib_trace,
            "conviction_prelim": conv_label_prelim,
            "weak_setup_max_rr": weak_max_rr,
            "held_missing": held_missing,
            "quote_age_min": round(quote_age, 1) if quote_age is not None else None,
        }
    except Exception as e:
        if verbose:
            print(f"  ⚠️ Ticker indisponible: {type(e).__name__}: {e}", flush=True)
        reject_stats["exception"] = reject_stats.get("exception", 0) + 1
        return None

def analyze_etf(ticker, regime=None, reject_stats=None):
    if reject_stats is None:
        reject_stats = {}
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
                reject_stats["data_missing"] = reject_stats.get("data_missing", 0) + 1
                return None
        if price < PRICE_MIN_ETFS or price > PRICE_MAX_ETFS:
            reject_stats["price_limits"] = reject_stats.get("price_limits", 0) + 1
            return None
        quote_age = _quote_age_minutes(info)
        bid = info.get("bid")
        ask = info.get("ask")
        spread_pct = 0.0
        if bid and ask and bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            spread_pct = ((ask - bid) / mid) * 100
            if spread_pct > MAX_SPREAD_PCT:
                reject_stats["spread"] = reject_stats.get("spread", 0) + 1
                return None
        if hist.empty or len(hist) < 2:
            reject_stats["data_missing"] = reject_stats.get("data_missing", 0) + 1
            return None
        closes = hist["Close"]
        volumes = hist["Volume"]
        prev_close = closes.iloc[-2]
        if not prev_close:
            reject_stats["data_missing"] = reject_stats.get("data_missing", 0) + 1
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
            reject_stats["gap"] = reject_stats.get("gap", 0) + 1
            return None

        if direction == "LONG" and not DIRECTION_CONTROL.get("enable_longs", True):
            print(f"  ❌ ETF {ticker}: LONG désactivé via direction_control", flush=True)
            reject_stats["direction"] = reject_stats.get("direction", 0) + 1
            return None
        if direction == "SHORT" and not DIRECTION_CONTROL.get("enable_shorts", True):
            print(f"  ❌ ETF {ticker}: SHORT désactivé via direction_control", flush=True)
            reject_stats["direction"] = reject_stats.get("direction", 0) + 1
            return None
        if direction == "SHORT" and price > SHORT_PRICE_MAX_ETF:
            print(f"  ❌ ETF {ticker}: SHORT prix {price:.2f}$ > {SHORT_PRICE_MAX_ETF:.0f}$", flush=True)
            reject_stats["price_limits"] = reject_stats.get("price_limits", 0) + 1
            return None

        etf_vol_deferred = bool(ROBUST_CONFIG.get("rvol_for_volume_signals", False))
        if not etf_vol_deferred and vol_ratio > 0.3:
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

        # v4.4 — P2 : filtre de score AVANT le téléchargement de structure 5 min
        timing_pen = get_timing_penalty()
        effective_score_min = min(5, SCORE_MIN_ETFS + regime.get("score_min_etf_adj", 0) + timing_pen)
        if score + (1 if etf_vol_deferred else 0) < effective_score_min:
            reject_stats["score"] = reject_stats.get("score", 0) + 1
            return None

        structure_hist = fetch_intraday_structure(ticker)
        rvol = calculate_intraday_rvol_from_hist(structure_hist) \
               if INTRADAY_FILTERS.get("rvol_enabled", True) else None

        if rvol is not None and rvol <= 0.01:
            rvol = None

        now_min = datetime.now(MONTREAL_TZ).hour * 60 + datetime.now(MONTREAL_TZ).minute
        if rvol is not None and now_min >= INTRADAY_FILTERS.get("rvol_apply_reject_after_min", 660):
            if rvol < INTRADAY_FILTERS.get("rvol_reject_below", 0.5):
                print(f"  ❌ ETF {ticker}: RVOL intraday x{rvol:.2f} trop faible", flush=True)
                reject_stats["rvol"] = reject_stats.get("rvol", 0) + 1
                return None

        vol_signal = vol_ratio
        if etf_vol_deferred:
            if rvol is None or rvol >= INTRADAY_FILTERS.get("rvol_weak_threshold", 0.8):
                score += 1
            vol_signal = rvol if rvol is not None else vol_ratio
            if score < effective_score_min:
                reject_stats["score"] = reject_stats.get("score", 0) + 1
                return None

        exchange = get_exchange(info)
        confidence = get_confidence_score(score, vol_signal, gap, "Large Cap")
        inst_score, inst_details = calculate_institutional_interest(info, price, vol_signal, gap, direction)
        hist_1m = fetch_intraday_1m(ticker)
        vwap, poc = compute_vwap_poc(hist_1m)
        if vwap is None or poc is None:
            reject_stats["vwap_na"] = reject_stats.get("vwap_na", 0) + 1
            vwap, poc = None, None
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
        structural_sl = calculate_structural_sl(
            price, direction, structure, regime_sl_mult=regime.get("sl_mult_adj", 1.0)
        )
        if structural_sl is None:
            print(f"  ❌ ETF {ticker}: SL structurel indisponible/invalide", flush=True)
            reject_stats["sl"] = reject_stats.get("sl", 0) + 1
            return None

        held_missing = inst_details.get("held_missing", False)
        held_pct = 0.5 if held_missing else inst_details.get("held", 0.5)
        tp_ref_adj, trail_adj = adjust_risk_with_factors(
            tp_ref, spread_pct, vol_signal, "Large Cap", gap, held_pct
        )
        if direction == "SHORT":
            trail_adj += SHORT_TRAIL_WIDENING

        sl_final = validate_sl_bounds_only(structural_sl)
        if sl_final is None:
            print(
                f"  ❌ ETF {ticker}: SL structurel hors bornes MAX "
                f"{structural_sl['sl_pct']:.2f}% ({structural_sl.get('sl_atr', 0):.2f} ATR)", flush=True
            )
            reject_stats["sl"] = reject_stats.get("sl", 0) + 1
            return None

        l2_result = calculate_synthetic_l2(
            ticker=ticker, direction=direction, current_price=price,
            spread_pct=spread_pct, vwap=vwap, poc=poc, verbose=False,
            hist=hist_1m
        )
        l2_score = l2_result["score"]
        l2_label = l2_result["label"]

        conv_label_prelim, _ = calculate_conviction(
            direction, gap, vol_signal, vwap, price, inst_score,
            regime.get("bias", "⚪ Neutral"), poc, l2_score
        )
        tp_ref_adj, tp_calib_trace = apply_tp_calibration(
            tp_ref_adj,
            direction=direction,
            regime_name=regime.get("regime", "Unknown"),
            conviction_label=conv_label_prelim,
            inst_interest=inst_score,
            atr_pct=atr_pct,
            verbose=False,
        )
        weak_max_rr = get_weak_setup_max_rr(conv_label_prelim, inst_score)

        if direction == "LONG":
            sl_price_for_qty = round(price * (1 - sl_final / 100), 2)
        else:
            sl_price_for_qty = round(price * (1 + sl_final / 100), 2)
        qty_for_fees = calculate_quantity(
            price, sl_price_for_qty, CAPITAL, RISK_PER_TRADE, MAX_CAPITAL_PER_POSITION
        )

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
            qty=qty_for_fees,
            lower_mult=INTRADAY_FILTERS.get("structural_tp_atr_lower_mult", 0.40),
            upper_mult=INTRADAY_FILTERS.get("structural_tp_atr_upper_mult", 1.80),
            max_rr=weak_max_rr,
            verbose=False,
        )
        if tp_final is None:
            print(f"  ❌ ETF {ticker}: aucun TP structurel valide (R/R ou frais IBKR)", flush=True)
            reject_stats["tp"] = reject_stats.get("tp", 0) + 1
            return None

        if tp_final <= 0 or sl_final <= 0 or (tp_final / sl_final) < (min_rr - 1e-6):
            print(
                f"  ❌ ETF {ticker}: R/R final {tp_final/sl_final:.2f}:1 < min {min_rr:.1f}:1",
                flush=True
            )
            reject_stats["rr_min"] = reject_stats.get("rr_min", 0) + 1
            return None

        if conv_label_prelim == "Low" and inst_score <= 3:
            atr_hard_cap = (atr_pct * TP_CALIBRATION.get("atr_hard_cap_mult", 1.5)) if atr_pct else 6.0
            if tp_final > atr_hard_cap:
                print(
                    f"  ❌ ETF {ticker}: garde-fou cohérence TP {tp_final:.2f}% > cap ATR "
                    f"{atr_hard_cap:.2f}% (conv Low, inst {inst_score})", flush=True
                )
                reject_stats["atr_cap"] = reject_stats.get("atr_cap", 0) + 1
                return None

        fee_min_pct = compute_min_tp_pct_for_fees(price, qty_for_fees, direction)
        if fee_min_pct is not None and tp_final < fee_min_pct:
            print(
                f"  ❌ ETF {ticker}: TP ({tp_final:.2f}%) < couverture frais IBKR ({fee_min_pct:.3f}%)",
                flush=True
            )
            reject_stats["fees"] = reject_stats.get("fees", 0) + 1
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
            "score": score, "vol_ratio": vol_signal, "vol_ratio_raw": vol_ratio,
            "aum_m": round(aum / 1_000_000, 1) if aum else 0,
            "confidence": confidence, "spread_pct": spread_pct, "direction": direction,
            "tp_mult": round(tp_mult, 3), "sl_mult": round(sl_mult, 3),
            "trail_pct": round(trail, 2), "tp_pct": round(tp_final, 2),
            "sl_pct": round(sl_final, 2), "inst_interest": inst_score,
            "atr_pct": round(atr_pct, 2) if atr_pct is not None else None,
            "rvol_intraday": round(rvol, 2) if rvol is not None else None,
            "min_rr_regime": min_rr,
            "fee_min_pct": fee_min_pct,
            "tp_source": tp_source_label,
            "short_ratio": short_ratio, "vwap": vwap, "poc": poc,
            "synthetic_l2_score": l2_score, "synthetic_l2_label": l2_label,
            "setup_type": (structure or {}).get("setup_type", "N/A"),
            "structure_level": (structure or {}).get("structure_level"),
            "invalidation_level": (structure or {}).get("invalidation_level"),
            "sl_atr": round(structural_sl.get("sl_atr"), 2) if structural_sl else None,
            "sl_widened": structural_sl.get("widened", False),
            "tp_calibration": tp_calib_trace,
            "conviction_prelim": conv_label_prelim,
            "weak_setup_max_rr": weak_max_rr,
            "held_missing": held_missing,
            "quote_age_min": round(quote_age, 1) if quote_age is not None else None,
        }
    except Exception as e:
        print(f"  ⚠️ ETF indisponible ({ticker}): {type(e).__name__}: {e}", flush=True)
        reject_stats["exception"] = reject_stats.get("exception", 0) + 1
        return None

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

def compute_position_size_pct(verdict, conviction, rank="1/1"):
    """v4.6 — palier de taille (% de la quantité maximale autorisée).
    Le VERDICT fixe le palier ; une CONVICTION Low retire un cran ; un RANK 2/2
    est plafonné. Indépendant du régime, du biais de marché et de la direction."""
    cfg = SIZING_CONFIG
    if not cfg.get("enabled", True):
        return 100.0, "sizing désactivé"
    tiers = [float(x) for x in cfg.get("tiers_pct", [33, 67, 100])]
    idx = {"Mixed": 0, "Favorable": 1, "Strong": 2}.get(verdict, 0)
    reason = verdict
    if conviction == "Low":
        idx = max(0, idx - int(cfg.get("low_conviction_notches", 1)))
        reason += " + Low conviction"
    pct = tiers[min(idx, len(tiers) - 1)]
    try:
        rank_pos = int(str(rank).split("/")[0])
    except Exception:
        rank_pos = 1
    cap = float(cfg.get("rank2_cap_pct", 67))
    if rank_pos >= 2 and pct > cap:
        pct = cap
        reason += f" + rank {rank}"
    return pct, reason

def _grade(data, bias):
    """VERDICT et CONVICTION d'un candidat (mêmes calculs que le message Telegram)."""
    verdict = get_verdict(data["confidence"])[0]
    conv, _ = calculate_conviction(
        data["direction"], data["gap"], data["vol_ratio"], data.get("vwap"), data["price"],
        data["inst_interest"], bias, data.get("poc"), data.get("synthetic_l2_score", 50)
    )
    return verdict, conv

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

    base_qty = calculate_quantity(entry, sl, CAPITAL, RISK_PER_TRADE, MAX_CAPITAL_PER_POSITION)
    unit_label = "shares" if not is_etf else "units"

    if direction == "LONG":
        trail_price = round(entry * (1 - trail_pct / 100), 2)
    else:
        trail_price = round(entry * (1 + trail_pct / 100), 2)

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

    # v4.6 — Q1/Q2 : quantité = palier x quantité maximale autorisée
    size_pct, size_reason = compute_position_size_pct(verdict_text, conv_label, rank)
    qty = int(base_qty * size_pct / 100.0)
    if base_qty > 0:
        qty = max(1, qty)

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
    msg += f"  📊 R/R → {rr_tp:.1f}:1 | Min. régime: {min_rr:.1f}:1\n"

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

def _reset_reject_stats():
    return {
        "price_limits": 0, "spread": 0, "gap": 0, "vol_ratio": 0,
        "rvol": 0, "score": 0, "sl": 0, "tp": 0, "rr_min": 0,
        "fees": 0, "atr_cap": 0, "direction": 0, "exception": 0, "data_missing": 0,
        "vwap_na": 0, "na_float": 0, "na_beta": 0, "na_short_ratio": 0,
    }

def _print_reject_stats(stats, label):
    info_keys = {"vwap_na", "na_float", "na_beta", "na_short_ratio"}
    rej = {k: v for k, v in stats.items() if v > 0 and k not in info_keys}
    gaps = {k: v for k, v in stats.items() if v > 0 and k in info_keys}
    if rej:
        detail = " ".join(f"{k}={v}" for k, v in rej.items())
        print(f"  📊 Rejets {label}: {detail}", flush=True)
    if gaps:
        detail = " ".join(f"{k}={v}" for k, v in gaps.items())
        print(f"  📉 Données manquantes {label} (non-rejets): {detail}", flush=True)

def _select_best_per_direction(stocks_results, etfs_results, market_bias):
    """v4.1 — F3 (legacy, non utilisée depuis v4.2).
    Conservée pour référence : remplacée dans main() par
    _select_top_candidates_with_diversity_rules."""
    best_long = None
    best_long_is_etf = False
    best_long_ps = float("-inf")

    best_short = None
    best_short_is_etf = False
    best_short_ps = float("-inf")

    for cand in stocks_results:
        ps = calculate_priority_score(cand, market_bias, False)
        if cand["direction"] == "LONG" and ps > best_long_ps:
            best_long, best_long_is_etf, best_long_ps = cand, False, ps
        elif cand["direction"] == "SHORT" and ps > best_short_ps:
            best_short, best_short_is_etf, best_short_ps = cand, False, ps

    for cand in etfs_results:
        ps = calculate_priority_score(cand, market_bias, True)
        if cand["direction"] == "LONG" and ps > best_long_ps:
            best_long, best_long_is_etf, best_long_ps = cand, True, ps
        elif cand["direction"] == "SHORT" and ps > best_short_ps:
            best_short, best_short_is_etf, best_short_ps = cand, True, ps

    selected_items = []
    if best_long is not None:
        selected_items.append((best_long, best_long_is_etf))
    if best_short is not None:
        selected_items.append((best_short, best_short_is_etf))
    return selected_items

def _select_top_candidates_with_diversity_rules(stocks_results, etfs_results, market_bias):
    """v4.3 — Sélection top-down stricte avec règles de diversité définitives.

    Règles absolues :
      - JAMAIS 2 setups de même TYPE (2 stocks ou 2 ETFs), quelles que
        soient leurs directions.
      - JAMAIS 2 setups de même DIRECTION (2 LONGs ou 2 SHORTs), quels
        que soient leurs types.
      - Le SEUL cas où 2 setups sont envoyés :
          1 stock + 1 ETF ET directions opposées (LONG + SHORT).
      - Dans TOUS les autres cas : envoyer uniquement le TOP 1.
    """
    scored = []
    for c in stocks_results:
        scored.append((calculate_priority_score(c, market_bias, False), c, False))
    for c in etfs_results:
        scored.append((calculate_priority_score(c, market_bias, True), c, True))

    if not scored:
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    best_ps, best, best_is_etf = scored[0]

    if len(scored) == 1:
        print(f"     🎯 1 seul candidat → single setup : {best['ticker']} {best['direction']}", flush=True)
        return [(best, best_is_etf)]

    second_ps, second, second_is_etf = scored[1]
    type_ok = (best_is_etf != second_is_etf)
    direction_ok = (best["direction"] != second["direction"])

    if type_ok and direction_ok:
        print(
            f"     🔀 Top 2 retenus (1 stock + 1 ETF, directions opposées) : "
            f"{best['ticker']} {best['direction']} ({best_ps:.1f}) + "
            f"{second['ticker']} {second['direction']} ({second_ps:.1f})",
            flush=True
        )
        return [(best, best_is_etf), (second, second_is_etf)]

    if not type_ok and not direction_ok:
        reason = "même type ET même direction"
    elif not type_ok:
        reason = "même type (2 stocks ou 2 ETFs) — interdit même si directions opposées"
    else:
        reason = "même direction (2 LONGs ou 2 SHORTs)"

    print(
        f"     🔀 Top 2 refusé ({reason}) → single setup : "
        f"{best['ticker']} {best['direction']} ({best_ps:.1f}) "
        f"[2e écarté : {second['ticker']} {second['direction']} ({second_ps:.1f})]",
        flush=True
    )
    return [(best, best_is_etf)]

def requote_selected(selected_items):
    """v4.5 — re-cote les setups retenus juste avant l'envoi (au plus 2 appels).
    N'altère ni l'entrée ni le SL/TP : renseigne price_now / drift_pct pour
    que le log signale une dérive de prix depuis le scan (le message Telegram est inchangé)."""
    if not ROBUST_CONFIG.get("requote_before_send", True):
        return
    for data, _is_etf in selected_items:
        try:
            info = yf.Ticker(data["ticker"], session=HTTP_SESSION).info
            p = info.get("regularMarketPrice") or info.get("currentPrice")
            if p and data.get("price", 0) > 0:
                data["price_now"] = float(p)
                data["drift_pct"] = (float(p) - data["price"]) / data["price"] * 100.0
        except Exception:
            _note_error("requote")

def _fmt_min(total):
    return f"{total // 60:02d}:{total % 60:02d}"

def wait_until_minute(target_total_min):
    """v4.5 — attend jusqu'à l'heure cible (minutes depuis minuit, heure de
    Montréal). Contrairement à wait_until_target, ne reporte JAMAIS la cible
    de 60 minutes quand elle est déjà passée."""
    now = datetime.now(MONTREAL_TZ)
    cur = now.hour * 60 + now.minute
    print(f"⏳ Attente jusqu'à {_fmt_min(target_total_min)}... ({target_total_min - cur} min)", flush=True)
    last_heartbeat = datetime.now(MONTREAL_TZ)
    while True:
        now = datetime.now(MONTREAL_TZ)
        if now.hour * 60 + now.minute >= target_total_min:
            return
        time.sleep(30)
        now = datetime.now(MONTREAL_TZ)
        if (now - last_heartbeat).total_seconds() >= 300:
            remaining = target_total_min - (now.hour * 60 + now.minute)
            print(f"💤 ... encore {remaining} min avant {_fmt_min(target_total_min)}", flush=True)
            last_heartbeat = now

def run_scan(now, session):
    """v4.5 — un scan complet, extrait de main() pour pouvoir être isolé par un
    try/except : une erreur ici n'empêche plus les créneaux suivants."""
    print(f"\n📊 Scan à {now.strftime('%H:%M')} (session {session})", flush=True)
    t_scan0 = time.time()
    _reset_data_errors()

    print("\n🧭 ================================", flush=True)
    print("🧭 DÉTECTION DE RÉGIME DE MARCHÉ", flush=True)
    print("🧭 ================================", flush=True)
    regime = detect_market_regime(verbose=True)
    market_bias = regime["bias"]
    t_regime = time.time()
    n_rss = refresh_rss_cache()
    print(f"📰 Cache RSS : {n_rss} articles < 6 h", flush=True)

    stocks_reject = _reset_reject_stats()
    stocks_results = []
    for ticker in STOCK_TICKERS:
        print(f"  - {ticker}:", flush=True)
        data = analyze_stock(ticker, regime=regime, verbose=True, reject_stats=stocks_reject)
        if data:
            stocks_results.append(data)
            l2_display = f"L2:{data.get('synthetic_l2_score', 50):.0f}"
            print(f"    ✅ Score {data['score']}/7 | {data['direction']} | TP: {data['tp_pct']}% [{data.get('tp_source','')}] | SL: {data['sl_pct']}% | RVOL: {data.get('rvol_intraday')} | {l2_display}", flush=True)
        else:
            print("    ❌", flush=True)
    _print_reject_stats(stocks_reject, "STOCKS")
    t_stocks = time.time()

    etfs_reject = _reset_reject_stats()
    etfs_results = []
    for ticker in ETF_TICKERS:
        print(f"  - {ticker}...", end=" ", flush=True)
        data = analyze_etf(ticker, regime=regime, reject_stats=etfs_reject)
        if data:
            etfs_results.append(data)
            l2_display = f"L2:{data.get('synthetic_l2_score', 50):.0f}"
            print(f"✅ Score {data['score']}/5 | {data['direction']} | TP: {data['tp_pct']}% [{data.get('tp_source','')}] | SL: {data['sl_pct']}% | RVOL: {data.get('rvol_intraday')} | {l2_display}", flush=True)
        else:
            print("❌", flush=True)
    _print_reject_stats(etfs_reject, "ETFS")
    t_etfs = time.time()
    _print_data_errors()

    ages = sorted(r["quote_age_min"] for r in (stocks_results + etfs_results) if r.get("quote_age_min") is not None)
    if ages:
        print(f"🕒 Âge des cotes (candidats) : min {ages[0]:.0f} | médiane {ages[len(ages)//2]:.0f} | max {ages[-1]:.0f} min", flush=True)

    print(f"🧠 SYNTHETIC L2 déjà intégré au pipeline (calculé pré-calibration TP).", flush=True)

    # v4.3 — F5 : sélection top-down stricte avec règles de diversité
    selected_items = _select_top_candidates_with_diversity_rules(
        stocks_results, etfs_results, market_bias
    )
    requote_selected(selected_items)   # v4.5 — R6
    for _d, _e in selected_items:      # v4.7 : information dans les LOGS uniquement (messages Telegram inchangés)
        _age, _dr = _d.get("quote_age_min"), _d.get("drift_pct")
        if _age is None and _dr is None:
            continue
        _flags = []
        if _age is not None and _age >= ROBUST_CONFIG.get("quote_warn_after_min", 20):
            _flags.append(f"cote âgée de {_age:.0f} min")
        if _dr is not None and abs(_dr) >= ROBUST_CONFIG.get("drift_warn_pct", 0.30):
            _flags.append(f"dérive {_dr:+.2f}% depuis le scan (prix actuel {_d.get('price_now', 0):.2f})")
        _age_txt = f"{_age:.0f} min" if _age is not None else "n/d"
        _dr_txt = f"{_dr:+.2f}%" if _dr is not None else "n/d"
        print(f"  🕒 {_d['ticker']}: âge de cote {_age_txt} | dérive depuis le scan {_dr_txt}" + (" ⚠️ " + ", ".join(_flags) if _flags else ""), flush=True)

    # v4.6 — Q3 : répartition Verdict x Conviction des candidats (calibration)
    grades = {}
    tiers = {}
    for cand in stocks_results + etfs_results:
        v, c = _grade(cand, market_bias)
        grades[f"{v}/{c}"] = grades.get(f"{v}/{c}", 0) + 1
        pct, _r = compute_position_size_pct(v, c, "1/1")
        tiers[f"{pct:.0f}%"] = tiers.get(f"{pct:.0f}%", 0) + 1
    if grades:
        print("📈 Candidats par Verdict/Conviction : " + " ".join(f"{k}={n}" for k, n in sorted(grades.items())), flush=True)
        print("📐 Paliers de taille (rang 1/1) : " + " ".join(f"{k}={n}" for k, n in sorted(tiers.items(), reverse=True)), flush=True)

    now_scan = datetime.now(MONTREAL_TZ)
    header = (
        "🤖 <b>NorthSentinel CA Only</b>™\n"
        "<i>Canadian intraday trading signals. Long & Short. Manual execution.</i>\n"
        f"📅 {now_scan.strftime('%Y-%m-%d %H:%M')} (Montreal) | Scanned: {len(STOCK_TICKERS)} Stocks, {len(ETF_TICKERS)} ETFs\n"
        f"Capital: ${CAPITAL:,.0f} (Paper Trading Account)\n"
        "═══════════════════════\n\n"
    )
    msg = header

    if selected_items:
        total_selected = len(selected_items)
        for idx, (selected, is_etf) in enumerate(selected_items, start=1):
            rank = f"{idx}/{total_selected}"
            msg += build_setup_message(
                selected, is_etf=is_etf, bias=market_bias, rank=rank, regime=regime
            )
            _v, _c = _grade(selected, market_bias)
            _pct, _why = compute_position_size_pct(_v, _c, rank)
            print(f"  📐 {selected['ticker']}: {_why} / conviction {_c} / rang {rank} → taille {_pct:.0f}%", flush=True)
            if idx < total_selected:
                msg += "\n"
    else:
        regime_name = regime.get("regime", "Unknown")
        volatility = regime.get("volatility", "Normal")
        adx = regime.get("adx")
        adx_display = f"{adx:.1f}" if isinstance(adx, (int, float)) else "N/A"
        msg += "ℹ️ <b>No valid setup for this scan.</b>\n"
        msg += f"  🧭 Regime: {regime_name} | Vol: {volatility} | ADX: {adx_display}\n"
        msg += f"  Market Bias: {market_bias}\n"
        msg += f"  Tickers evaluated: {len(STOCK_TICKERS)} stocks, {len(ETF_TICKERS)} ETFs\n"
        msg += "  All candidates rejected by filters (gap, RVOL, structure SL, structural TP, minimum R/R, or IBKR fee coverage).\n"

    msg += "\n━━━━━━━━━━━━━━━━━\n\n"
    msg += "<i>Informational automated signal. Not financial or trading advice.</i>"
    send_telegram(msg)
    t_end = time.time()
    print(
        f"⏱️ Durée scan : régime {t_regime - t_scan0:.0f}s | stocks (+RSS) {t_stocks - t_regime:.0f}s | "
        f"ETFs {t_etfs - t_stocks:.0f}s | sélection+Telegram {t_end - t_etfs:.0f}s | "
        f"TOTAL {t_end - t_scan0:.0f}s",
        flush=True
    )

def main():
    now = datetime.now(MONTREAL_TZ)
    heure = now.hour
    minute = now.minute

    if is_ca_market_closed(now):
        print("🏖️ Marché CA fermé – Arrêt.", flush=True)
        return

    early_close = is_early_close(now)
    early_hour = get_early_close_hour(now) if early_close else None
    if early_close:
        print(f"⚠️ Fermeture anticipée – Marché ferme à {early_hour}:00 ET.", flush=True)

    if 9 <= heure <= 11 and (heure < 11 or minute <= 35):
        session = "morning"
        scan_hours = [9, 10, 11]
        scan_minutes = [45, 30, 15]
        print("☀️ Session MATIN détectée – Scans à 09:45, 10:30, 11:15.", flush=True)
    elif 14 <= heure <= 15 and (heure < 15 or minute <= 15):
        session = "afternoon"
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

    # v4.5 — R5 : planification par créneaux avec rattrapage
    slots = [h * 60 + m for h, m in zip(scan_hours, scan_minutes)]
    grace = int(SCHED_CONFIG.get("catchup_grace_min", 12))
    done = set()
    print(f"🗓️ Créneaux : {', '.join(_fmt_min(x) for x in slots)} (rattrapage jusqu'à {grace} min de retard)", flush=True)

    while True:
        now = datetime.now(MONTREAL_TZ)
        cur = now.hour * 60 + now.minute

        for sl in slots:
            if sl not in done and cur > sl + grace:
                done.add(sl)
                print(f"⚠️ Créneau {_fmt_min(sl)} MANQUÉ (il est {now.strftime('%H:%M')}, au-delà de {grace} min de rattrapage).", flush=True)
                if SCHED_CONFIG.get("notify_missed_slot", False):
                    send_telegram(
                        "🤖 <b>NorthSentinel CA Only</b>™\n"
                        f"<i>⚠️ Scan slot {_fmt_min(sl)} skipped — bot woke up at {now.strftime('%H:%M')} (ET), "
                        f"beyond the {grace}-min catch-up window.</i>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "<i>Informational automated signal. Not financial or trading advice.</i>"
                    )

        pending = [x for x in slots if x not in done]
        if not pending:
            print("⏹️ Tous les créneaux sont traités – Fin de session.", flush=True)
            send_session_end_message(now, session)
            break

        nxt = pending[0]
        if cur < nxt:
            wait_until_minute(nxt)
            continue

        done.add(nxt)
        late = cur - nxt
        if late > 0:
            print(f"🔁 Rattrapage du créneau {_fmt_min(nxt)} (démarrage avec {late} min de retard).", flush=True)
        try:
            run_scan(now, session)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"❌ Scan {_fmt_min(nxt)} interrompu : {type(e).__name__}: {e} — passage au créneau suivant.", flush=True)
            if SCHED_CONFIG.get("notify_scan_failure", False):
                send_telegram(
                    "🤖 <b>NorthSentinel CA Only</b>™\n"
                    f"<i>⚠️ Scan {_fmt_min(nxt)} failed ({type(e).__name__}). The next slot will still run.</i>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "<i>Informational automated signal. Not financial or trading advice.</i>"
                )

if __name__ == "__main__":
    main()
