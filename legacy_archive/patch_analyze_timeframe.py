import re

with open("src/tools/stock_tools.py", "r") as f:
    content = f.read()

old_func_sig = """def analyze_timeframe(df: pd.DataFrame, htf_bias: str) -> dict:"""
new_func_sig = """def analyze_timeframe(df: pd.DataFrame, htf_bias: str, tf_label: str = '15m') -> dict:"""
content = content.replace(old_func_sig, new_func_sig)

old_score_logic = """    rsi_div = check_rsi_divergence(df)
    if "Bullish RSI Divergence Detected" in rsi_div and htf_bias == "Bullish":
        score += 15
    elif "Bearish RSI Divergence Detected" in rsi_div and htf_bias == "Bearish":
        score += 15
        
    smc = detect_smc_structure(df)
    if "Bullish BOS/CHoCH" in smc and htf_bias == "Bullish":
        score += 15
    elif "Bearish BOS/CHoCH" in smc and htf_bias == "Bearish":
        score += 15"""

new_score_logic = """    tf_points = {'1D': 20, '1H': 15, '15m': 10, '5m': 5}.get(tf_label, 10)
    
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

content = content.replace(old_score_logic, new_score_logic)

old_call = """tf_report = analyze_timeframe(dfs[tf], htf_bias)"""
new_call = """tf_report = analyze_timeframe(dfs[tf], htf_bias, tf)"""
content = content.replace(old_call, new_call)

with open("src/tools/stock_tools.py", "w") as f:
    f.write(content)
