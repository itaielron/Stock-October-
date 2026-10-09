from crewai import Agent
from crewai.tools import BaseTool
import json
from datetime import datetime, timedelta


class GoogleFlightsTool(BaseTool):
    name: str = "Google Flights Scraper"
    description: str = "Search for cheap flights. Pass origin, destination, and the outbound date (YYYY-MM-DD). It automatically searches for a 7-day round-trip and includes baggage fees."
    
    def _run(self, origin: str, dest: str, date: str) -> str:
        try:
            import fast_flights
            from datetime import datetime, timedelta
            outbound_date = datetime.strptime(date, "%Y-%m-%d")
            return_date = outbound_date + timedelta(days=7)
            
            q = fast_flights.create_query(
                flights=[
                    fast_flights.FlightQuery(date=outbound_date.strftime("%Y-%m-%d"), from_airport=origin, to_airport=dest),
                    fast_flights.FlightQuery(date=return_date.strftime("%Y-%m-%d"), from_airport=dest, to_airport=origin)
                ],
                trip="round-trip",
                currency="USD",
                carry_on_bags=1,
                checked_bags=1
            )
            
            res = fast_flights.get_flights(q)
            
            flights_data = []
            seen_signatures = set()
            
            for f in res:
                # Deduplication logic
                signature = f"{f.price}_" + "_".join(f.airlines)
                if signature in seen_signatures:
                    continue
                
                outbound_legs = []
                warnings = []
                total_duration_mins = 0
                is_valid = True
                
                # Check arrival date
                arrival_date_str = outbound_date.strftime("%Y-%m-%d")
                
                if len(f.flights) > 0:
                    arrival_time = f.flights[-1].arrival
                    if arrival_time:
                        arrival_date_str = str(arrival_time).split(" ")[0]
                        if arrival_date_str != outbound_date.strftime("%Y-%m-%d"):
                            warnings.append("⚠ Arrives next day")
                
                for i, leg in enumerate(f.flights):
                    leg_str = f"{leg.from_airport.code} -> {leg.to_airport.code} ({str(leg.departure)} to {str(leg.arrival)})"
                    outbound_legs.append(leg_str)
                    
                    if leg.departure and leg.arrival:
                        try:
                            # fast_flights might return string or datetime
                            dep = leg.departure if isinstance(leg.departure, datetime) else datetime.strptime(str(leg.departure), "%Y-%m-%d %H:%M:%S")
                            arr = leg.arrival if isinstance(leg.arrival, datetime) else datetime.strptime(str(leg.arrival), "%Y-%m-%d %H:%M:%S")
                            total_duration_mins += (arr - dep).total_seconds() / 60
                        except:
                            pass
                    
                    # Layover logic
                    if i < len(f.flights) - 1:
                        next_leg = f.flights[i+1]
                        if leg.arrival and next_leg.departure:
                            try:
                                arr = leg.arrival if isinstance(leg.arrival, datetime) else datetime.strptime(str(leg.arrival), "%Y-%m-%d %H:%M:%S")
                                next_dep = next_leg.departure if isinstance(next_leg.departure, datetime) else datetime.strptime(str(next_leg.departure), "%Y-%m-%d %H:%M:%S")
                                layover_mins = (next_dep - arr).total_seconds() / 60
                                total_duration_mins += layover_mins
                                
                                if layover_mins < 60:
                                    warnings.append(f"⚠ Risky connection at {leg.to_airport.code} ({int(layover_mins)}m)")
                                if layover_mins > 720:
                                    is_valid = False # Reject layovers > 12h
                            except:
                                pass
                
                if not is_valid:
                    continue # Skip this itinerary
                    
                seen_signatures.add(signature)
                
                # Link builder fix
                booking_link = f"https://www.google.com/travel/flights?q=Flights%20to%20{dest}%20from%20{origin}%20on%20{outbound_date.strftime('%Y-%m-%d')}%20through%20{return_date.strftime('%Y-%m-%d')}"
                
                flights_data.append({
                    "airlines": ", ".join(f.airlines),
                    "total_usd_price_for_roundtrip": f.price,
                    "price_is_verified_roundtrip": False, # Since we only see outbound
                    "outbound_route": " | ".join(outbound_legs),
                    "return_route": "NOT PROVIDED (Verify manually)",
                    "total_travel_time_hours": round(total_duration_mins / 60, 1) if total_duration_mins > 0 else "N/A",
                    "warnings": ", ".join(warnings) if warnings else "None",
                    "booking_link": booking_link
                })
                
                if len(flights_data) >= 3:
                    break
                
            return json.dumps({
                "origin": origin,
                "destination": dest,
                "requested_outbound_date": outbound_date.strftime("%Y-%m-%d"),
                "requested_return_date": return_date.strftime("%Y-%m-%d"),
                "top_options": flights_data,
                "instruction": "You MUST display the 'warnings', 'total_travel_time_hours', and use the exact 'booking_link' provided."
            }, indent=2)
        except Exception as e:
            return f"Error scraping flights: {str(e)}"


def create_flight_agent(llm):
    return Agent(
        role='Vacation Deal Finder',
        goal='Find incredibly cheap round-trip flights from Tel Aviv (TLV) to Europe for 1 adult. You must use the scraper to get real prices.',
        backstory='You are a frugal Israeli travel expert. You never hallucinate prices. You always rely on the scraper tool.',
        verbose=True,
        allow_delegation=False,
        tools=[GoogleFlightsTool()],
        llm=llm
    )
