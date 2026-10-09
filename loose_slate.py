from orchestrator_helpers import replace_function_source

loose_func = """def _confluence_cluster(df, i, atr):
    row = df.iloc[i]
    entry = float(row["Close"])
    sl = entry - atr
    tp1 = entry + (atr * 1.5)
    tp2 = entry + (atr * 3.0)
    
    # Just enter on any green candle
    if float(row["Close"]) > float(row["Open"]):
        return {
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "swing_low": sl,
            "swing_high": tp2,
            "risk": atr
        }
    return None"""

replace_function_source("real_alpaca_backtester.py", "_confluence_cluster", loose_func)
