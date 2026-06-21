# ============================================================
# NORTHSENTINEL PRO — MODULE CONFIDENCE SCORE
# Note de confiance /10 basée sur technique + VWAP/POC
# ============================================================

def calculate_confidence_score(stock_data, vol_profile, cum_delta=None, inst_flow=None):
    """
    Calcule une note de confiance /10 avec sous-scores.
    cum_delta et inst_flow sont ignorés dans Pro (réservés Premium).
    """
    technical_score = 0
    volume_score = 0
    
    # --- 1. Score technique (gap + volume + news) — max 5 points ---
    score = stock_data.get('score', 0)
    gap = stock_data.get('gap', 0)
    vol_ratio = stock_data.get('vol_ratio', 0)
    
    if score >= 6:
        technical_score += 5
    elif score == 5:
        technical_score += 4
    else:
        technical_score += 3
    
    if 8 <= gap <= 25:
        technical_score += 0
    elif 5 <= gap < 8 or 25 < gap <= 40:
        technical_score -= 0.5
    
    if vol_ratio > 2.0:
        technical_score += 0
    elif vol_ratio < 1.5:
        technical_score -= 0.5
    
    technical_score = max(0, min(5, technical_score))
    
    # --- 2. Volume Profile (VWAP/POC) — max 5 points ---
    if vol_profile and vol_profile.get('vwap') and vol_profile.get('poc'):
        current_price = stock_data.get('price', 0)
        vwap = vol_profile['vwap']
        poc = vol_profile['poc']
        
        if current_price > vwap:
            volume_score += 3
        else:
            volume_score += 1
        
        distance_to_poc = abs(current_price - poc) / poc * 100
        if distance_to_poc < 1.0:
            volume_score += 2
        elif distance_to_poc < 2.0:
            volume_score += 1.5
        elif distance_to_poc < 4.0:
            volume_score += 0.5
        else:
            volume_score += 0
        
        volume_score = max(0, min(5, volume_score))
    
    # --- Total /10 ---
    total = round(technical_score + volume_score, 1)
    
    # --- Verdict — 5 niveaux ---
    if total >= 8.5:
        verdict = "Strong setup — 3 greens"
    elif total >= 7.5:
        verdict = "Favorable setup — 2 greens, 1 warning"
    elif total >= 5.5:
        verdict = "Mixed setup — 2 greens, 1 warning — caution"
    elif total >= 3.5:
        verdict = "Weak setup — unfavorable risk/reward"
    else:
        verdict = "Poor setup — insufficient confidence"
    
    return {
        'total': total,
        'verdict': verdict
    }
