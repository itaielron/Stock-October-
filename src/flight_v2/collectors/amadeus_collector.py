import os
import sqlite3
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from amadeus import Client, ResponseError
from src.flight_v2.db import DB_PATH

load_dotenv()

def run(destinations: list[str]) -> int:
    """Fetch prices for the given destinations via Amadeus, insert into price_history.
    Returns number of rows inserted. Honors quota budget in §7."""
    rows_inserted = 0
    target_date = (datetime.now() + timedelta(days=45)).strftime("%Y-%m-%d")
    
    # Initialize Amadeus client
    client_id = os.environ.get("AMADEUS_CLIENT_ID")
    client_secret = os.environ.get("AMADEUS_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        raise ValueError("AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET must be set in .env")
        
    amadeus = Client(
        client_id=client_id,
        client_secret=client_secret
    )
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for dest in destinations:
        try:
            # Amadeus Flight Offers Search API (v2)
            response = amadeus.shopping.flight_offers_search.get(
                originLocationCode='TLV',
                destinationLocationCode=dest,
                departureDate=target_date,
                adults=1,
                currencyCode='USD',
                max=1
            )
            
            if response.data:
                offer = response.data[0]
                price = float(offer['price']['total'])
                base_fare = float(offer['price']['base'])
                taxes = price - base_fare
                
                # Parse itinerary for carrier and stops
                itinerary = offer['itineraries'][0]
                segments = itinerary['segments']
                stops = len(segments) - 1
                carrier = segments[0]['carrierCode']
                
                cursor.execute('''
                    INSERT INTO price_history 
                    (origin, destination, depart_date, return_date, fare_total, base_fare, taxes, currency, carrier, stops, bag_included, bag_price, source, captured_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', ('TLV', dest, target_date, None, price, base_fare, taxes, 'USD', carrier, stops, None, None, 'amadeus', datetime.now().isoformat()))
                rows_inserted += 1
                
        except ResponseError as error:
            print(f"Amadeus API Error for {dest}: {error}")
        except Exception as e:
            print(f"Error parsing Amadeus response for {dest}: {e}")
            
        time.sleep(1) # Throttle
        
    conn.commit()
    conn.close()
    return rows_inserted

if __name__ == "__main__":
    try:
        inserted = run(["LHR"])
        print(f"Rows inserted: {inserted}")
    except ValueError as e:
        print(f"Slice 2 Blocked: {e}")
