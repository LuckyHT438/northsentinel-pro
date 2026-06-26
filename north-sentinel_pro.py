# ============================================================
# NORTHSENTINEL PRO — ADVANCED SCALPING & OVERNIGHT SIGNALS
# ============================================================
import requests
import yfinance as yf
import time
import random
import json
from datetime import datetime, timezone, timedelta, date
from bs4 import BeautifulSoup
import re
import pytz
import os
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# === MODULES PRO ===
from pro_volume_profile import get_volume_profile
from pro_confidence import calculate_confidence_score
from pro_macro_context import get_macro_context

# Récupération depuis les secrets GitHub
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_PRO_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_PRO_CHAT_ID")
MONTREAL_TZ = pytz.timezone('America/Toronto')

# === PARAMÈTRES ACTIONS ===
CAPITAL = 1_000_000
RISK_PER_TRADE = 0.02
MAX_CAPITAL_PER_POSITION = 0.10
SCORE_MIN_ACTIONS = 5
SCORE_MIN_OVERNIGHT_ACTIONS = 6
PRICE_MAX_ACTIONS = 300
PRICE_MIN_ACTIONS = 2.00

# === PARAMÈTRES FNB ===
SCORE_MIN_FNB = 5
SCORE_MIN_OVERNIGHT_FNB = 5
PRICE_MAX_FNB = 9999

# === CALENDRIER JOURS FÉRIÉS US/CANADA ===
def is_market_closed(check_date=None):
    if check_date is None:
        check_date = datetime.now(MONTREAL_TZ).date()
    elif isinstance(check_date, datetime):
        check_date = check_date.date()
    
    year = check_date.year
    
    us_holidays = set()
    us_holidays.add(date(year, 1, 1))
    us_holidays.add(date(year, 6, 19))
    us_holidays.add(date(year, 7, 4))
    us_holidays.add(date(year, 12, 25))
    
    mlk = date(year, 1, 1)
    while mlk.weekday() != 0:
        mlk = date(year, 1, mlk.day + 1)
    mlk = date(year, 1, mlk.day + 14)
    us_holidays.add(mlk)
    
    pres = date(year, 2, 1)
    while pres.weekday() != 0:
        pres = date(year, 2, pres.day + 1)
    pres = date(year, 2, pres.day + 14)
    us_holidays.add(pres)
    
    mem = date(year, 5, 31)
    while mem.weekday() != 0:
        mem = date(year, 5, mem.day - 1)
    us_holidays.add(mem)
    
    lab = date(year, 9, 1)
    while lab.weekday() != 0:
        lab = date(year, 9, lab.day + 1)
    us_holidays.add(lab)
    
    thanks = date(year, 11, 1)
    while thanks.weekday() != 3:
        thanks = date(year, 11, thanks.day + 1)
    thanks = date(year, 11, thanks.day + 21)
    us_holidays.add(thanks)
    
    ca_holidays = set()
    ca_holidays.add(date(year, 1, 1))
    ca_holidays.add(date(year, 7, 1))
    ca_holidays.add(date(year, 12, 25))
    ca_holidays.add(date(year, 12, 26))
    
    fam = date(year, 2, 1)
    while fam.weekday() != 0:
        fam = date(year, 2, fam.day + 1)
    fam = date(year, 2, fam.day + 14)
    ca_holidays.add(fam)
    
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
    good_friday = easter - timedelta(days=2)
    ca_holidays.add(good_friday)
    
    vic = date(year, 5, 24)
    while vic.weekday() != 0:
        vic = date(year, 5, vic.day - 1)
    ca_holidays.add(vic)
    
    civ = date(year, 8, 1)
    while civ.weekday() != 0:
        civ = date(year, 8, civ.day + 1)
    ca_holidays.add(civ)
    
    ca_holidays.add(lab)
    
    ca_thanks = date(year, 10, 1)
    while ca_thanks.weekday() != 0:
        ca_thanks = date(year, 10, ca_thanks.day + 1)
    ca_thanks = date(year, 10, ca_thanks.day + 7)
    ca_holidays.add(ca_thanks)
    
    early_close_dates = set()
    early_close_dates.add(date(year, 7, 3))
    early_close_dates.add(date(year, 11, 28))
    early_close_dates.add(date(year, 12, 24))
    early_close_dates.add(date(year, 12, 31))
    
    def adjust_weekend(d):
        if d.weekday() == 5:
            return d - timedelta(days=1)
        elif d.weekday() == 6:
            return d + timedelta(days=1)
        return d
    
    adjusted_us = set()
    for d in us_holidays:
        adjusted_us.add(adjust_weekend(d))
    
    adjusted_ca = set()
    for d in ca_holidays:
        adjusted_ca.add(adjust_weekend(d))
    
    if check_date in adjusted_us or check_date in adjusted_ca:
        return 'closed'
    elif check_date in early_close_dates:
        return 'early_close'
    else:
        return 'open'

# === SESSION HTTP UNIFIÉE ===
def create_session():
    session = requests.Session()
    retry = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    return session

HTTP_SESSION = create_session()

canadian_symbols = {
    "TD.TO", "BMO.TO", "BNS.TO", "NA.TO",
    "ENB.TO", "SU.TO", "CNQ.TO", "SOBO.TO",
    "FTS.TO", "AQN.TO", "H.TO", "BEP-UN.TO",
    "SHOP.TO", "LSPD.TO", "OTEX.TO", "SPCX.TO",
    "CAE.TO", "MDA.TO", "BBD-B.TO",
    "L.TO", "MRU.TO", "CCO.TO", "DOL.TO",
    "CNR.TO", "CP.TO", "T.TO", "BCE.TO",
    "BHC.TO", "CSH-UN.TO", "AND.TO",
    "AEM.TO", "ABX.TO", "WPM.TO",
    "GRDG.TO", "IFC.TO", "SLF.TO", "GWO.TO",
    "MG.TO", "RBA.TO", "TFII.TO"
}

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram Pro tokens missing")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
        r = requests.post(url, json=payload, timeout=10)
        print(f"✅ Telegram Pro sent - Status: {r.status_code}")
        return True
    except Exception as e:
        print(f"❌ Telegram Pro error: {e}")
        return False

def get_exchange_from_info(info):
    exchange = info.get('exchange', '')
    exchange_map = {
        'NMS': 'NASDAQ', 'NGM': 'NASDAQ', 'NCM': 'NASDAQ',
        'NYQ': 'NYSE', 'NYM': 'NYSE', 'PCX': 'ARCA',
        'BTS': 'BATS', 'ASE': 'AMEX', 'PSE': 'NYSE ARCA',
        'TOR': 'TMX', 'TSX': 'TMX', 'TRV': 'TSXV', 'CNQ': 'CSE'
    }
    return exchange_map.get(exchange, exchange if exchange else 'US')

def get_trail_percent(score, is_fnb=False):
    if is_fnb:
        if score >= 5: return 2.5
        elif score == 4: return 3.0
        elif score == 3: return 3.5
        else: return 4.0
    else:
        if score >= 9: return 2.5
        elif score == 8: return 3.0
        elif score == 7: return 3.5
        elif score == 6: return 4.0
        elif score == 5: return 4.5
        else: return 5.0

def get_exit_time():
    now_mtl = datetime.now(MONTREAL_TZ)
    if is_market_closed() == 'early_close':
        exit_time = now_mtl.replace(hour=13, minute=0, second=0, microsecond=0)
        return exit_time.strftime('%H:%M')
    if now_mtl.hour < 12:
        exit_time = now_mtl.replace(hour=11, minute=30, second=0, microsecond=0)
    else:
        exit_time = now_mtl.replace(hour=15, minute=45, second=0, microsecond=0)
    return exit_time.strftime('%H:%M')

def get_gap_min():
    now_mtl = datetime.now(MONTREAL_TZ)
    if now_mtl.hour < 12:
        return 5.0
    else:
        return 2.0

def get_tp_multiplier(score, gap, post_news=False):
    if score < 6:
        if score == 5: base = 1.010
        else: base = 1.005
    elif gap >= 20: base = 1.02 + (score - 4) * 0.006
    elif gap >= 10: base = 1.015 + (score - 4) * 0.004
    else: base = 1.005 + (score - 4) * 0.002
    if post_news: base = round(1.0 + (base - 1.0) * 0.833, 3)
    return round(base, 3)

def get_fnb_tp_multiplier(score, gap, post_news=False):
    if score < 4: base = 1.005
    elif gap >= 6: base = 1.015 + (score - 3) * 0.005
    elif gap >= 3: base = 1.01 + (score - 3) * 0.005
    else: base = 1.005 + (score - 3) * 0.005
    if post_news: base = round(1.0 + (base - 1.0) * 0.833, 3)
    return round(base, 3)

def get_sl_multiplier(score):
    if score >= 8: return 0.97
    elif score >= 6: return 0.96
    else: return 0.95

def calculate_quantity(entry_price, stop_price, capital, risk_per_trade, max_capital_per_position):
    risk_amount = capital * risk_per_trade
    max_exposure = capital * max_capital_per_position
    stop_distance = entry_price - stop_price
    if stop_distance <= 0: return 0
    qty_risk = int(risk_amount / stop_distance)
    qty_cap = int(max_exposure / entry_price)
    return max(0, min(qty_risk, qty_cap))

def get_news_rss(ticker):
    try:
        if ticker in canadian_symbols:
            base_url = "https://news.google.com/rss/search"
            params = {"q": f"{ticker}+stock", "hl": "en-CA", "gl": "CA"}
        else:
            base_url = "https://news.google.com/rss/search"
            params = {"q": f"{ticker}+stock", "hl": "en-US", "gl": "US", "ceid": "US:en"}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
        r = requests.get(base_url, headers=headers, timeout=5, params=params)
        soup = BeautifulSoup(r.content, 'xml')
        items = soup.find_all('item')[:3]
        news_data = []
        now_utc = datetime.now(timezone.utc)
        for item in items:
            title = item.find('title').text if item.find('title') else ''
            pub_date_str = item.find('pubDate').text if item.find('pubDate') else ''
            try:
                pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %Z').replace(tzinfo=timezone.utc)
                hours_ago = (now_utc - pub_date).total_seconds() / 3600
                if hours_ago < 6: news_data.append({'title': title, 'hours_ago': hours_ago})
            except: pass
        return news_data
    except: return []

def analyze_news_sentiment(title, summary=""):
    text = f"{title} {summary}".lower()
    bullish_strong = ['fda approval','partnership','deal','acquisition','buyout','merger','earnings beat','upgraded','breakthrough','contract awarded','clinical success','phase 3','drill results','high-grade','discovery','resource estimate','feasibility study','permit granted','commercial production','joint venture','bought deal','flow-through','positive','upgrade','record revenue','guidance raised','beat estimates']
    bullish = ['growth','revenue','profit','gain','surge','rally','momentum','expansion','launch','agreement','assay','PEA','preliminary economic','buy rating','outperform','overweight','new contract','granted','approval','approved','commenced','completed','successful']
    bearish_strong = ['dilution','offering','bankruptcy','lawsuit','sec investigation','delisting','fda rejection','clinical failure','downgraded','private placement','unit offering','permit denied','cease trade','suspension','default','going concern','termination','insider selling','ceo departure','investigation','guidance lowered','missed estimates']
    bearish = ['loss','decline','drop','fall','warning','concern','risk','delay','delayed','suspended','halted','reduced','lowered','restructuring','layoff','impairment','write-down','debt']
    score = 0
    for word in bullish_strong:
        if word in text: score += 2; break
    for word in bullish:
        if word in text: score += 1; break
    for word in bearish_strong:
        if word in text: score -= 2; break
    for word in bearish:
        if word in text: score -= 1; break
    return score

# === MODE POST-NEWS ===
def scrape_forexfactory():
    try:
        url = "https://www.forexfactory.com/calendar"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=3)
        soup = BeautifulSoup(r.content, 'html.parser')
        news_events = []
        rows = soup.find_all('tr', class_='calendar__row')
        for row in rows:
            impact = row.find('td', class_='impact')
            currency = row.find('td', class_='currency')
            event = row.find('td', class_='event')
            time_cell = row.find('td', class_='time')
            if impact and currency and event and time_cell:
                impact_class = impact.find('span', class_='impact')
                if impact_class and 'high' in impact_class.get('class', []):
                    currency_text = currency.text.strip().upper()
                    event_text = event.text.strip()
                    time_text = time_cell.text.strip()
                    if currency_text == 'USD' and any(kw in event_text.lower() for kw in ['fomc statement','fomc press conference','cpi y/y']):
                        news_events.append({'event': event_text, 'time': time_text, 'source': 'ForexFactory'})
        print(f"📰 ForexFactory: {len(news_events)} High Impact news found")
        return news_events
    except Exception as e:
        print(f"❌ ForexFactory error: {e}")
        return None

def scrape_investing():
    try:
        url = "https://www.investing.com/economic-calendar"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=3)
        soup = BeautifulSoup(r.content, 'html.parser')
        news_events = []
        rows = soup.find_all('tr', class_='js-event-item')
        for row in rows[:30]:
            volatility = row.find_all('td')
            if len(volatility) >= 6:
                currency_text = volatility[2].text.strip().upper()
                event_text = volatility[3].text.strip()
                time_text = volatility[0].text.strip()
                volatility_icons = row.find_all('i', class_='grayFullBullishIcon')
                if volatility_icons and currency_text == 'USD':
                    if any(kw in event_text.lower() for kw in ['fomc statement','fomc press conference','cpi y/y']):
                        try:
                            gmt_time = datetime.strptime(time_text, '%H:%M')
                            gmt_time = gmt_time.replace(tzinfo=timezone.utc)
                            et_time = gmt_time.astimezone(MONTREAL_TZ)
                            time_text = et_time.strftime('%H:%M')
                        except: pass
                        news_events.append({'event': event_text, 'time': time_text, 'source': 'Investing.com'})
        print(f"📰 Investing.com: {len(news_events)} High Impact news found")
        return news_events
    except Exception as e:
        print(f"❌ Investing.com error: {e}")
        return None

def is_high_impact_news(for_tomorrow=False):
    all_news = []
    ff_news = scrape_forexfactory()
    if ff_news: all_news.extend(ff_news)
    inv_news = scrape_investing()
    if inv_news: all_news.extend(inv_news)
    if not all_news: return False, None
    unique_news = []
    seen_events = set()
    for news in all_news:
        key = news['event'].lower().strip()
        if key not in seen_events:
            seen_events.add(key)
            unique_news.append(news)
    if for_tomorrow:
        tomorrow_news = []
        for news in unique_news:
            try:
                news_time = datetime.strptime(news['time'], '%H:%M').time()
                if news_time >= datetime.strptime('07:30', '%H:%M').time() and news_time <= datetime.strptime('11:00', '%H:%M').time():
                    tomorrow_news.append(news)
            except: pass
        unique_news = tomorrow_news
        if not unique_news: return False, None
    print(f"📰 News check: {len(unique_news)} High Impact news | POST-NEWS ACTIVE")
    for n in unique_news:
        print(f"   • {n['event']} — {n['time']} ({n['source']})")
    return True, unique_news

# === SOURCES ACTIONS ===
def get_tickers_canada():
    tickers = ["TD.TO","BMO.TO","BNS.TO","NA.TO","ENB.TO","SU.TO","CNQ.TO","SOBO.TO","FTS.TO","AQN.TO","H.TO","BEP-UN.TO","SHOP.TO","LSPD.TO","OTEX.TO","SPCX.TO","CAE.TO","MDA.TO","BBD-B.TO","L.TO","MRU.TO","CCO.TO","DOL.TO","CNR.TO","CP.TO","T.TO","BCE.TO","BHC.TO","CSH-UN.TO","AND.TO","AEM.TO","ABX.TO","WPM.TO","GRDG.TO","IFC.TO","SLF.TO","GWO.TO","MG.TO","RBA.TO","TFII.TO"]
    random.shuffle(tickers)
    selected = tickers[:20]
    print(f"📊 Canada: {len(selected)} tickers (out of 40)")
    return selected

def get_tickers_from_alpha_vantage():
    try:
        url = "https://www.alphavantage.co/query?function=TOP_GAINERS_LOSERS&apikey=demo"
        r = requests.get(url, timeout=8)
        data = r.json()
        tickers = [item.get('ticker','') for item in data.get('top_gainers',[])[:50] if item.get('ticker')]
        print(f"📊 Alpha Vantage: {len(tickers)} tickers")
        return tickers
    except: return []

def get_tickers_from_yahoo():
    try:
        url = "https://finance.yahoo.com/gainers"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(r.content, 'html.parser')
        tickers = []
        for a in soup.find_all('a', href=re.compile(r'/quote/')):
            t = a.text.strip()
            if t and t.isalpha() and 2 <= len(t) <= 5: tickers.append(t.upper())
        tickers = list(dict.fromkeys(tickers))[:30]
        print(f"📊 Yahoo Finance: {len(tickers)} tickers")
        return tickers
    except: return []

def get_tickers_from_finviz():
    try:
        url = "https://finviz.com/screener.ashx?v=111&ft=4"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(r.content, 'html.parser')
        table = soup.find('table', class_='screen-body-table')
        tickers = []
        if table:
            rows = table.find_all('tr')[1:51]
            for row in rows:
                cols = row.find_all('td')
                if len(cols) > 1:
                    link = cols[1].find('a')
                    if link:
                        t = link.text.strip().upper()
                        if t and t.isalpha() and 2 <= len(t) <= 5: tickers.append(t)
        print(f"📊 Finviz: {len(tickers)} tickers")
        return tickers
    except: return []

def get_tickers_from_stockanalysis():
    try:
        url = "https://stockanalysis.com/list/gainers/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(r.content, 'html.parser')
        tickers = []
        for row in soup.find_all('tr')[1:31]:
            td = row.find('td')
            if td:
                t = td.text.strip().upper()
                if t and t.isalpha() and 2 <= len(t) <= 5: tickers.append(t)
        tickers = list(dict.fromkeys(tickers))[:30]
        print(f"📊 StockAnalysis: {len(tickers)} tickers")
        return tickers
    except: return []

def clean_ticker(t):
    t_upper = t.upper()
    if t_upper.endswith('W') or t_upper.endswith('+') or t_upper.endswith('R'): return None
    if t.count('.') > 1 or '/' in t: return None
    if len(t) > 6: return None
    return t_upper

def get_all_tickers():
    ca_clean = []
    us_clean = []
    ca_tickers = get_tickers_canada()
    for t in ca_tickers:
        if t not in ca_clean: ca_clean.append(t)
    us_tickers = []
    for src in [get_tickers_from_alpha_vantage, get_tickers_from_yahoo, get_tickers_from_finviz, get_tickers_from_stockanalysis]:
        try:
            batch = src()
            us_tickers.extend(batch)
        except: pass
    for t in list(dict.fromkeys(us_tickers)):
        clean = clean_ticker(t)
        if clean and clean not in ca_clean and clean not in us_clean: us_clean.append(clean)
    result = ca_clean + us_clean[:20]
    print(f"🎯 TOTAL STOCKS: {len(result)} tickers (CA: {len(ca_clean)}, US: {min(len(us_clean), 20)})")
    return result

def get_fnb_list():
    fnb_list = ["FLKR","VMO.TO","EWT","XLF","XLE","ARKK","XMA.TO","CHPS.TO","EWJ","TLT","XLB","VI.TO","XGD.TO","SOXU.TO","XFN.TO","ZUT.TO"]
    print(f"🎯 TOTAL ETFs: {len(fnb_list)} tickers")
    return fnb_list

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if len(rsi) > 0 else None

def get_stock_data(ticker, rate_limited_flag):
    try:
        stock = yf.Ticker(ticker, session=HTTP_SESSION)
        info = stock.info
        time.sleep(random.uniform(0.3, 0.5))
        if not info or (info.get('regularMarketPrice') is None and info.get('currentPrice') is None):
            if info.get('message') and 'rate' in str(info.get('message','')).lower():
                print(f"\n⚠️ RATE LIMIT detected - Pausing")
                rate_limited_flag[0] = True
                return None
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        if not price or price < PRICE_MIN_ACTIONS or price > PRICE_MAX_ACTIONS: return None
        prev_close = info.get('previousClose')
        if not prev_close: return None
        gap = ((price - prev_close) / prev_close * 100)
        GAP_MIN = get_gap_min()
        if gap > 50 or gap < GAP_MIN: return None
        volume = info.get('volume', 0)
        is_canadian = ticker in canadian_symbols
        vol_min = 100_000 if is_canadian else 500_000
        if volume < vol_min: return None
        avg_volume = info.get('averageVolume', volume)
        vol_ratio = volume / avg_volume if avg_volume > 0 else 1
        score = 0
        if 5 <= gap <= 40: score += 1
        if vol_ratio > 1.5: score += 1
        if info.get('floatShares', 0) < 50_000_000: score += 1
        if info.get('beta', 0) > 1.0: score += 1
        if info.get('shortRatio', 0) > 2: score += 1
        rsi_50 = info.get('fiftyDayAverage', 0)
        current_close = info.get('regularMarketPreviousClose', price)
        if rsi_50 > 0 and current_close > rsi_50: score += 1
        news = get_news_rss(ticker)
        if news:
            for n in news[:3]:
                sentiment = analyze_news_sentiment(n.get('title',''))
                if sentiment >= 1: score += 1; break
                elif sentiment <= -2: score -= 1; break
        if score < SCORE_MIN_ACTIONS: return None
        exchange = get_exchange_from_info(info)
        trail_percent = get_trail_percent(score, is_fnb=False)
        return {'ticker': ticker, 'exchange': exchange, 'price': price, 'gap': gap, 'score': score, 'vol_ratio': vol_ratio, 'trail_percent': trail_percent}
    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "Too Many Requests" in err_str:
            print(f"\n⚠️ RATE LIMIT YF - Pausing")
            rate_limited_flag[0] = True
        return None

def analyze_fnb(ticker):
    try:
        stock = yf.Ticker(ticker, session=HTTP_SESSION)
        info = stock.info
        hist = stock.history(period="1mo")
        time.sleep(random.uniform(0.3, 0.5))
        if hist.empty or len(hist) < 2: return None
        closes = hist['Close']
        volumes = hist['Volume']
        price = closes.iloc[-1]
        prev_close = closes.iloc[-2]
        volume = volumes.iloc[-1] if len(volumes) > 0 else 0
        avg_volume = volumes.mean() if len(volumes) > 0 else volume
        if not price or price < 0.5 or price > PRICE_MAX_FNB: return None
        if not prev_close: return None
        gap = ((price - prev_close) / prev_close * 100)
        crit_gap = 0.5 <= gap <= 8
        vol_ratio = volume / avg_volume if avg_volume > 0 else 1
        crit_vol = vol_ratio > 0.9
        aum = info.get('totalAssets', 0) or info.get('assetsUnderManagement', 0)
        crit_aum = aum > 50_000_000 if aum else True
        rsi = None
        crit_rsi = False
        sma20 = None
        crit_sma = False
        if len(closes) > 14:
            rsi = calculate_rsi(closes)
            crit_rsi = 35 <= rsi <= 80 if rsi else False
        if len(closes) >= 20:
            sma20 = closes.rolling(20).mean().iloc[-1]
            crit_sma = price > 0.70 * sma20
        score = sum([crit_gap, crit_vol, crit_aum, crit_rsi, crit_sma])
        if score < SCORE_MIN_FNB: return None
        exchange = get_exchange_from_info(info)
        trail_percent = get_trail_percent(score, is_fnb=True)
        return {'ticker': ticker, 'exchange': exchange, 'price': price, 'gap': gap, 'score': score, 'vol_ratio': vol_ratio, 'aum_m': aum/1_000_000 if aum else 0, 'rsi': rsi, 'sma20': sma20, 'trail_percent': trail_percent}
    except: return None

def format_capital(amount):
    if amount >= 1_000_000: return f"{amount/1_000_000:.1f}M$"
    elif amount >= 1_000: return f"{amount/1_000:.0f}k$"
    else: return f"{amount}$"

def save_signal_for_overnight(signals):
    try:
        data = []
        for signal, ticker_type in signals:
            data.append({"ticker": signal['ticker'], "type": ticker_type, "entry_price": signal['price'], "score": signal['score'], "gap": signal['gap'], "vol_ratio": signal['vol_ratio'], "trail_percent": signal['trail_percent'], "date": datetime.now(MONTREAL_TZ).strftime('%Y-%m-%d')})
        with open('/tmp/pro_signal_1455.json', 'w') as f: json.dump(data, f)
        print(f"💾 {len(data)} signal(s) saved for overnight check")
        return True
    except Exception as e:
        print(f"❌ Signal save error: {e}")
        return False

def load_previous_signal(ticker_type=None):
    try:
        with open('/tmp/pro_signal_1455.json', 'r') as f: data = json.load(f)
        today = datetime.now(MONTREAL_TZ).strftime('%Y-%m-%d')
        if isinstance(data, list):
            for item in data:
                if item.get('date') == today and item.get('ticker'):
                    if ticker_type is None or item.get('type') == ticker_type:
                        print(f"📂 Previous signal loaded: {item['ticker']} ({item['type']})")
                        return item
            return None
        else:
            if data.get('date') == today and data.get('ticker'):
                if ticker_type is None or data.get('type') == ticker_type: return data
            return None
    except FileNotFoundError: return None
    except Exception as e:
        print(f"❌ Signal load error: {e}")
        return None

def main():
    START_TIME = time.time()
    now_mtl = datetime.now(MONTREAL_TZ)
    jour = now_mtl.weekday()
    heure = now_mtl.hour
    minute = now_mtl.minute
    
    market_status = is_market_closed()
    if market_status == 'closed':
        print(f"🏖️ Market closed (holiday) - No execution")
        return
    elif market_status == 'early_close':
        print(f"⏰ Early close today (1:00 PM ET)")
    
    if jour >= 5:
        print("🔧 Weekend — Manual run authorized")
    
    # === MODE OVERNIGHT CHECK ===
    if jour in [0,1,2,3] and heure == 15 and minute >= 45:
        tomorrow = now_mtl.date() + timedelta(days=1)
        if is_market_closed(datetime(tomorrow.year, tomorrow.month, tomorrow.day)) == 'closed':
            print(f"🏖️ Tomorrow is holiday - No Overnight Check")
            return
        
        print("=" * 50)
        print(f"🤖 NorthSentinel Pro — Overnight Check - {now_mtl.strftime('%Y-%m-%d %H:%M:%S')} (Montreal)")
        print("=" * 50)
        
        post_news_tomorrow, news_tomorrow = is_high_impact_news(for_tomorrow=True)
        
        tickers_actions = get_all_tickers()
        print(f"\n🔍 Phase 1: Analyzing {len(tickers_actions)} stocks for Overnight...\n")
        
        rate_limited_flag = [False]
        buys_actions = []
        analysed_actions = 0
        
        for i, ticker in enumerate(tickers_actions):
            if time.time() - START_TIME > 55:
                print(f"\n⚠️ TIMEOUT 55s - {i}/{len(tickers_actions)} stocks processed")
                break
            print(f"[STOCK {i+1}/{len(tickers_actions)}] {ticker}...", end=" ")
            data = get_stock_data(ticker, rate_limited_flag)
            analysed_actions = i + 1
            if data and data['score'] >= SCORE_MIN_OVERNIGHT_ACTIONS:
                buys_actions.append(data)
                print(f"✅ Score: {data['score']}/9")
            elif data:
                print(f"❌ Score insufficient: {data['score']}/9")
            else:
                print("❌")
            if rate_limited_flag[0]:
                print("⏸️ Rate limit pause 15s...")
                time.sleep(15)
                rate_limited_flag[0] = False
        
        tickers_fnb = get_fnb_list()
        print(f"\n🔍 Phase 2: Analyzing {len(tickers_fnb)} ETFs for Overnight...\n")
        
        buys_fnb = []
        analysed_fnb = 0
        
        for i, ticker in enumerate(tickers_fnb):
            if time.time() - START_TIME > 55:
                print(f"\n⚠️ TIMEOUT 55s - {i}/{len(tickers_fnb)} ETFs processed")
                break
            print(f"[ETF {i+1}/{len(tickers_fnb)}] {ticker}...", end=" ")
            data = analyze_fnb(ticker)
            analysed_fnb = i + 1
            if data and data['score'] >= SCORE_MIN_OVERNIGHT_FNB:
                buys_fnb.append(data)
                print(f"✅ Score: {data['score']}/5")
            elif data:
                print(f"❌ Score insufficient: {data['score']}/5")
            else:
                print("❌")
        
        elapsed = time.time() - START_TIME
        
        # === TELEGRAM MESSAGE - PRO OVERNIGHT ===
        message = f"🤖 <b>NorthSentinel Pro</b>\n"
        message += f"<i>US/CA advanced intraday & overnight hold trading signals. Manual execution. Post-market recap.</i>\n"
        message += f"📅 {now_mtl.strftime('%Y-%m-%d %H:%M')} (Montreal)\n"
        message += "═" * 35 + "\n"
        
        if post_news_tomorrow and news_tomorrow:
            message += f"\n⚠️ <b>HIGH IMPACT NEWS TOMORROW</b>\n"
            for news in news_tomorrow:
                sentiment = analyze_news_sentiment(news['event'])
                if sentiment >= 1:
                    direction = "📈"
                elif sentiment <= -1:
                    direction = "📉"
                else:
                    direction = "➡️"
                message += f"📅 {news['event']} — {news['time']} ({news['source']}) {direction}\n"
            message += f"💡 Critical window: 7:30 AM-11:00 AM (Montreal time)\n"
            message += "═" * 35 + "\n"
        
        message += f"\n🚀 <b>STOCK — Overnight Setup</b>\n"
        message += f"📊 Scanned: {analysed_actions}/{len(tickers_actions)} | Min Score: {SCORE_MIN_OVERNIGHT_ACTIONS}/9\n"
        if buys_actions:
            best_action = sorted(buys_actions, key=lambda x: (x['score'], x['vol_ratio']), reverse=True)[0]
            b = best_action
            buy_price = round(b['price'], 2)
            tp_mult = get_tp_multiplier(b['score'], b['gap'], post_news_tomorrow)
            sl_mult = get_sl_multiplier(b['score'])
            sell_price = round(buy_price * tp_mult, 2)
            stop = round(buy_price * sl_mult, 2)
            trail_price = round(buy_price * (1 - b['trail_percent']/100), 2)
            quantity = calculate_quantity(buy_price, stop, CAPITAL, RISK_PER_TRADE, MAX_CAPITAL_PER_POSITION)
            vol_profile = get_volume_profile(b['ticker'], b['price'])
            confidence = calculate_confidence_score(b, vol_profile)
            sector_context = get_macro_context(b['ticker'])
            
            if confidence['total'] >= 8.5:
                verdict_line = f"  ⚖️ <b>VERDICT: Strong setup</b> 🟢\n"
            elif confidence['total'] >= 7.5:
                verdict_line = f"  ⚖️ <b>VERDICT: Favorable setup</b> 🟢\n"
            elif confidence['total'] >= 5.5:
                verdict_line = f"  ⚖️ <b>VERDICT: Mixed setup</b> 🟡\n"
            elif confidence['total'] >= 3.5:
                verdict_line = f"  ⚖️ <b>VERDICT: Weak setup</b> 🟠\n"
            else:
                verdict_line = f"  ⚖️ <b>VERDICT: Poor setup</b> 🔴\n"
            
            message += f"\n🔹 <b>{b['ticker']}</b> ({b['exchange']}) | Quality: <b>{b['score']}/9</b> | 🎯 Confidence: <b>{confidence['total']}/10</b>\n"
            message += f"  📊 GAP: {b['gap']:.1f}% | VOL: x{b['vol_ratio']:.1f}\n"
            if sector_context['line']:
                message += sector_context['line']
            message += f"  💵 CUR. PRICE: ${b['price']}\n"
            if vol_profile['line']:
                message += vol_profile['line']
            message += verdict_line
            message += (
                f"  🎯 ENTRY PRICE: ${buy_price}\n"
                f"  📦 QTY TO BUY: {quantity} shares\n"
                f"  📈 TAKE-PROFIT: ${sell_price} (+{round((tp_mult - 1) * 100, 1)}%)\n"
                f"  🛑 STOP LOSS: ${stop} ({round((1 - sl_mult) * 100, 1)}%)\n"
                f"  🔄 TRAILING SL: ${trail_price} → {b['trail_percent']}%\n"
            )
        else:
            message += f"❌ No Valid Stock for Overnight\n"
            message += f"⏰ Until next time!\n"
        
        message += f"\n📈 <b>ETF — Overnight Setup</b>\n"
        message += f"📊 Scanned: {analysed_fnb}/{len(tickers_fnb)} | Min Score: {SCORE_MIN_OVERNIGHT_FNB}/5\n"
        if buys_fnb:
            best_fnb = sorted(buys_fnb, key=lambda x: (x['score'], x['vol_ratio']), reverse=True)[0]
            b = best_fnb
            buy_price = round(b['price'], 2)
            tp_mult = get_fnb_tp_multiplier(b['score'], b['gap'], post_news_tomorrow)
            sell_price = round(buy_price * tp_mult, 2)
            stop = round(buy_price * 0.97, 2)
            trail_price = round(buy_price * (1 - b['trail_percent']/100), 2)
            quantity = calculate_quantity(buy_price, stop, CAPITAL, RISK_PER_TRADE, MAX_CAPITAL_PER_POSITION)
            vol_profile_etf = get_volume_profile(b['ticker'], b['price'])
            confidence_etf = calculate_confidence_score(b, vol_profile_etf)
            sector_context_etf = get_macro_context(b['ticker'])
            
            if confidence_etf['total'] >= 8.5:
                verdict_line = f"  ⚖️ <b>VERDICT: Strong setup</b> 🟢\n"
            elif confidence_etf['total'] >= 7.5:
                verdict_line = f"  ⚖️ <b>VERDICT: Favorable setup</b> 🟢\n"
            elif confidence_etf['total'] >= 5.5:
                verdict_line = f"  ⚖️ <b>VERDICT: Mixed setup</b> 🟡\n"
            elif confidence_etf['total'] >= 3.5:
                verdict_line = f"  ⚖️ <b>VERDICT: Weak setup</b> 🟠\n"
            else:
                verdict_line = f"  ⚖️ <b>VERDICT: Poor setup</b> 🔴\n"
            
            message += f"\n🔹 <b>{b['ticker']}</b> ({b['exchange']}) | Quality: <b>{b['score']}/5</b> | 🎯 Confidence: <b>{confidence_etf['total']}/10</b>\n"
            message += f"  📊 GAP: {b['gap']:.2f}% | VOL: x{b['vol_ratio']:.2f}\n"
            if sector_context_etf['line']:
                message += sector_context_etf['line']
            message += f"  💵 CUR. PRICE: ${b['price']:.2f}\n"
            if vol_profile_etf['line']:
                message += vol_profile_etf['line']
            message += verdict_line
            message += (
                f"  🎯 ENTRY PRICE: ${buy_price}\n"
                f"  📦 QTY TO BUY: {quantity} units\n"
                f"  📈 TAKE-PROFIT: ${sell_price} (+{round((tp_mult - 1) * 100, 1)}%)\n"
                f"  🛑 STOP LOSS: ${stop} (3.0%)\n"
                f"  🔄 TRAILING SL: ${trail_price} → {b['trail_percent']}%\n"
            )
        else:
            message += f"❌ No Valid ETF for Overnight\n"
            message += f"⏰ Until next time!\n"
        
        message += "\n\n<i>Automated informational signal. Not financial or trading advice.</i>"
        print("\n" + "=" * 50)
        print(f"⏱️ Total time: {elapsed:.1f}s")
        print("📤 Sending Telegram...")
        send_telegram(message)
        print("=" * 50)
        return
    
    # === MODE NORMAL ===
    post_news = False
    news_info = None
    if (heure == 9 and minute >= 25) or (heure == 14 and minute >= 55):
        post_news, news_info = is_high_impact_news()
    
    current_score_min_actions = SCORE_MIN_ACTIONS
    current_score_min_fnb = SCORE_MIN_FNB
    
    GAP_MIN = get_gap_min()
    
    print("=" * 50)
    print(f"🤖 NorthSentinel Pro - {now_mtl.strftime('%Y-%m-%d %H:%M:%S')} (Montreal)")
    print(f"💰 Capital: {format_capital(CAPITAL)} | Min Gap: {GAP_MIN}% | Stock Score: {current_score_min_actions}/9 | ETF: {current_score_min_fnb}/5")
    if market_status == 'early_close':
        print(f"⏰ EARLY CLOSE 1:00 PM ET")
    print("=" * 50)
    
    tickers_actions = get_all_tickers()
    print(f"\n🔍 Phase 1: Analyzing {len(tickers_actions)} stocks...\n")
    
    rate_limited_flag = [False]
    buys_actions = []
    analysed_actions = 0
    
    for i, ticker in enumerate(tickers_actions):
        if time.time() - START_TIME > 55:
            print(f"\n⚠️ TIMEOUT 55s - {i}/{len(tickers_actions)} stocks processed")
            break
        print(f"[STOCK {i+1}/{len(tickers_actions)}] {ticker}...", end=" ")
        data = get_stock_data(ticker, rate_limited_flag)
        analysed_actions = i + 1
        if data:
            if post_news and data['score'] < current_score_min_actions:
                print("❌ (score < post-news min)")
            else:
                buys_actions.append(data)
                print(f"✅ Score: {data['score']}/9")
        else:
            print("❌")
        if rate_limited_flag[0]:
            print("⏸️ Rate limit pause 15s...")
            time.sleep(15)
            rate_limited_flag[0] = False
    
    tickers_fnb = get_fnb_list()
    print(f"\n🔍 Phase 2: Analyzing {len(tickers_fnb)} ETFs...\n")
    
    buys_fnb = []
    analysed_fnb = 0
    
    for i, ticker in enumerate(tickers_fnb):
        if time.time() - START_TIME > 55:
            print(f"\n⚠️ TIMEOUT 55s - {i}/{len(tickers_fnb)} ETFs processed")
            break
        print(f"[ETF {i+1}/{len(tickers_fnb)}] {ticker}...", end=" ")
        data = analyze_fnb(ticker)
        analysed_fnb = i + 1
        if data:
            if post_news and data['score'] < current_score_min_fnb:
                print("❌ (score < post-news min)")
            else:
                buys_fnb.append(data)
                print(f"✅ Score: {data['score']}/5")
        else:
            print("❌")
    
    elapsed = time.time() - START_TIME
    
    # === TELEGRAM MESSAGE - PRO NORMAL ===
    message = f"🤖 <b>NorthSentinel Pro</b>\n"
    message += f"<i>US/CA advanced intraday & overnight hold trading signals. Manual execution. Post-market recap.</i>\n"
    message += f"📅 {now_mtl.strftime('%Y-%m-%d %H:%M')} (Montreal)\n"
    message += f"💰 Capital: {format_capital(CAPITAL)} | Min Gap: {GAP_MIN}%\n"
    message += "═" * 35 + "\n"
    
    if post_news and news_info:
        message += f"\n⚠️ <b>HIGH IMPACT NEWS DETECTED</b>\n"
        for news in news_info:
            sentiment = analyze_news_sentiment(news['event'])
            if sentiment >= 1:
                direction = "📈"
            elif sentiment <= -1:
                direction = "📉"
            else:
                direction = "➡️"
            message += f"📅 {news['event']} — {news['time']} ({news['source']}) {direction}\n"
        message += "═" * 35 + "\n"
    
    message += f"\n🚀 <b>STOCK</b> - Best Setup\n"
    message += f"📊 Scanned: {analysed_actions}/{len(tickers_actions)} | Min Score: {current_score_min_actions}/9\n"
    if buys_actions:
        best_action = sorted(buys_actions, key=lambda x: (x['score'], x['vol_ratio']), reverse=True)[0]
        b = best_action
        buy_price = round(b['price'], 2)
        tp_mult = get_tp_multiplier(b['score'], b['gap'], post_news)
        sl_mult = get_sl_multiplier(b['score'])
        sell_price = round(buy_price * tp_mult, 2)
        stop = round(buy_price * sl_mult, 2)
        trail_price = round(buy_price * (1 - b['trail_percent']/100), 2)
        quantity = calculate_quantity(buy_price, stop, CAPITAL, RISK_PER_TRADE, MAX_CAPITAL_PER_POSITION)
        vol_profile = get_volume_profile(b['ticker'], b['price'])
        confidence = calculate_confidence_score(b, vol_profile)
        sector_context = get_macro_context(b['ticker'])
        
        if confidence['total'] >= 8.5:
            verdict_line = f"  ⚖️ <b>VERDICT: Strong setup</b> 🟢\n"
        elif confidence['total'] >= 7.5:
            verdict_line = f"  ⚖️ <b>VERDICT: Favorable setup</b> 🟢\n"
        elif confidence['total'] >= 5.5:
            verdict_line = f"  ⚖️ <b>VERDICT: Mixed setup</b> 🟡\n"
        elif confidence['total'] >= 3.5:
            verdict_line = f"  ⚖️ <b>VERDICT: Weak setup</b> 🟠\n"
        else:
            verdict_line = f"  ⚖️ <b>VERDICT: Poor setup</b> 🔴\n"
        
        message += f"\n🔹 <b>{b['ticker']}</b> ({b['exchange']}) | Quality: <b>{b['score']}/9</b> | 🎯 Confidence: <b>{confidence['total']}/10</b>\n"
        message += f"  📊 GAP: {b['gap']:.1f}% | VOL: x{b['vol_ratio']:.1f}\n"
        if sector_context['line']:
            message += sector_context['line']
        message += f"  💵 CUR. PRICE: ${b['price']}\n"
        if vol_profile['line']:
            message += vol_profile['line']
        message += verdict_line
        message += (
            f"  🎯 ENTRY PRICE: ${buy_price}\n"
            f"  📦 QTY TO BUY: {quantity} shares\n"
            f"  📈 TAKE-PROFIT: ${sell_price} (+{round((tp_mult - 1) * 100, 1)}%)\n"
            f"  🛑 STOP LOSS: ${stop} ({round((1 - sl_mult) * 100, 1)}%)\n"
            f"  🔄 TRAILING SL: ${trail_price} → {b['trail_percent']}%\n"
        )
    else:
        message += f"❌ No Valid Stock Identified\n"
        message += f"⏰ Until next time!\n"
    
    message += f"\n📈 <b>ETF</b> - Best Setup\n"
    message += f"📊 Scanned: {analysed_fnb}/{len(tickers_fnb)} | Min Score: {current_score_min_fnb}/5\n"
    if buys_fnb:
        best_fnb = sorted(buys_fnb, key=lambda x: (x['score'], x['vol_ratio']), reverse=True)[0]
        b = best_fnb
        buy_price = round(b['price'], 2)
        tp_mult = get_fnb_tp_multiplier(b['score'], b['gap'], post_news)
        sell_price = round(buy_price * tp_mult, 2)
        stop = round(buy_price * 0.97, 2)
        trail_price = round(buy_price * (1 - b['trail_percent']/100), 2)
        quantity = calculate_quantity(buy_price, stop, CAPITAL, RISK_PER_TRADE, MAX_CAPITAL_PER_POSITION)
        vol_profile_etf = get_volume_profile(b['ticker'], b['price'])
        confidence_etf = calculate_confidence_score(b, vol_profile_etf)
        sector_context_etf = get_macro_context(b['ticker'])
        
        if confidence_etf['total'] >= 8.5:
            verdict_line = f"  ⚖️ <b>VERDICT: Strong setup</b> 🟢\n"
        elif confidence_etf['total'] >= 7.5:
            verdict_line = f"  ⚖️ <b>VERDICT: Favorable setup</b> 🟢\n"
        elif confidence_etf['total'] >= 5.5:
            verdict_line = f"  ⚖️ <b>VERDICT: Mixed setup</b> 🟡\n"
        elif confidence_etf['total'] >= 3.5:
            verdict_line = f"  ⚖️ <b>VERDICT: Weak setup</b> 🟠\n"
        else:
            verdict_line = f"  ⚖️ <b>VERDICT: Poor setup</b> 🔴\n"
        
        message += f"\n🔹 <b>{b['ticker']}</b> ({b['exchange']}) | Quality: <b>{b['score']}/5</b> | 🎯 Confidence: <b>{confidence_etf['total']}/10</b>\n"
        message += f"  📊 GAP: {b['gap']:.2f}% | VOL: x{b['vol_ratio']:.2f}\n"
        if sector_context_etf['line']:
            message += sector_context_etf['line']
        message += f"  💵 CUR. PRICE: ${b['price']:.2f}\n"
        if vol_profile_etf['line']:
            message += vol_profile_etf['line']
        message += verdict_line
        message += (
            f"  🎯 ENTRY PRICE: ${buy_price}\n"
            f"  📦 QTY TO BUY: {quantity} units\n"
            f"  📈 TAKE-PROFIT: ${sell_price} (+{round((tp_mult - 1) * 100, 1)}%)\n"
            f"  🛑 STOP LOSS: ${stop} (3.0%)\n"
            f"  🔄 TRAILING SL: ${trail_price} → {b['trail_percent']}%\n"
        )
    else:
        message += f"❌ No Valid ETF Identified\n"
        message += f"⏰ Until next time!\n"
    
    if jour in [0,1,2,3] and heure == 14 and 45 <= minute <= 59:
        signals_to_save = []
        if buys_actions:
            best_action = sorted(buys_actions, key=lambda x: (x['score'], x['vol_ratio']), reverse=True)[0]
            signals_to_save.append((best_action, "STOCK"))
        if buys_fnb:
            best_fnb = sorted(buys_fnb, key=lambda x: (x['score'], x['vol_ratio']), reverse=True)[0]
            signals_to_save.append((best_fnb, "ETF"))
        if signals_to_save:
            save_signal_for_overnight(signals_to_save)
    
    message += "\n\n<i>Automated informational signal. Not financial or trading advice.</i>"
    
    print("\n" + "=" * 50)
    print(f"⏱️ Total time: {elapsed:.1f}s")
    print("📤 Sending Telegram...")
    send_telegram(message)
    print("=" * 50)

if __name__ == "__main__":
    main()
