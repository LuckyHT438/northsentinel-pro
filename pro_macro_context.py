# ============================================================
# NORTHSENTINEL PRO — MODULE MACRO CONTEXT
# Delta global US/CA + spreads moyens via yfinance
# ============================================================
import yfinance as yf

# ETF représentatifs pour le contexte macro
MACRO_ETFS = {
    "SPY": "US Market",
    "QQQ": "US Tech",
    "IWM": "US Small Caps",
    "XIU.TO": "CA Market",
    "HYG": "Credit Sentiment",
    "VIXM": "Volatility"
}

def get_macro_context():
    """
    Calcule le contexte macro via les ETFs de référence.
    Retourne un résumé pour l'en-tête du message Pro.
    """
    signals = []
    
    for ticker, label in MACRO_ETFS.items():
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            price = info.get('currentPrice') or info.get('regularMarketPrice')
            prev_close = info.get('previousClose')
            
            if price and prev_close and prev_close > 0:
                change = (price - prev_close) / prev_close * 100
                
                if change > 0.5:
                    signals.append(f"{label} ▲")
                elif change < -0.5:
                    signals.append(f"{label} ▼")
                else:
                    signals.append(f"{label} —")
        except:
            pass
    
    if not signals:
        return {'line': ''}
    
    # Compte les hausses vs baisses
    up_count = sum(1 for s in signals if '▲' in s)
    down_count = sum(1 for s in signals if '▼' in s)
    
    if up_count > down_count:
        bias = "🟢 Risk-on"
    elif down_count > up_count:
        bias = "🔴 Risk-off"
    else:
        bias = "⚪ Neutral"
    
    summary = " | ".join(signals[:4])
    line = f"  🌐 Macro: {bias} | {summary}\n"
    
    return {'line': line}
