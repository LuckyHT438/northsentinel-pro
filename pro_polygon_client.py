# ============================================================
# NORTHSENTINEL PRO — CLIENT POLYGON.IO
# Gère les appels API avec limite 5 appels/min (Basic plan)
# ============================================================
import requests
import time
import os

POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
BASE_URL = "https://api.polygon.io"

# Compteur pour respecter la limite 5 appels/min
_call_timestamps = []

def _respect_rate_limit():
    """Bloque si 5 appels ont été faits dans la dernière minute"""
    global _call_timestamps
    now = time.time()
    # Nettoie les timestamps de plus d'une minute
    _call_timestamps = [t for t in _call_timestamps if now - t < 60]
    
    if len(_call_timestamps) >= 5:
        wait_time = 60 - (now - _call_timestamps[0]) + 1
        print(f"⏸️ Polygon rate limit — waiting {wait_time:.0f}s")
        time.sleep(wait_time)
    
    _call_timestamps.append(time.time())


def get_snapshot(ticker):
    """Snapshot L1: prix, bid/ask, spread, volume"""
    if not POLYGON_API_KEY:
        print("⚠️ Polygon API key missing")
        return None
    
    _respect_rate_limit()
    
    try:
        url = f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
        params = {"apiKey": POLYGON_API_KEY}
        r = requests.get(url, params=params, timeout=5)
        
        if r.status_code == 200:
            data = r.json()
            ticker_data = data.get("ticker", {})
            day = ticker_data.get("day", {})
            last_trade = ticker_data.get("lastTrade", {})
            
            return {
                "price": last_trade.get("p"),
                "bid": last_trade.get("b"),
                "ask": last_trade.get("a"),
                "spread": round((last_trade.get("a", 0) - last_trade.get("b", 0)) / last_trade.get("a", 1) * 100, 2) if last_trade.get("a") and last_trade.get("b") else None,
                "volume": day.get("v"),
                "vwap": day.get("vw"),
                "open": day.get("o"),
                "high": day.get("h"),
                "low": day.get("l"),
                "close": day.get("c")
            }
        else:
            print(f"⚠️ Polygon snapshot error {r.status_code}: {r.text[:100]}")
            return None
    except Exception as e:
        print(f"❌ Polygon snapshot error: {e}")
        return None


def get_aggs_minute(ticker, limit=30):
    """Agrégats 1min pour cumulative delta"""
    if not POLYGON_API_KEY:
        print("⚠️ Polygon API key missing")
        return None
    
    _respect_rate_limit()
    
    try:
        url = f"{BASE_URL}/v2/aggs/ticker/{ticker}/range/1/minute?limit={limit}&sort=desc"
        params = {"apiKey": POLYGON_API_KEY}
        r = requests.get(url, params=params, timeout=5)
        
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            return results  # Liste de {o, h, l, c, v, vw, t, n}
        else:
            print(f"⚠️ Polygon aggs error {r.status_code}: {r.text[:100]}")
            return None
    except Exception as e:
        print(f"❌ Polygon aggs error: {e}")
        return None
