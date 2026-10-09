import os
import requests
import yaml
from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml")
with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

def send(deal: dict) -> bool:
    """Send a single deal to configured output channel.
    Returns True on success. Must not raise on failure - log and return False."""
    
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    # For Telegram channels, chat_id is the @channel_name. 
    # Or it can be a numeric ID for a DM.
    chat_id = config["notify"]["telegram_channel"] 
    
    if not bot_token:
        print("Error: TELEGRAM_BOT_TOKEN not set in .env")
        return False
        
    route = deal.get("route", "UNKNOWN")
    depart_date = deal.get("depart_date", "UNKNOWN")
    fare_total = deal.get("fare_total", 0.0)
    pct_drop = deal.get("pct_drop", 0.0)
    
    message = (
        f"🚨 **FLIGHT DEAL ALERT** 🚨\n\n"
        f"🛫 **Route:** {route}\n"
        f"📅 **Date:** {depart_date}\n"
        f"💰 **Price:** ${fare_total:.2f} USD\n"
        f"📉 **Drop:** {pct_drop:.1f}%\n\n"
        f"🔗 [Search on Google Flights](https://www.google.com/travel/flights?q=Flights%20to%20{route.split('-')[1]}%20from%20{route.split('-')[0]}%20on%20{depart_date})"
    )
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return True
        else:
            print(f"Telegram API Error {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"Error sending Telegram alert: {e}")
        return False

if __name__ == "__main__":
    # Slice 5 Gate verification
    fake_deal = {
        "route": "TLV-LHR",
        "depart_date": "2026-12-01",
        "fare_total": 700.0,
        "pct_drop": -30.0
    }
    success = send(fake_deal)
    if success:
        print("✅ Slice 5 Gate Passed! Alert sent successfully.")
    else:
        print("❌ Slice 5 Gate Failed!")
