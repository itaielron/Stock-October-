from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from datetime import datetime, timedelta
import os
import pytz
from dotenv import load_dotenv

load_dotenv()

client = StockHistoricalDataClient(
    api_key=os.getenv("APCA_API_KEY_ID"),
    secret_key=os.getenv("APCA_API_SECRET_KEY")
)

end_date = datetime.now()
start_date = end_date - timedelta(days=1)

req = StockBarsRequest(symbol_or_symbols=["MSFT"], timeframe=TimeFrame(5, TimeFrameUnit.Minute), start=start_date, end=end_date, feed="iex")
data = client.get_stock_bars(req).df

print("Alpaca Index Type:", type(data.index))
print("Alpaca Index Name:", data.index.names)
print("Alpaca Index TZ:", data.index.tz)

if hasattr(data.index, 'levels'): # MultiIndex
    data = data.reset_index(level=0, drop=True)

print("First index item:", data.index[0])
print("First index item TZ:", data.index[0].tz)
