import time
import os
import sys

print("Watchdog initialized. Monitoring for endless loops...")
last_size = 0
stuck_time = 0

while True:
    time.sleep(30)
    try:
        current_size = os.path.getsize('agent_activity.log')
        if current_size == last_size:
            stuck_time += 30
        else:
            stuck_time = 0
            last_size = current_size
            
        if stuck_time >= 300: # 5 minutes of no output
            print("\n[WATCHDOG] 🚨 WARNING: DeepSeek agents appear stuck or looping. Triggering halt to save credits.")
            os.system("pkill -f 'python deepseek_'")
            with open('agent_activity.log', 'a') as f:
                f.write("\n\n[WATCHDOG] 🚨 HALTED DEEPSEEK PROCESSES DUE TO INACTIVITY OR INFINITE LOOP.\n")
            sys.exit(0)
    except Exception:
        pass
