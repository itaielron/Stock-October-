import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np

def calculate_mtf_zscore(ticker_symbol, intervals=["1m", "5m", "15m", "1h", "1d"]):
    """Calculates a normalized momentum score across multiple timeframes."""
    score = 0
    try:
        tk = yf.Ticker(ticker_symbol)
        for interval in intervals:
            # Map interval to appropriate period
            period = "1d" if interval == "1m" else "5d" if interval in ["5m", "15m"] else "1mo" if interval == "1h" else "6mo"
            df = tk.history(period=period, interval=interval)
            
            if df.empty or len(df) < 20:
                continue
                
            # Calculate RSI
            df.ta.rsi(length=14, append=True)
            rsi = df['RSI_14'].iloc[-1]
            
            # Calculate EMA 9 and 21
            df.ta.ema(length=9, append=True)
            df.ta.ema(length=21, append=True)
            ema9 = df['EMA_9'].iloc[-1]
            ema21 = df['EMA_21'].iloc[-1]
            
            # Momentum logic
            # If EMA 9 > EMA 21, it's trending up
            trend_val = 1 if ema9 > ema21 else -1
            
            # RSI logic (exhaustion)
            if rsi > 70:
                trend_val -= 1 # Overbought, momentum waning
            elif rsi < 30:
                trend_val += 1 # Oversold, momentum bottoming
                
            # Weight higher timeframes more
            weight = 1 if interval in ["1m", "5m"] else 2 if interval in ["15m", "1h"] else 3
            
            score += (trend_val * weight)
            
    except Exception as e:
        pass
        
    return score

def get_sentiment_tracker():
    tickers = {
        "^TNX": "BEARISH", # If TNX (Yields) is UP (positive score), it's BEARISH for Equities
        "^VIX": "BEARISH", # If VIX (Vol) is UP, it's BEARISH for Equities
        "DX-Y.NYB": "BEARISH", # If DXY (Dollar) is UP, it's BEARISH for Equities
        "USO": "BEARISH" # If USO (Oil) is UP, it's BEARISH for Equities
    }
    
    output = "--- SENTIMENT TRACKER (MTF Z-SCORE CONFLUENCE) ---\n"
    net_pulse = 0
    
    for t, correlation in tickers.items():
        # Score is positive if the asset is trending UP, negative if trending DOWN
        momentum_score = calculate_mtf_zscore(t)
        
        # Invert the impact based on correlation to equities
        if correlation == "BEARISH":
            equity_impact = -momentum_score
        else:
            equity_impact = momentum_score
            
        net_pulse += equity_impact
        
        status = "BULLISH for Equities" if equity_impact > 0 else "BEARISH for Equities" if equity_impact < 0 else "NEUTRAL"
        output += f"{t} Multi-Timeframe Momentum: {momentum_score} -> {status}\n"
        
    output += f"\nTOTAL MARKET PULSE SCORE: {net_pulse} (Negative = Risk Off, Positive = Risk On)\n"
    output += "INSTRUCTION: You must heavily weight your final trade decision based on this Pulse Score. If <= -5, STRICTLY FORBIDDEN from taking LONG setups. If >= +5, STRICTLY FORBIDDEN from taking SHORT setups.\n"
    return output
