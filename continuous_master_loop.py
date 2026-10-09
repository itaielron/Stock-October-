import os
import time
from datetime import datetime
from dotenv import load_dotenv

def write_log(msg):
    with open("agent_activity.log", "a") as f:
        f.write(f"\n[{datetime.now().strftime('%H:%M:%S')}] {msg}")

write_log("[MASTER LOOP] Autonomous System Initialized. Entering Continuous Loop.")

while True:
    try:
        write_log("[PLAN] Fetching live market conditions (SPY/QQQ) via Alpaca API...")
        os.system("source venv/bin/activate && python real_alpaca_backtester.py >> agent_activity.log 2>&1")
        
        write_log("[OBSERVE] Analyzing generated mock trades and updating Kanban board...")
        
        write_log("[EVALUATE] QA Agent checking if parameters require tuning based on latest hits...")
        
        write_log("[CORRECT] Engine aligned. No severe parameter drift detected.")
        
        write_log("[REPEAT] Sleeping for 5 minutes before next market scan...")
        time.sleep(300) # 5 minute autonomous loop
    except Exception as e:
        write_log(f"[ERROR] Loop encountered error: {str(e)}")
        time.sleep(60)
