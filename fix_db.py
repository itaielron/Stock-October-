import sqlite3
import re

conn = sqlite3.connect("hub.db")
cursor = conn.cursor()

# Get all stock sweep alerts
cursor.execute("SELECT id, message FROM alerts WHERE category='STOCK_SWEEP' AND (message LIKE '%🟢%' OR message LIKE '%🔴%')")
rows = cursor.fetchall()

updates = 0

for row_id, message in rows:
    new_message = message
    
    # We need to parse block by block, fixing the title if the math contradicts it.
    blocks = re.split(r'(?=[🟢🔴])', message)
    reconstructed = []
    
    for block in blocks:
        if not ('🟢' in block or '🔴' in block):
            reconstructed.append(block)
            continue
            
        entry_match = re.search(r'\|\s*Entry[^\|]*\|\s*~?([\d]+\.[\d]+)', block)
        tp1_match = re.search(r'\|\s*Suggested Target 1[^\|]*\|\s*([\d\.]+)', block)
        
        if entry_match and tp1_match:
            entry = float(entry_match.group(1))
            tp1 = float(tp1_match.group(1))
            
            true_dir = "LONG" if tp1 > entry else "SHORT"
            
            if "LONG SETUP" in block and true_dir == "SHORT":
                block = block.replace("LONG SETUP", "SHORT SETUP", 1)
                block = block.replace("🟢", "🔴", 1)
            elif "SHORT SETUP" in block and true_dir == "LONG":
                block = block.replace("SHORT SETUP", "LONG SETUP", 1)
                block = block.replace("🔴", "🟢", 1)
                
        reconstructed.append(block)
        
    final_message = "".join(reconstructed)
    if final_message != message:
        cursor.execute("UPDATE alerts SET message = ? WHERE id = ?", (final_message, row_id))
        updates += 1

conn.commit()
conn.close()

print(f"Fixed {updates} contradictory signals in the database.")
