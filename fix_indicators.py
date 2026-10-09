import re

with open("real_alpaca_backtester.py", "r") as f:
    code = f.read()

# Add EMAs to calculate_indicators
old_code = '''    out["EMA9"] = out["Close"].ewm(span=9, adjust=False).mean()
    out["EMA21"] = out["Close"].ewm(span=21, adjust=False).mean()'''

new_code = '''    out["EMA9"] = out["Close"].ewm(span=9, adjust=False).mean()
    out["EMA21"] = out["Close"].ewm(span=21, adjust=False).mean()
    out["EMA_20"] = out["Close"].ewm(span=20, adjust=False).mean()
    out["EMA_50"] = out["Close"].ewm(span=50, adjust=False).mean()
    out["EMA_100"] = out["Close"].ewm(span=100, adjust=False).mean()
    out["EMA_200"] = out["Close"].ewm(span=200, adjust=False).mean()
    out["ATR_14"] = tr.rolling(14).mean()'''

code = code.replace(old_code, new_code)

with open("real_alpaca_backtester.py", "w") as f:
    f.write(code)
