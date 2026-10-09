with open("generate_charts_alpaca.py", "r") as f:
    content = f.read()

new_parse = """def parse_alert(message, timestamp_str):
    signals = []
    # Split the message into blocks starting with 🟢 or 🔴
    import re
    blocks = re.split(r'(?=[🟢🔴])', message)
    
    for block in blocks:
        if not ('🟢' in block or '🔴' in block):
            continue
            
        ticker_match = re.search(r'\|\s*Ticker\s*\|\s*([A-Z]+)\s*\|', block)
        entry_match = re.search(r'\|\s*Entry[^\|]*\|\s*~?([\d]+\.[\d]+)', block)
        sl_match = re.search(r'\|\s*Suggested Stop Loss\s*\|\s*([\d\.]+)', block)
        tp1_match = re.search(r'\|\s*Suggested Target 1[^\|]*\|\s*([\d\.]+)', block)
        tp2_match = re.search(r'\|\s*Suggested Target 2[^\|]*\|\s*([\d\.]+)', block)
        
        direction = "LONG" if "LONG SETUP" in block else "SHORT" if "SHORT SETUP" in block else "UNKNOWN"
        
        if ticker_match and entry_match and sl_match and tp1_match:
            signals.append({
                "ticker": ticker_match.group(1),
                "direction": direction,
                "entry": float(entry_match.group(1)),
                "sl": float(sl_match.group(1)),
                "tp1": float(tp1_match.group(1)),
                "tp2": float(tp2_match.group(1)) if tp2_match else None,
                "timestamp": timestamp_str
            })
    return signals"""

import re
content = re.sub(r'def parse_alert\(message, timestamp_str\):.*?return signals', new_parse, content, flags=re.DOTALL)

with open("generate_charts_alpaca.py", "w") as f:
    f.write(content)
