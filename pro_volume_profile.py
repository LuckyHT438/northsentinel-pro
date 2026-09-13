# ============================================================
# NORTHSENTINEL PRO — MODULE VOLUME PROFILE
# VWAP, POC et positionnement prix depuis yfinance (gratuit)
# VERSION DIRECTION-AWARE (2026-09-13)
# ============================================================
import yfinance as yf
import numpy as np

def calculate_vwap(ticker):
    """VWAP session courante depuis données 1min"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d", interval="1m")
        if hist.empty or len(hist) < 10:
            return None
        typical_price = (hist['High'] + hist['Low'] + hist['Close']) / 3
        vwap = (typical_price * hist['Volume']).sum() / hist['Volume'].sum()
        return round(vwap, 2)
    except:
        return None

def calculate_poc(ticker):
    """Point of Control — prix avec le plus de volume"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d", interval="1m")
        if hist.empty or len(hist) < 10:
            return None
        price_levels = hist['Close'].round(2)
        volume_by_price = hist.groupby(price_levels)['Volume'].sum()
        poc = volume_by_price.idxmax()
        return round(poc, 2)
    except:
        return None

def get_volume_profile(ticker, current_price, direction="LONG"):
    """
    Fonction principale appelée par le script Pro/Scanner.
    direction : "LONG" ou "SHORT" — adapte le verdict au sens du trade.
    """
    vwap = calculate_vwap(ticker)
    poc = calculate_poc(ticker)

    if vwap is None or poc is None:
        return {'vwap': None, 'poc': None, 'line': ''}

    distance_to_poc = abs(current_price - poc) / poc * 100
    near_poc = distance_to_poc < 1.0

    if direction == "LONG":
        aligned = current_price > vwap
        if aligned and near_poc:
            comment = "🟢 Above VWAP + Near POC — strong"
        elif aligned:
            comment = "🟡 Above VWAP, far from POC"
        elif near_poc:
            comment = "🟡 Below VWAP, near POC"
        else:
            comment = "🔴 Below VWAP + Far from POC — weak"
    else:  # SHORT
        aligned = current_price < vwap
        if aligned and near_poc:
            comment = "🟢 Below VWAP + Near POC — strong"
        elif aligned:
            comment = "🟡 Below VWAP, far from POC"
        elif near_poc:
            comment = "🟡 Above VWAP, near POC"
        else:
            comment = "🔴 Above VWAP + Far from POC — weak"

    line = f"  🏦 VWAP: ${vwap} | POC: ${poc}\n  📐 {comment}\n"

    return {
        'vwap': vwap,
        'poc': poc,
        'line': line
    }
