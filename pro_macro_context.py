# ============================================================
# NORTHSENTINEL PRO — MODULE MACRO CONTEXT
# Contexte sectoriel par ticker via ETF représentatifs
# ============================================================
import yfinance as yf

# Mapping ticker → ETF sectoriel représentatif
SECTOR_ETFS = {
    # Technologie
    "AAPL": "QQQ", "MSFT": "QQQ", "GOOGL": "QQQ", "META": "QQQ", "NVDA": "QQQ",
    "ADBE": "QQQ", "CRM": "QQQ", "CSCO": "QQQ", "INTC": "QQQ", "AMD": "QQQ",
    "SHOP": "QQQ", "SHOP.TO": "QQQ", "OTEX": "QQQ", "OTEX.TO": "QQQ",
    "LSPD": "QQQ", "LSPD.TO": "QQQ", "SPCX": "QQQ", "SPCX.TO": "QQQ",
    
    # Finance
    "JPM": "XLF", "BAC": "XLF", "WFC": "XLF", "C": "XLF", "GS": "XLF",
    "TD": "XLF", "TD.TO": "XLF", "BMO": "XLF", "BMO.TO": "XLF",
    "BNS": "BNS.TO", "NA": "NA.TO", "GWO": "GWO.TO", "SLF": "SLF.TO",
    "IFC": "IFC.TO", "GRDG": "GRDG.TO", "XFN.TO": "XFN.TO",
    
    # Énergie
    "XOM": "XLE", "CVX": "XLE", "COP": "XLE", "SLB": "XLE", "EOG": "XLE",
    "ENB": "XLE", "ENB.TO": "XLE", "SU": "XLE", "SU.TO": "XLE",
    "CNQ": "CNQ.TO", "SOBO": "SOBO.TO", "HOU.TO": "HOU.TO",
    
    # Matériaux / Mines
    "AEM": "XLB", "AEM.TO": "XLB", "ABX": "XLB", "ABX.TO": "XLB",
    "WPM": "XLB", "WPM.TO": "XLB", "CCO": "CCO.TO",
    "XMA.TO": "XMA.TO", "XGD.TO": "XGD.TO",
    
    # Industrie
    "CAT": "XLI", "DE": "XLI", "BA": "XLI", "GE": "XLI", "LMT": "XLI",
    "CNR": "XLI", "CNR.TO": "XLI", "CP": "CP.TO", "CAE": "CAE.TO",
    "MDA": "MDA.TO", "BBD-B.TO": "BBD-B.TO", "TFII": "TFII.TO",
    
    # Consommation
    "AMZN": "XLY", "TSLA": "XLY", "HD": "XLY", "NKE": "XLY", "SBUX": "XLY",
    "L": "XLY", "L.TO": "XLY", "MRU": "MRU.TO", "DOL": "DOL.TO",
    "MG": "MG.TO", "RBA": "RBA.TO",
    
    # Immobilier / Utilities
    "FTS": "XLU", "FTS.TO": "XLU", "AQN": "AQN.TO", "H": "H.TO",
    "BEP-UN.TO": "BEP-UN.TO", "CSH-UN.TO": "CSH-UN.TO",
    
    # Santé / Pharma
    "JNJ": "XLV", "PFE": "XLV", "UNH": "XLV", "ABBV": "XLV",
    "BHC": "BHC.TO", "AND": "AND.TO",
    
    # Innovation / ARK
    "ARKK": "ARKK", "TSLA": "ARKK", "ROKU": "ARKK", "SQ": "ARKK",
    
    # Canada large cap
    "XIU.TO": "XIU.TO", "VI.TO": "VI.TO",
    
    # International
    "EWJ": "EWJ", "EWT": "EWT", "VWO": "VWO",
    
    # Obligations / Or / Volatilité
    "TLT": "TLT", "GLD": "GLD", "UVXY": "UVXY",
    "USO": "USO", "FLKR": "FLKR", "SOXU.TO": "SOXU.TO",
    "VMO.TO": "VMO.TO", "CHPS.TO": "CHPS.TO", "ZUT.TO": "ZUT.TO",
}


def get_macro_context(ticker):
    """
    Retourne le contexte sectoriel pour un ticker donné.
    Cherche l'ETF sectoriel correspondant et donne sa performance du jour.
    """
    ticker_clean = ticker.upper().replace(".TO", "")
    
    # Chercher le ticker dans le mapping
    sector_etf = SECTOR_ETFS.get(ticker, None)
    if not sector_etf:
        sector_etf = SECTOR_ETFS.get(ticker_clean, None)
    if not sector_etf:
        sector_etf = SECTOR_ETFS.get(ticker + ".TO", None)
    
    if not sector_etf:
        return {'line': ''}
    
    try:
        stock = yf.Ticker(sector_etf)
        info = stock.info
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        prev_close = info.get('previousClose')
        
        if price and prev_close and prev_close > 0:
            change = (price - prev_close) / prev_close * 100
            
            if change > 0.5:
                direction = "▲"
            elif change < -0.5:
                direction = "▼"
            else:
                direction = "—"
            
            sector_name = info.get('shortName', sector_etf)
            line = f"  🌐 {sector_name} ({sector_etf} {direction})"
            
            # Ajouter le biais marché global
            spy = yf.Ticker("SPY")
            spy_info = spy.info
            spy_price = spy_info.get('currentPrice') or spy_info.get('regularMarketPrice')
            spy_prev = spy_info.get('previousClose')
            
            if spy_price and spy_prev and spy_prev > 0:
                spy_change = (spy_price - spy_prev) / spy_prev * 100
                if spy_change > 0.3:
                    line += f" | US market ▲"
                elif spy_change < -0.3:
                    line += f" | US market ▼"
                else:
                    line += f" | US market —"
            
            line += "\n"
            return {'line': line}
    except:
        pass
    
    return {'line': ''}
