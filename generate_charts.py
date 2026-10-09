import sqlite3
import re
import yfinance as yf
import mplfinance as mpf
import pandas as pd
from datetime import datetime, timedelta
import pytz
import os

OUT_DIR = "/Users/itaielron/.gemini/antigravity/brain/c0df299c-545f-4292-b580-1c4542af62c7/scratch"
os.makedirs(OUT_DIR, exist_ok=True)

def parse_alert(message, timestamp_str):
    signals = []
    ticker_match = re.search(r'\|\s*Ticker\s*\|\s*([A-Z]+)\s*\|', message)
    entry_match = re.search(r'\|\s*Entry[^\|]*\|\s*~?([\d]+\.[\d]+)', message)
    sl_match = re.search(r'\|\s*Suggested Stop Loss\s*\|\s*([\d\.]+)', message)
    tp1_match = re.search(r'\|\s*Suggested Target 1[^\|]*\|\s*([\d\.]+)', message)
    tp2_match = re.search(r'\|\s*Suggested Target 2[^\|]*\|\s*([\d\.]+)', message)
    
    direction = "LONG" if "LONG SETUP" in message else "SHORT" if "SHORT SETUP" in message else "UNKNOWN"
    
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
    return signals

conn = sqlite3.connect("hub.db")
cursor = conn.cursor()
yesterday = (datetime.now() - timedelta(days=2)).isoformat()
cursor.execute("SELECT timestamp, message FROM alerts WHERE category='STOCK_SWEEP' AND (message LIKE '%🟢%' OR message LIKE '%🔴%') AND timestamp > ?", (yesterday,))
rows = cursor.fetchall()
conn.close()

all_signals = []
for row in rows:
    all_signals.extend(parse_alert(row[1], row[0]))

print(f"Generating charts for {len(all_signals)} signals...")

for i, sig in enumerate(all_signals):
    ticker = sig['ticker']
    print(f"Plotting {ticker}...")
    
    # Download 2 days of 5m data to have some context before the alert
    data = yf.download(ticker, period="3d", interval="5m", progress=False)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)
        
    if data.empty:
        print(f"No data for {ticker}")
        continue
        
    alert_dt = datetime.fromisoformat(sig['timestamp']).replace(tzinfo=pytz.UTC)
    if data.index.tz is not None:
        alert_dt = alert_dt.astimezone(data.index.tz)
    else:
        alert_dt = alert_dt.replace(tzinfo=None)
        
    # Create horizontal lines
    lines = [
        (sig['entry'], 'blue'),   # Entry
        (sig['sl'], 'red'),       # Stop Loss
        (sig['tp1'], 'green')     # Target 1
    ]
    if sig['tp2']:
        lines.append((sig['tp2'], 'darkgreen')) # Target 2
        
    hlines = dict(hlines=[l[0] for l in lines], colors=[l[1] for l in lines], linestyle='--', linewidths=1.5)
    
    # Add a vertical line for the alert time
    vlines = dict(vlines=[alert_dt], colors=['orange'], linewidths=2)
    
    title = f"{ticker} - {sig['direction']} Alert (Entry: {sig['entry']} | SL: {sig['sl']} | TP: {sig['tp1']})"
    fname = f"{OUT_DIR}/chart_{i}_{ticker}_{sig['direction']}.png"
    
    # Use dark style to match the user's dashboard preference
    s = mpf.make_mpf_style(base_mpf_style='cyberpunk', gridstyle=':', facecolor='#0f172a', edgecolor='#334155', figcolor='#0f172a', rc={'text.color': '#e2e8f0', 'axes.labelcolor': '#e2e8f0'})
    
    try:
        mpf.plot(data, type='candle', style=s, hlines=hlines, vlines=vlines, title=title, savefig=fname, figsize=(10, 6))
        print(f"Saved {fname}")
    except Exception as e:
        print(f"Failed to plot {ticker}: {e}")

