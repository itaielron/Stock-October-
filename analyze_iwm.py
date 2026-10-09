import sqlite3
import re

conn = sqlite3.connect("hub.db")
cursor = conn.cursor()

cursor.execute("SELECT timestamp, message FROM alerts WHERE category='STOCK_SWEEP' AND timestamp LIKE '2026-09-24%' AND message LIKE '%IWM%'")
rows = cursor.fetchall()

for ts, msg in rows:
    blocks = re.split(r'(?=[🟢🔴])', msg)
    for block in blocks:
        if "IWM" in block and ('🟢' in block or '🔴' in block):
            print("====================================")
            print(f"Timestamp: {ts}")
            print("====================================")
            print(block.strip())
            
conn.close()
