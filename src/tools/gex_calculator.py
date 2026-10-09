import yfinance as yf
import numpy as np
import pandas as pd
from scipy.stats import norm
import datetime

def calculate_gamma(S, K, T, r, sigma):
    """Calculate Black-Scholes Gamma"""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    pdf_d1 = (1.0 / np.sqrt(2.0 * np.pi)) * np.exp(-0.5 * d1 ** 2)
    gamma = pdf_d1 / (S * sigma * np.sqrt(T))
    return gamma

def get_gex_walls(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        spot_price = tk.history(period="1d")['Close'].iloc[-1]
        
        # Get the nearest expiration date
        expirations = tk.options
        if not expirations:
            return "No options data available."
            
        nearest_exp = expirations[0]
        chain = tk.option_chain(nearest_exp)
        
        calls = chain.calls
        puts = chain.puts
        
        r = 0.045 # Risk free rate approx 4.5%
        today = datetime.datetime.now()
        exp_date = datetime.datetime.strptime(nearest_exp, '%Y-%m-%d')
        T = max((exp_date - today).days / 365.0, 1/365.0) # Avoid zero DTE crash
        
        max_call_gex = 0
        call_wall_strike = 0
        
        for idx, row in calls.iterrows():
            strike = row['strike']
            iv = row['impliedVolatility']
            oi = row['openInterest']
            if iv > 0 and oi > 0:
                gamma = calculate_gamma(spot_price, strike, T, r, iv)
                gex = gamma * oi * 100
                if gex > max_call_gex:
                    max_call_gex = gex
                    call_wall_strike = strike
                    
        max_put_gex = 0
        put_wall_strike = 0
        
        for idx, row in puts.iterrows():
            strike = row['strike']
            iv = row['impliedVolatility']
            oi = row['openInterest']
            if iv > 0 and oi > 0:
                gamma = calculate_gamma(spot_price, strike, T, r, iv)
                gex = gamma * oi * 100
                if gex > max_put_gex:
                    max_put_gex = gex
                    put_wall_strike = strike
                    
        return f"OPTIONS GEX (Exp: {nearest_exp}): Call Wall (Major Resistance) at ${call_wall_strike}. Put Wall (Major Support) at ${put_wall_strike}."
    except Exception as e:
        return f"GEX Data Error: {str(e)}"

if __name__ == "__main__":
    print(get_gex_walls("AAPL"))
