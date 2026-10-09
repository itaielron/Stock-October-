import sqlite3
import re
import mplfinance as mpf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
import os
import json
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from dotenv import load_dotenv

load_dotenv()

OUT_DIR = "/Users/itaielron/.gemini/antigravity/brain/c0df299c-545f-4292-b580-1c4542af62c7"

def parse_alert(message, timestamp_str):
    signals = []
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
        
        # Override mislabeled direction if geometry contradicts
        if sl_match and tp1_match and entry_match:
            sl_val = float(sl_match.group(1))
            entry_val = float(entry_match.group(1))
            tp_val = float(tp1_match.group(1))
            if sl_val < entry_val and tp_val > entry_val:
                direction = "LONG"
            elif sl_val > entry_val and tp_val < entry_val:
                direction = "SHORT"
        
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

valid_signals = []
israel_tz = pytz.timezone('Asia/Jerusalem')
ny_tz = pytz.timezone('US/Eastern')

for i, sig in enumerate(all_signals):
    ticker = sig['ticker']
    alert_dt_utc = datetime.fromisoformat(sig['timestamp']).replace(tzinfo=pytz.UTC)
    alert_est = alert_dt_utc.astimezone(ny_tz)
    
    market_open = alert_est.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = alert_est.replace(hour=16, minute=0, second=0, microsecond=0)
    
    if not (market_open <= alert_est <= market_close):
        continue

    # Get data
    end_date = datetime.now()
    start_date = alert_dt_utc - timedelta(days=1) # Get data from a bit before the alert
    
    try:
        req = StockBarsRequest(symbol_or_symbols=[ticker], timeframe=TimeFrame(5, TimeFrameUnit.Minute), start=start_date, end=end_date, feed="iex")
        data = client.get_stock_bars(req).df
        
        if isinstance(data.index, pd.MultiIndex):
            data = data.reset_index(level=0, drop=True)
            
        if data.empty:
            continue
            
        if data.index.tz is None:
            data.index = data.index.tz_localize('UTC')
        data.index = data.index.tz_convert(israel_tz)
        alert_dt_il = alert_dt_utc.astimezone(israel_tz)
        
        # Only keep data up to the current moment
        
        # 1. RED CIRCLE ON THE ACTUAL CANDLE (Close price)
        time_diffs = abs(data.index - alert_dt_il)
        entry_idx = time_diffs.argmin()
        actual_candle_close = data['close'].iloc[entry_idx]
        
        # Determine WIN/LOSS
        future_data = data.iloc[entry_idx:]
        outcome = "PENDING"
        outcome_color = "yellow"
        exit_idx = None
        exit_price = None
        
        if sig['direction'] == 'LONG':
            for idx in range(len(future_data)):
                row = future_data.iloc[idx]
                if row['high'] >= sig['tp1']:
                    outcome = "WIN"
                    outcome_color = "green"
                    exit_idx = entry_idx + idx
                    exit_price = sig['tp1']
                    break
                elif row['low'] <= sig['sl']:
                    outcome = "LOSS"
                    outcome_color = "red"
                    exit_idx = entry_idx + idx
                    exit_price = sig['sl']
                    break
        else: # SHORT
            for idx in range(len(future_data)):
                row = future_data.iloc[idx]
                if row['low'] <= sig['tp1']:
                    outcome = "WIN"
                    outcome_color = "green"
                    exit_idx = entry_idx + idx
                    exit_price = sig['tp1']
                    break
                elif row['high'] >= sig['sl']:
                    outcome = "LOSS"
                    outcome_color = "red"
                    exit_idx = entry_idx + idx
                    exit_price = sig['sl']
                    break
                    
        # Plottings
        entry_series = pd.Series(np.nan, index=data.index)
        entry_series.iloc[entry_idx] = actual_candle_close
        
        exit_series = pd.Series(np.nan, index=data.index)
        if exit_idx is not None:
            exit_series.iloc[exit_idx] = exit_price
            
        ap_list = [
            mpf.make_addplot(entry_series, type='scatter', markersize=250, marker='o', color='red'),
        ]
        
        if exit_idx is not None:
            if outcome == "WIN":
                ap_list.append(mpf.make_addplot(exit_series, type='scatter', markersize=350, marker='*', color='green'))
            else:
                ap_list.append(mpf.make_addplot(exit_series, type='scatter', markersize=350, marker='X', color='red'))
                
        lines = [(sig['entry'], 'blue'), (sig['sl'], 'red'), (sig['tp1'], 'green')]
        hlines = dict(hlines=[l[0] for l in lines], colors=[l[1] for l in lines], linestyle='--', linewidths=1.5)
        vlines = dict(vlines=[alert_dt_il], colors=['yellow'], linewidths=2)
        
        local_time_str = alert_dt_il.strftime("%b %d, %H:%M")
        title = f"{ticker} {sig['direction']} | Alert Fired: {local_time_str} | Entry: {sig['entry']} | SL: {sig['sl']} | TP1: {sig['tp1']}"
        fname = f"{OUT_DIR}/chart_v5_{i}_{ticker}_{sig['direction']}.png"
        
        s = mpf.make_mpf_style(base_mpf_style='nightclouds', gridstyle=':', facecolor='#0f172a', edgecolor='#334155', figcolor='#0f172a', rc={'text.color': '#e2e8f0', 'axes.labelcolor': '#e2e8f0'})
        
        fig, axes = mpf.plot(data, type='candle', style=s, addplot=ap_list, hlines=hlines, vlines=vlines, title=title, figsize=(11, 7), returnfig=True)
        fig.subplots_adjust(top=0.80, bottom=0.15) 
        
        # Add WIN/LOSS big text to top left corner
        axes[0].text(0.02, 0.95, outcome, transform=axes[0].transAxes, fontsize=28, weight='bold', color=outcome_color, verticalalignment='top')
        
        fig.savefig(fname)
        
        valid_signals.append({
            "ticker": ticker,
            "direction": sig['direction'],
            "entry": sig['entry'],
            "sl": sig['sl'],
            "tp1": sig['tp1'],
            "outcome": outcome,
            "path": fname,
            "time": local_time_str
        })
    except Exception as e:
        print(f"Failed to plot {ticker}: {e}")

with open('valid_signals_v5.json', 'w') as f:
    json.dump(valid_signals, f)
