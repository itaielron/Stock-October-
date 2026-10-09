import sqlite3
import re
import mplfinance as mpf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
import os
import json
import time
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from dotenv import load_dotenv

load_dotenv()

OUT_DIR = "/Users/itaielron/.gemini/antigravity/brain/c0df299c-545f-4292-b580-1c4542af62c7"
israel_tz = pytz.timezone('Asia/Jerusalem')
ny_tz = pytz.timezone('US/Eastern')

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
yesterday = (datetime.now() - timedelta(days=5)).isoformat()
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

print(f"Total raw signals: {len(all_signals)}")

for i, sig in enumerate(all_signals):
    ticker = sig['ticker']
    alert_dt_il = datetime.fromisoformat(sig['timestamp'])
    
    if alert_dt_il.tzinfo is None:
        alert_dt_il = israel_tz.localize(alert_dt_il)
        
    local_time_str = alert_dt_il.strftime("%b %d, %H:%M")
        
    alert_est = alert_dt_il.astimezone(ny_tz)
    market_open = alert_est.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = alert_est.replace(hour=16, minute=0, second=0, microsecond=0)
    
    # Must be during live market hours
    if not (market_open <= alert_est <= market_close):
        continue

    end_date = datetime.now()
    start_date = alert_dt_il.astimezone(pytz.UTC) - timedelta(days=1)
    
    try:
        req = StockBarsRequest(symbol_or_symbols=[ticker], timeframe=TimeFrame(5, TimeFrameUnit.Minute), start=start_date, end=end_date, feed="iex")
        time.sleep(0.5) # Prevent Alpaca rate limiting
        data = client.get_stock_bars(req).df
        
        if isinstance(data.index, pd.MultiIndex):
            data = data.reset_index(level=0, drop=True)
            
        if data.empty:
            continue
            
        if data.index.tz is None:
            data.index = data.index.tz_localize('UTC')
        data.index = data.index.tz_convert(israel_tz)
        
        time_diffs = abs(data.index - alert_dt_il)
        entry_idx = time_diffs.argmin()
        actual_candle_close = data['close'].iloc[entry_idx]
        
        # Hallucination Check - if the LLM entry is more than 0.5% away from the actual market price, reject it entirely
        price_diff = abs(actual_candle_close - sig['entry'])
        pct_diff = (price_diff / actual_candle_close) * 100
        if pct_diff > 0.5:
            print(f"Skipping {ticker} at {local_time_str} - Hallucinated Entry: {sig['entry']} vs Real: {actual_candle_close:.2f}")
            continue
            
        # Also skip if SL equals Entry! That's a bad signal (like the NVDA one)
        if sig['entry'] == sig['sl']:
            print(f"Skipping {ticker} at {local_time_str} - SL equals Entry")
            continue
        
        future_data = data.iloc[entry_idx:]
        
        outcome_text = "PENDING"
        outcome_color = "yellow"
        
        tp1_idx = None
        tp2_idx = None
        sl_idx = None
        
        if sig['direction'] == 'LONG':
            for idx in range(len(future_data)):
                row = future_data.iloc[idx]
                abs_idx = entry_idx + idx
                if sl_idx is None and row['low'] <= sig['sl']: sl_idx = abs_idx
                if tp1_idx is None and row['high'] >= sig['tp1']: tp1_idx = abs_idx
                if sig['tp2'] and tp2_idx is None and row['high'] >= sig['tp2']: tp2_idx = abs_idx
        else: # SHORT
            for idx in range(len(future_data)):
                row = future_data.iloc[idx]
                abs_idx = entry_idx + idx
                if sl_idx is None and row['high'] >= sig['sl']: sl_idx = abs_idx
                if tp1_idx is None and row['low'] <= sig['tp1']: tp1_idx = abs_idx
                if sig['tp2'] and tp2_idx is None and row['low'] <= sig['tp2']: tp2_idx = abs_idx
        
        final_exit_idx = None
        if sl_idx is not None and (tp1_idx is None or sl_idx < tp1_idx):
            outcome_text = "LOSS"
            outcome_color = "red"
            final_exit_idx = sl_idx
        elif tp2_idx is not None and (sl_idx is None or tp2_idx < sl_idx):
            outcome_text = "FULL WIN (TP2)"
            outcome_color = "lime"
            final_exit_idx = tp2_idx
        elif tp1_idx is not None and (sl_idx is None or tp1_idx < sl_idx):
            outcome_text = "PARTIAL WIN (TP1)"
            outcome_color = "green"
            final_exit_idx = tp1_idx
            
        is_swing = False
        if final_exit_idx is not None:
            entry_date = data.index[entry_idx].date()
            exit_date = data.index[final_exit_idx].date()
            if exit_date > entry_date:
                is_swing = True
                outcome_text += " - swing"
            
        entry_series = pd.Series(np.nan, index=data.index)
        entry_series.iloc[entry_idx] = sig['entry']
        
        ap_list = [mpf.make_addplot(entry_series, type='scatter', markersize=250, marker='o', color='red')]
        
        if tp1_idx is not None:
            tp1_series = pd.Series(np.nan, index=data.index)
            tp1_series.iloc[tp1_idx] = sig['tp1']
            ap_list.append(mpf.make_addplot(tp1_series, type='scatter', markersize=350, marker='*', color='green'))
            
        if tp2_idx is not None:
            tp2_series = pd.Series(np.nan, index=data.index)
            tp2_series.iloc[tp2_idx] = sig['tp2']
            ap_list.append(mpf.make_addplot(tp2_series, type='scatter', markersize=350, marker='*', color='lime'))
            
        if sl_idx is not None:
            sl_series = pd.Series(np.nan, index=data.index)
            sl_series.iloc[sl_idx] = sig['sl']
            ap_list.append(mpf.make_addplot(sl_series, type='scatter', markersize=350, marker='X', color='red'))
                
        lines = [(sig['entry'], 'blue'), (sig['sl'], 'red'), (sig['tp1'], 'green')]
        if sig['tp2']:
            lines.append((sig['tp2'], 'lime'))
            
        hlines = dict(hlines=[l[0] for l in lines], colors=[l[1] for l in lines], linestyle='--', linewidths=1.5)
        
        unique_dates = np.unique(data.index.date)
        vlines_list = []
        vlines_colors = []
        vlines_styles = []
        
        for d in unique_dates:
            dt_open = israel_tz.localize(datetime(d.year, d.month, d.day, 16, 30))
            dt_close = israel_tz.localize(datetime(d.year, d.month, d.day, 22, 55))
            
            if dt_open >= data.index[0] and dt_open <= data.index[-1]:
                vlines_list.append(dt_open)
                vlines_colors.append('white')
                vlines_styles.append('--')
            
            if dt_close >= data.index[0] and dt_close <= data.index[-1]:
                vlines_list.append(dt_close)
                vlines_colors.append('white')
                vlines_styles.append('--')
        
        vlines_dict = dict(vlines=vlines_list, colors=vlines_colors, linestyle=vlines_styles, linewidths=1.5) if vlines_list else None
        
        title = f"{ticker} {sig['direction']} | Fired: {local_time_str}"
        fname = f"{OUT_DIR}/chart_v10_{i}_{ticker}_{sig['direction']}.png"
        
        s = mpf.make_mpf_style(base_mpf_style='nightclouds', gridstyle=':', facecolor='#0f172a', edgecolor='#334155', figcolor='#0f172a', rc={'text.color': '#e2e8f0', 'axes.labelcolor': '#e2e8f0'})
        
        kwargs = dict(type="candle", style=s, addplot=ap_list, hlines=hlines, title=title, figsize=(12, 7), returnfig=True, show_nontrading=False)
        if vlines_dict:
            kwargs["vlines"] = vlines_dict
        fig, axes = mpf.plot(data, **kwargs)
        fig.subplots_adjust(top=0.80, bottom=0.15) 
        
        axes[0].text(0.02, 0.95, outcome_text, transform=axes[0].transAxes, fontsize=28, weight='bold', color=outcome_color, verticalalignment='top')
        
        for d in unique_dates:
            dt_open = israel_tz.localize(datetime(d.year, d.month, d.day, 16, 30))
            dt_close = israel_tz.localize(datetime(d.year, d.month, d.day, 22, 55))
            
            try:
                open_idx = data.index.get_indexer([dt_open], method='nearest')[0]
                close_idx = data.index.get_indexer([dt_close], method='nearest')[0]
                y_bottom = axes[0].get_ylim()[0]
                axes[0].text(open_idx, y_bottom, ' 16:30', color='white', fontsize=12, verticalalignment='bottom', rotation=90)
                axes[0].text(close_idx, y_bottom, ' 23:00', color='white', fontsize=12, verticalalignment='bottom', rotation=90)
            except Exception:
                pass
        
        fig.savefig(fname)
        
        valid_signals.append({
            "ticker": ticker,
            "direction": sig['direction'],
            "entry": sig['entry'],
            "sl": sig['sl'],
            "tp1": sig['tp1'],
            "tp2": sig['tp2'],
            "outcome": outcome_text,
            "path": fname,
            "time": local_time_str
        })
        print(f"Generated chart for {ticker} at {local_time_str} - {outcome_text}")
    except Exception as e:
        print(f"Failed to plot {ticker}: {e}")

with open('valid_signals_v10.json', 'w') as f:
    json.dump(valid_signals, f)
