# ============================================================
# NORTHSENTINEL PRO — MODULE INSTITUTIONAL FLOW
# Détection absorption, breakout et distribution
# via Polygon.io aggs 1min + snapshots
# ============================================================
from pro_polygon_client import get_aggs_minute, get_snapshot


def detect_institutional_flow(ticker):
    """
    Analyse les 10 dernières minutes pour détecter :
    - Absorption : volume surge + prix stable = institution accumule
    - Breakout : volume surge + prix en hausse rapide = institution pousse
    - Distribution : volume surge + prix en baisse = institution liquide
    """
    aggs = get_aggs_minute(ticker, limit=10)
    
    if aggs is None or len(aggs) < 5:
        return {'flow': 'no_data', 'line': ''}
    
    # Calculer le volume moyen sur les 10 dernières minutes
    volumes = [bar.get('v', 0) for bar in aggs]
    avg_volume = sum(volumes) / len(volumes) if volumes else 0
    
    # Prendre la dernière barre (minute en cours)
    last = aggs[0]
    last_volume = last.get('v', 0)
    last_open = last.get('o', 0)
    last_close = last.get('c', 0)
    
    if last_open == 0 or avg_volume == 0:
        return {'flow': 'no_data', 'line': ''}
    
    price_change = (last_close - last_open) / last_open * 100
    volume_ratio = last_volume / avg_volume if avg_volume > 0 else 0
    
    # Détection
        if volume_ratio > 2.0:
            if -0.1 <= price_change <= 0.1:
                flow = "absorption"
                comment = "🟢 High volume — price stable"
            elif price_change > 0.5:
                flow = "breakout"
                comment = "🟢 High volume — price rising"
            elif price_change < -0.3:
                flow = "distribution"
                comment = "🔴 High volume — price declining"
            else:
                flow = "neutral"
                comment = "⚪ High volume — no clear direction"
        elif volume_ratio > 1.5:
            if price_change > 0.3:
                flow = "buying"
                comment = "🟡 Volume rising — price up"
            elif price_change < -0.2:
                flow = "selling"
                comment = "🟠 Volume rising — price down"
            else:
                flow = "neutral"
                comment = "⚪ Normal flow"
        else:
            flow = "normal"
            comment = "⚪ Normal flow"
    
    line = f"  🏦 Flow: {comment}\n" if flow != "normal" and flow != "no_data" else ""
    
    return {
        'flow': flow,
        'line': line
    }
