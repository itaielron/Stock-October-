import re

with open("src/tools/stock_tools.py", "r") as f:
    content = f.read()

old_logic = """    # Ribbons
    if current_close > df['EMA20'].iloc[-1] > df['EMA50'].iloc[-1] > df['SMA200'].iloc[-1]:
        trend = "Strong Uptrend"
        score = 80
    elif current_close < df['EMA20'].iloc[-1] < df['EMA50'].iloc[-1] < df['SMA200'].iloc[-1]:
        trend = "Strong Downtrend"
        score = 80
    else:
        trend = "Chop / Transition State"
        score = 40
        
    tf_points = {'1D': 20, '1H': 15, '15m': 10, '5m': 5}.get(tf_label, 10)
    
    rsi_div = check_rsi_divergence(df)
    if "Bullish RSI Divergence Detected" in rsi_div and htf_bias == "Bullish":
        score += tf_points
    elif "Bearish RSI Divergence Detected" in rsi_div and htf_bias == "Bearish":
        score += tf_points
        
    smc = detect_smc_structure(df)
    if "Bullish BOS/CHoCH" in smc and htf_bias == "Bullish":
        score += tf_points
    elif "Bearish BOS/CHoCH" in smc and htf_bias == "Bearish":
        score += tf_points"""

new_logic = """    # Ribbons
    current_open = df['open'].iloc[-1]
    is_green = current_close > current_open
    
    if current_close > df['EMA20'].iloc[-1] > df['EMA50'].iloc[-1] > df['SMA200'].iloc[-1]:
        trend = "Strong Uptrend"
        score = 80 if is_green else 65  # Downgrade if it's a red candle despite the macro uptrend
    elif current_close < df['EMA20'].iloc[-1] < df['EMA50'].iloc[-1] < df['SMA200'].iloc[-1]:
        trend = "Strong Downtrend"
        score = 80 if not is_green else 65  # Downgrade if it's a green candle despite the macro downtrend
    else:
        trend = "Chop / Transition State"
        score = 40
        
    tf_points = {'1D': 20, '1H': 15, '15m': 10, '5m': 5}.get(tf_label, 10)
    
    rsi_div = check_rsi_divergence(df)
    if "Bullish RSI Divergence Detected" in rsi_div and "Bull" in htf_bias:
        score += tf_points
    elif "Bearish RSI Divergence Detected" in rsi_div and "Bear" in htf_bias:
        score += tf_points
        
    smc = detect_smc_structure(df)
    if "Bullish BOS/CHoCH" in smc and "Bull" in htf_bias:
        score += tf_points
    elif "Bearish BOS/CHoCH" in smc and "Bear" in htf_bias:
        score += tf_points"""

content = content.replace(old_logic, new_logic)

with open("src/tools/stock_tools.py", "w") as f:
    f.write(content)
