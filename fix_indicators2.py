with open("real_alpaca_backtester.py", "r") as f:
    code = f.read()

# Fix the placement
bad = '''    out["EMA9"] = out["Close"].ewm(span=9, adjust=False).mean()
    out["EMA21"] = out["Close"].ewm(span=21, adjust=False).mean()
    out["EMA_20"] = out["Close"].ewm(span=20, adjust=False).mean()
    out["EMA_50"] = out["Close"].ewm(span=50, adjust=False).mean()
    out["EMA_100"] = out["Close"].ewm(span=100, adjust=False).mean()
    out["EMA_200"] = out["Close"].ewm(span=200, adjust=False).mean()
    out["ATR_14"] = tr.rolling(14).mean()'''

good = '''    out["EMA9"] = out["Close"].ewm(span=9, adjust=False).mean()
    out["EMA21"] = out["Close"].ewm(span=21, adjust=False).mean()
    out["EMA_20"] = out["Close"].ewm(span=20, adjust=False).mean()
    out["EMA_50"] = out["Close"].ewm(span=50, adjust=False).mean()
    out["EMA_100"] = out["Close"].ewm(span=100, adjust=False).mean()
    out["EMA_200"] = out["Close"].ewm(span=200, adjust=False).mean()'''

code = code.replace(bad, good)
code = code.replace('out["TR"] = tr\n    out["ATR"] = tr.rolling(ATR_PERIOD).mean()', 'out["TR"] = tr\n    out["ATR"] = tr.rolling(ATR_PERIOD).mean()\n    out["ATR_14"] = tr.rolling(14).mean()')

with open("real_alpaca_backtester.py", "w") as f:
    f.write(code)
