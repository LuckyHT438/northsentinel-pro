# ============================================================
# NORTHSENTINEL PRO — MODULE POST-MARKET RECAP
# Récap de session envoyé à 16:00 via workflow dédié
# ============================================================
import json
import os
from datetime import datetime
import pytz

MONTREAL_TZ = pytz.timezone('America/Toronto')

def build_recap_message():
    """
    Construit le message récap à partir du fichier de signaux sauvegardé.
    """
    now_mtl = datetime.now(MONTREAL_TZ)
    
    message = f"📊 <b>NorthSentinel Pro™ — Session Recap</b>\n"
    message += f"📅 {now_mtl.strftime('%Y-%m-%d')} (Montreal)\n"
    message += "═" * 30 + "\n\n"
    
    # Charger les signaux du jour
    signals = _load_today_signals()
    
    if signals:
        message += "🔹 <b>SIGNALS TODAY</b>\n"
        for s in signals:
            ticker = s.get('ticker', '?')
            score = s.get('score', '?')
            s_type = s.get('type', '?')
            gap = s.get('gap', 0)
            message += f"  • {ticker} ({s_type}) — Score: {score} | Gap: {gap:.1f}%\n"
    else:
        message += "🔹 <b>SIGNALS TODAY</b>\n"
        message += "  No signals generated.\n"
    
    # Contexte macro
    try:
        from pro_macro_context import get_macro_context
        macro = get_macro_context()
        if macro['line']:
            message += f"\n{macro['line']}"
    except:
        pass
    
    message += "\n<i>Automated recap. Not financial or trading advice.</i>"
    
    return message


def _load_today_signals():
    """Charge les signaux du jour depuis le fichier temporaire"""
    try:
        with open('/tmp/pro_signal_1455.json', 'r') as f:
            data = json.load(f)
        today = datetime.now(MONTREAL_TZ).strftime('%Y-%m-%d')
        
        if isinstance(data, list):
            return [item for item in data if item.get('date') == today]
        elif isinstance(data, dict) and data.get('date') == today:
            return [data]
        return []
    except:
        return []


def send_recap(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID):
    """Envoie le récap Telegram. Appelé par le workflow récap."""
    import requests
    
    message = build_recap_message()
    
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram tokens missing")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
        r = requests.post(url, json=payload, timeout=10)
        print(f"✅ Recap sent - Status: {r.status_code}")
        return True
    except Exception as e:
        print(f"❌ Recap error: {e}")
        return False


if __name__ == "__main__":
    TELEGRAM_TOKEN = os.environ.get("TELEGRAM_PRO_TOKEN")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_PRO_CHAT_ID")
    send_recap(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
