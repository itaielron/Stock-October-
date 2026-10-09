from orchestrator_helpers import replace_function_source

clean_func = """def _confluence_cluster(df, i, atr):
    row = df.iloc[i]
    prev = df.iloc[i - 1]
    
    # 1) Moving Average Fan (9 > 21)
    if float(row["EMA9"]) <= float(row["EMA21"]):
        return None
        
    # 2) Structural Pullback
    swing_low = float(df["Low"].iloc[max(0, i-5):i].min())
    swing_high = float(df["High"].iloc[max(0, i-5):i].max())
    
    # 3) Entry constraints
    entry = float(row["Close"])
    sl = swing_low - (atr * 0.5)
    risk = entry - sl
    if risk <= 0:
        return None
        
    tp1 = entry + (risk * 1.5)
    tp2 = entry + (risk * 3.0)
    
    return {
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "swing_low": swing_low,
        "swing_high": swing_high,
        "risk": risk
    }"""

replace_function_source("real_alpaca_backtester.py", "_confluence_cluster", clean_func)
