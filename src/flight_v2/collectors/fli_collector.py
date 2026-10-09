import sqlite3
import time
from datetime import datetime, timedelta
from src.flight_v2.db import DB_PATH
from fli.search import SearchFlights
from fli.models import FlightSearchFilters, Airport, SeatType, TripType, PassengerInfo, FlightSegment

def _parse_fli_result(result) -> dict | None:
    try:
        fare_total = float(result.price)
    except Exception:
        return None

    carrier = getattr(result, "airline", None) or None
    stops = getattr(result, "stops", None)

    return {
        "fare_total": fare_total,
        "base_fare": None,
        "taxes": None,
        "currency": "USD",
        "carrier": carrier,
        "stops": stops,
        "bag_included": None,
        "bag_price": None,
        "source": "fli",
    }

def run(destinations: list[str], days_ahead: int = 45) -> int:
    rows_inserted = 0
    target_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for dest in destinations:
        try:
            filters = FlightSearchFilters(
                trip_type=TripType.ONE_WAY,
                seat_type=SeatType.ECONOMY,
                passenger_info=PassengerInfo(adults=1),
                flight_segments=[FlightSegment(
                    departure_airport=[[getattr(Airport, "TLV")]],
                    arrival_airport=[[getattr(Airport, dest)]],
                    travel_date=target_date
                )]
            )
            results = SearchFlights().search(filters)
            
            if results:
                best = min(results, key=lambda r: getattr(r, "price", 1e9))
                parsed = _parse_fli_result(best)
                if parsed:
                    cursor.execute('''
                        INSERT INTO price_history 
                        (origin, destination, depart_date, return_date, fare_total, base_fare, taxes, currency, carrier, stops, bag_included, bag_price, source, captured_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', ('TLV', dest, target_date, None, parsed["fare_total"], parsed["base_fare"], parsed["taxes"], parsed["currency"], parsed["carrier"], parsed["stops"], parsed["bag_included"], parsed["bag_price"], parsed["source"], datetime.now().isoformat()))
                    rows_inserted += 1
                
        except Exception as e:
            print(f"Error fetching {dest} via fli: {e}")
            
        time.sleep(2)
        
    conn.commit()
    conn.close()
    
    return rows_inserted

if __name__ == "__main__":
    inserted = run(["LHR"], days_ahead=45)
    print(f"Rows inserted: {inserted}")
