import sqlite3
import re
import mplfinance as mpf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
import os
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from dotenv import load_dotenv

load_dotenv()

OUT_DIR = "/Users/itaielron/.gemini/antigravity/brain/c0df299c-545f-4292-b580-1c4542af62c7"

def parse_alert(message, timestamp_str):
    signals = []
    # Split the message into blocks starting with 🟢 or 🔴
    import re
    blocks = re.split(r'(?=[🟢🔴])', message)
    
    for block in blocks:
        if not ('🟢' in block or '🔴' in block):
            continue
            
        ticker_match = re.search(r'\|\s*Ticker\s*\|\s*([A-Z]+)\s*\|', block)
        entry_match = re.search(r'\|\s*Entry[^\|]*\|\s*~?([\d]+\.[\d]+)', block)
        sl_match = re.search(r'\|\s*Suggested Stop Loss\s*\|\s*([\d\.]+)', block)
        tp1_match = re.search(r'\|\s*Suggested Target 1[^\|]*\|\s*([\d\.]+)', block)
        tp2_match = re.search(r'\|\s*Suggested Target 2[^\|]*\|\s*([\d\.]+)', block)
        
        direction = "LONG" if "LONG SETUP" in block else "SHORT" if "SHORT SETUP" in block else "UNKNOWN"
        
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

client = StockHistoricalDataClient(
    api_key=os.getenv("APCA_API_KEY_ID"),
    secret_key=os.getenv("APCA_API_SECRET_KEY")
)

for i, sig in enumerate(all_signals):
    ticker = sig['ticker']
    end_date = datetime.now()
    start_date = end_date - timedelta(days=3)
    
    try:
        req = StockBarsRequest(symbol_or_symbols=[ticker], timeframe=TimeFrame(5, TimeFrameUnit.Minute), start=start_date, end=end_date, feed="iex")
        data = client.get_stock_bars(req).df
        
        if isinstance(data.index, pd.MultiIndex):
            data = data.reset_index(level=0, drop=True)
            
        if data.empty:
            continue
            
        alert_dt = datetime.fromisoformat(sig['timestamp']).replace(tzinfo=pytz.UTC)
        import pytz
        israel_tz = pytz.timezone('Asia/Jerusalem')
        
        # Convert dataframe index to Israel time
        if data.index.tz is None:
            data.index = data.index.tz_localize('UTC')
        data.index = data.index.tz_convert(israel_tz)
        
        # Convert alert_dt to Israel time
        alert_dt = alert_dt.astimezone(israel_tz)
            
        # Draw red circle at the entry signal time
        # Find the closest index in data to the alert_dt
        time_diffs = abs(data.index - alert_dt)
        closest_idx = time_diffs.argmin()
        
        scatter_series = pd.Series(np.nan, index=data.index)
        scatter_series.iloc[closest_idx] = sig['entry']
        
        ap = mpf.make_addplot(scatter_series, type='scatter', markersize=200, marker='o', color='red')
            
        lines = [
            (sig['entry'], 'blue'),
            (sig['sl'], 'red'),
            (sig['tp1'], 'green')
        ]
        if sig['tp2']:
            lines.append((sig['tp2'], 'lime'))
            
        hlines = dict(hlines=[l[0] for l in lines], colors=[l[1] for l in lines], linestyle='--', linewidths=1.5)
        
        # Yellow line for signal time
        vlines = dict(vlines=[alert_dt], colors=['yellow'], linewidths=2)
        
        # Parse time for title
        local_time_str = alert_dt.strftime("%b %d, %H:%M")
        
        title = f"{ticker} {sig['direction']} | Alert Fired: {local_time_str}\n(Entry: {sig['entry']} | SL: {sig['sl']} | TP1: {sig['tp1']} | TP2: {sig['tp2']})"
        fname = f"{OUT_DIR}/chart_v3_{i}_{ticker}_{sig['direction']}.png"
        
        s = mpf.make_mpf_style(base_mpf_style='nightclouds', gridstyle=':', facecolor='#0f172a', edgecolor='#334155', figcolor='#0f172a', rc={'text.color': '#e2e8f0', 'axes.labelcolor': '#e2e8f0'})
        
        
        fig, axes = mpf.plot(data, type='candle', style=s, addplot=ap, hlines=hlines, vlines=vlines, title=title, figsize=(10, 7), returnfig=True)
        fig.subplots_adjust(top=0.85) # Prevent title cutoff
        fig.savefig(fname)

    except Exception as e:
        pass

