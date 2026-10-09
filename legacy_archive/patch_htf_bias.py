import re

with open("src/tools/stock_tools.py", "r") as f:
    content = f.read()

old_htf = """    # 1. Higher Timeframe (HTF) Hard-Gate
    htf_df = dfs.get('1D')
    htf_bias = "Neutral"
    if htf_df is not None and len(htf_df) > 50:
        htf_df['EMA50'] = htf_df['close'].ewm(span=50, adjust=False).mean()
        htf_bias = "Bullish" if htf_df['close'].iloc[-1] > htf_df['EMA50'].iloc[-1] else "Bearish"
        report["HTF_Gate (1D Bias)"] = htf_bias"""

new_htf = """    # 1. Higher Timeframe (HTF) Hard-Gate
    htf_df = dfs.get('1D')
    htf_bias = "Neutral"
    if htf_df is not None and len(htf_df) > 50:
        htf_df['EMA50'] = htf_df['close'].ewm(span=50, adjust=False).mean()
        current_close = htf_df['close'].iloc[-1]
        current_open = htf_df['open'].iloc[-1]
        ema50 = htf_df['EMA50'].iloc[-1]
        
        if current_close > ema50:
            if current_close < current_open:
                htf_bias = "Neutral (Weakening Bull)"
            else:
                htf_bias = "Bullish"
        else:
            if current_close > current_open:
                htf_bias = "Neutral (Bouncing Bear)"
            else:
                htf_bias = "Bearish"
                
        report["HTF_Gate (1D Bias)"] = htf_bias"""

content = content.replace(old_htf, new_htf)

with open("src/tools/stock_tools.py", "w") as f:
    f.write(content)

# Now fix stock_agent.py
with open("src/agents/stock_agent.py", "r") as f:
    content = f.read()

old_dossier_trend = """- 1D Trend: {'Bullish' if current_price > df_1d['EMA_50'].iloc[-1] else 'Bearish'}"""
new_dossier_trend = """- 1D Trend: {'Bullish' if current_price > df_1d['EMA_50'].iloc[-1] and df_1d['close'].iloc[-1] > df_1d['open'].iloc[-1] else ('Neutral (Weakening Bull)' if current_price > df_1d['EMA_50'].iloc[-1] else ('Neutral (Bouncing Bear)' if df_1d['close'].iloc[-1] > df_1d['open'].iloc[-1] else 'Bearish'))}"""

content = content.replace(old_dossier_trend, new_dossier_trend)

with open("src/agents/stock_agent.py", "w") as f:
    f.write(content)
