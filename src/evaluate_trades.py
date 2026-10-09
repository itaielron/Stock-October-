import sqlite3
import re
import yfinance as yf
from datetime import datetime, timedelta
import pytz

def parse_alert(message, timestamp_str):
    # Try to find all blocks starting with 🟢 or 🔴
    signals = []
    
    # Simple regex to extract the table values
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
            "timestamp": timestamp_str
        })
    return signals

def run_evaluation():
    conn = sqlite3.connect("hub.db")
    cursor = conn.cursor()
    # Get last 24h of alerts
    yesterday = (datetime.now() - timedelta(days=2)).isoformat()
    cursor.execute("SELECT timestamp, message FROM alerts WHERE category='STOCK_SWEEP' AND (message LIKE '%🟢%' OR message LIKE '%🔴%') AND timestamp > ?", (yesterday,))
    rows = cursor.fetchall()
    conn.close()
    
    all_signals = []
    for row in rows:
        signals = parse_alert(row[1], row[0])
        all_signals.extend(signals)
        
    print(f"Found {len(all_signals)} signals to evaluate.")
    
    results = []
    for sig in all_signals:
        ticker = sig['ticker']
        print(f"Evaluating {sig['direction']} on {ticker} @ {sig['entry']}")
        
        # Download 1m data for the last 2 days
        try:
            data = yf.download(ticker, period="2d", interval="1m", progress=False)
            if data.empty:
                continue
                
            # Filter data to only after the alert timestamp
            alert_dt = datetime.fromisoformat(sig['timestamp']).replace(tzinfo=pytz.UTC)
            
            # Yfinance data is usually tz-aware (America/New_York). Convert alert_dt
            if data.index.tz is not None:
                alert_dt = alert_dt.astimezone(data.index.tz)
            else:
                alert_dt = alert_dt.replace(tzinfo=None)
                
            future_data = data[data.index >= alert_dt]
            
            if future_data.empty:
                results.append(f"{ticker} {sig['direction']}: No market data since alert.")
                continue
                
            # Simulate
            outcome = "PENDING"
            for index, row in future_data.iterrows():
                high = float(row['High'].iloc[0]) if isinstance(row['High'], pd.Series) else float(row['High'])
                low = float(row['Low'].iloc[0]) if isinstance(row['Low'], pd.Series) else float(row['Low'])
                
                if sig['direction'] == "LONG":
                    if low <= sig['sl']:
                        outcome = "LOSS (Hit Stop Loss)"
                        break
                    elif high >= sig['tp1']:
                        outcome = "WIN (Hit Target 1)"
                        break
                else: # SHORT
                    if high >= sig['sl']:
                        outcome = "LOSS (Hit Stop Loss)"
                        break
                    elif low <= sig['tp1']:
                        outcome = "WIN (Hit Target 1)"
                        break
                        
            results.append(f"{ticker} {sig['direction']}: Entry={sig['entry']}, SL={sig['sl']}, TP={sig['tp1']} -> OUTCOME: {outcome}")
        except Exception as e:
            print(f"Error evaluating {ticker}: {e}")
            
    # Feed to Optimization Agent
    print("\n--- RESULTS ---")
    for r in results:
        print(r)
        
    return results

if __name__ == "__main__":
    import pandas as pd
    run_evaluation()
