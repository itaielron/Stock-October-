import re

with open("src/tools/stock_tools.py", "r") as f:
    content = f.read()

# Replace the broken get_macro_sentiment
start_idx = content.find("def get_macro_sentiment():")
if start_idx != -1:
    new_func = """def get_macro_sentiment():
    import yfinance as yf
    tickers = ["^VIX", "USO", "^TNX", "DX-Y.NYB"]
    output = "--- INTRADAY MACRO-ECONOMIC CONFLUENCE (15m Momentum) ---\\n"
    score = 0
    
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            hist = tk.history(period="1d", interval="15m")
            if len(hist) < 2:
                output += f"{t}: Insufficient intraday data\\n"
                continue
            
            close_now = hist['Close'].iloc[-1]
            close_prev = hist['Close'].iloc[0]
            if len(hist) >= 5:
                close_prev = hist['Close'].iloc[-5]
                
            pct_change = ((close_now - close_prev) / close_prev) * 100
            
            if t == "^TNX":
                impact = "BEARISH for Equities" if pct_change > 0 else "BULLISH for Equities"
                if pct_change > 0: score -= 1
                else: score += 1
            elif t == "^VIX":
                impact = "BEARISH for Equities" if pct_change > 0 else "BULLISH for Equities"
                if pct_change > 0: score -= 1
                else: score += 1
            elif t == "DX-Y.NYB":
                impact = "BEARISH for Equities (Strong Dollar)" if pct_change > 0 else "BULLISH for Equities (Weak Dollar)"
                if pct_change > 0: score -= 1
                else: score += 1
            elif t == "USO":
                impact = "BEARISH for Equities (Inflation Risk)" if pct_change > 0 else "BULLISH for Equities (Disinflationary)"
                if pct_change > 0: score -= 1
                else: score += 1
                
            output += f"{t}: {close_now:.2f} (1hr momentum: {pct_change:+.2f}%) -> {impact}\\n"
        except Exception as e:
            output += f"{t}: Error fetching ({e})\\n"
            
    output += f"\\nTOTAL MACRO SCORE: {score} (-4 = Max Bearish, +4 = Max Bullish)\\n"
    output += "INSTRUCTION: You must heavily weight your final trade decision based on this INTRADAY macro score. If Macro Score is >= +2, strictly prioritize LONG setups. If <= -2, strictly prioritize SHORT setups.\\n"
    return output
"""
    content = content[:start_idx] + new_func

    with open("src/tools/stock_tools.py", "w") as f:
        f.write(content)
