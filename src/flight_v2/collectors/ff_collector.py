import sqlite3
import time
from datetime import datetime, timedelta
import yaml
import fast_flights
from src.flight_v2.db import DB_PATH
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml")

with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

ALL_DESTINATIONS = config["destinations"]["europe"] + config["destinations"]["us_east"]
DESTINATIONS_PER_DAY = config["amadeus"]["destinations_per_day"]
DAYS_AHEAD = config["fli"]["days_ahead"]
THROTTLE_SECONDS = config["fli"]["throttle_seconds"]

def get_destinations_for_date(date_obj: datetime) -> list[str]:
    """Deterministically rotate destinations based on day of year."""
    day_of_year = date_obj.timetuple().tm_yday
    pool_size = len(ALL_DESTINATIONS)
    start_idx = (day_of_year * DESTINATIONS_PER_DAY) % pool_size
    
    dests = []
    for i in range(DESTINATIONS_PER_DAY):
        idx = (start_idx + i) % pool_size
        dests.append(ALL_DESTINATIONS[idx])
    return dests

def run(destinations: list[str] = None, days_ahead: int = DAYS_AHEAD) -> int:
    """Fetch prices via fast-flights, insert into price_history.
    If destinations is None, uses deterministic rotation per SPEC §7."""
    
    if destinations is None:
        destinations = get_destinations_for_date(datetime.now())
        
    rows_inserted = 0
    target_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for dest in destinations:
        try:
            q = fast_flights.create_query(
                flights=[fast_flights.FlightQuery(date=target_date, from_airport='TLV', to_airport=dest)],
                trip='one-way',
                currency='USD'
            )
            res = fast_flights.get_flights(q)
            
            if res and len(res) > 0:
                cheapest = res[0]
                price = float(cheapest.price)
                carrier = ", ".join(cheapest.airlines)
                stops = max(0, len(cheapest.flights) - 1)
                
                cursor.execute('''
                    INSERT INTO price_history 
                    (origin, destination, depart_date, return_date, fare_total, currency, carrier, stops, source, captured_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', ('TLV', dest, target_date, None, price, 'USD', carrier, stops, 'fast-flights', datetime.now().isoformat()))
                rows_inserted += 1
                
        except Exception as e:
            print(f"Error fetching {dest}: {e}")
            
        # Polite throttling
        time.sleep(THROTTLE_SECONDS)
        
    conn.commit()
    conn.close()
    
    return rows_inserted

if __name__ == "__main__":
    # Slice 3 Gate verification
    dests_today = get_destinations_for_date(datetime.now())
    dests_tmrw = get_destinations_for_date(datetime.now() + timedelta(days=1))
    
    print(f"Slice 3 Gate Check:")
    print(f"Pool size: {len(ALL_DESTINATIONS)}")
    print(f"Today's {DESTINATIONS_PER_DAY} destinations: {dests_today}")
    print(f"Tomorrow's {DESTINATIONS_PER_DAY} destinations: {dests_tmrw}")
    
    if dests_today != dests_tmrw:
        print("✅ Rotation Strategy verified: consecutive days visit different destinations.")
        inserted = run(dests_today, days_ahead=DAYS_AHEAD)
        print(f"Rows inserted today: {inserted}")
    else:
        print("❌ Rotation Strategy failed.")
