import sqlite3
import yaml
from datetime import datetime, timedelta
import statistics
import os
from src.flight_v2.db import DB_PATH

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml")
with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

WINDOW_DAYS = config["detection"]["window_days"]
MIN_SAMPLES = config["detection"]["min_samples"]
Z_THRESHOLD = config["detection"]["z_threshold"]
PCT_THRESHOLD = config["detection"]["pct_threshold"]

def flag_deals() -> list[dict]:
    """Read price_history + signals, compute anomalies,
    upsert into deals, return newly flagged deals."""
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cutoff_date = (datetime.now() - timedelta(days=WINDOW_DAYS)).isoformat()
    
    # 1. Get all routes/dates with >= MIN_SAMPLES in the window
    cursor.execute('''
        SELECT origin, destination, depart_date
        FROM price_history
        WHERE captured_at >= ?
        GROUP BY origin, destination, depart_date
        HAVING COUNT(*) >= ?
    ''', (cutoff_date, MIN_SAMPLES))
    
    candidates = cursor.fetchall()
    
    new_deals = []
    
    for row in candidates:
        origin, destination, depart_date = row['origin'], row['destination'], row['depart_date']
        route = f"{origin}-{destination}"
        
        # 2. Get all observations for this route/date in the window
        cursor.execute('''
            SELECT fare_total, source, captured_at 
            FROM price_history
            WHERE origin = ? AND destination = ? AND depart_date = ? AND captured_at >= ?
            ORDER BY captured_at ASC
        ''', (origin, destination, depart_date, cutoff_date))
        
        observations = cursor.fetchall()
        prices = [obs['fare_total'] for obs in observations]
        
        if len(prices) < MIN_SAMPLES:
            continue
            
        latest_obs = observations[-1]
        latest_price = latest_obs['fare_total']
        latest_source = latest_obs['source']
        
        # 3. Compute stats
        median_30d = statistics.median(prices)
        sd_30d = statistics.pstdev(prices)
        
        # Guard against zero variance
        if sd_30d == 0:
            sd_30d = 0.0001
            
        z_score = (latest_price - median_30d) / sd_30d
        pct_drop = ((latest_price - median_30d) / median_30d) * 100
        
        # 4. Check thresholds
        if z_score <= Z_THRESHOLD or pct_drop <= PCT_THRESHOLD:
            # Upsert into deals
            try:
                # Basic confirmed=1 since we are our own truth source, 
                # signal logic comes in Slice 7
                cursor.execute('''
                    INSERT INTO deals 
                    (route, depart_date, fare_total, median_30d, z_score, pct_drop, confirmed, sources, flagged_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (route, depart_date, latest_price, median_30d, z_score, pct_drop, 1, f'["{latest_source}"]', datetime.now().isoformat()))
                
                deal_id = cursor.lastrowid
                
                deal = {
                    "id": deal_id,
                    "route": route,
                    "depart_date": depart_date,
                    "fare_total": latest_price,
                    "pct_drop": pct_drop
                }
                new_deals.append(deal)
                
            except sqlite3.IntegrityError:
                # Unique constraint (route, depart_date, fare_total) hit, already flagged
                pass
                
    conn.commit()
    conn.close()
    
    return new_deals

def run_slice4_gate():
    """Seed fake rows to force a flag."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 5 fake rows with price 1000
    for i in range(5):
        cap_time = (datetime.now() - timedelta(days=5-i)).isoformat()
        cursor.execute('''
            INSERT INTO price_history 
            (origin, destination, depart_date, fare_total, source, captured_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('TLV', 'FAKE', '2026-12-01', 1000.0, 'fast-flights', cap_time))
        
    # 1 fake row with price 700 (30% drop)
    cursor.execute('''
        INSERT INTO price_history 
        (origin, destination, depart_date, fare_total, source, captured_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', ('TLV', 'FAKE', '2026-12-01', 700.0, 'fast-flights', datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    print("Fake rows seeded.")
    
    deals = flag_deals()
    if deals:
        print(f"✅ Slice 4 Gate Passed! Detector fired deals: {deals}")
    else:
        print("❌ Slice 4 Gate Failed! Detector did not fire.")

if __name__ == "__main__":
    run_slice4_gate()
