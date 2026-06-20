# ============================================================
# NORTHSENTINEL PRO — MODULE CUMULATIVE DELTA
# Delta acheteur/vendeur via Polygon.io aggs 1min
# ============================================================
from pro_polygon_client import get_aggs_minute


def calculate_cumulative_delta(ticker):
    """
    Calcule le delta cumulé (volume achat - volume vente) sur les 30 dernières minutes.
    Approximation : si prix close > prix open → volume = achat, sinon vente.
    Retourne un dict avec delta, direction et commentaire.
    """
    aggs = get_aggs_minute(ticker, limit=30)
    
    if aggs is None or len(aggs) < 5:
        return {'delta': None, 'line': ''}
    
    delta = 0
    for bar in aggs:
        volume = bar.get('v', 0)
        open_price = bar.get('o', 0)
        close_price = bar.get('c', 0)
        
        if close_price > open_price:
            delta += volume      # Achat
        else:
            delta -= volume      # Vente
    
    # Interprétation
    if delta > 5000:
        comment = "🟢 Strong net buying"
    elif delta > 1000:
        comment = "🟡 Moderate buying"
    elif delta < -5000:
        comment = "🔴 Strong net selling"
    elif delta < -1000:
        comment = "🟠 Moderate selling"
    else:
        comment = "⚪ Neutral flow"
    
    line = f"  📊 CumDelta: {delta:+,} | {comment}\n"
    
    return {
        'delta': delta,
        'line': line
    }
