import re

with open("src/tools/stock_tools.py", "r") as f:
    content = f.read()

old_logic = """    if len(lows) >= 2:
        price_l1, price_l2 = df['low'].iloc[lows[-2]], df['low'].iloc[lows[-1]]
        rsi_l1, rsi_l2 = df['RSI'].iloc[lows[-2]], df['RSI'].iloc[lows[-1]]
        
        if price_l2 < price_l1 and rsi_l2 > rsi_l1:
            return "Bullish RSI Divergence Detected! (Lower Lows in Price, Higher Lows in RSI)."
            
    return "No significant RSI divergence detected.""""

new_logic = """    divergences = []
    
    # Check Bullish Divergence (on lows)
    if len(lows) >= 2:
        price_l1, price_l2 = df['low'].iloc[lows[-2]], df['low'].iloc[lows[-1]]
        rsi_l1, rsi_l2 = df['RSI'].iloc[lows[-2]], df['RSI'].iloc[lows[-1]]
        if price_l2 < price_l1 and rsi_l2 > rsi_l1:
            divergences.append("Bullish RSI Divergence Detected! (Lower Lows in Price, Higher Lows in RSI).")
            
    # Check Bearish Divergence (on highs)
    if len(highs) >= 2:
        price_h1, price_h2 = df['high'].iloc[highs[-2]], df['high'].iloc[highs[-1]]
        rsi_h1, rsi_h2 = df['RSI'].iloc[highs[-2]], df['RSI'].iloc[highs[-1]]
        if price_h2 > price_h1 and rsi_h2 < rsi_h1:
            divergences.append("Bearish RSI Divergence Detected! (Higher Highs in Price, Lower Highs in RSI).")
            
    return " | ".join(divergences) if divergences else "No significant RSI divergence detected.""""

content = content.replace(old_logic, new_logic)

with open("src/tools/stock_tools.py", "w") as f:
    f.write(content)
