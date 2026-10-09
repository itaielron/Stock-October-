import yfinance as yf
import numpy as np
import pandas as pd
from scipy.stats import norm
import datetime

def calc_bs_price(S, K, T, r, sigma, opt_type='call'):
    """Black-Scholes Theoretical Price"""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if opt_type == 'call':
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    return max(price, 0.0)

def calc_bs_delta(S, K, T, r, sigma, opt_type='call'):
    """Black-Scholes Delta"""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    if opt_type == 'call':
        return norm.cdf(d1)
    else:
        return norm.cdf(d1) - 1

def recommend_options(ticker_symbol, direction, entry_price, tp1, tp2, sl):
    try:
        tk = yf.Ticker(ticker_symbol)
        expirations = tk.options
        if not expirations:
            return "No options data available for this ticker."
            
        today = datetime.datetime.now().date()
        
        # Find 0-3 DTE and 7+ DTE
        lotto_exp = None
        safe_exp = None
        
        for exp in expirations:
            exp_date = datetime.datetime.strptime(exp, '%Y-%m-%d').date()
            dte = (exp_date - today).days
            
            if 0 <= dte <= 4 and lotto_exp is None:
                lotto_exp = exp
            elif dte >= 7 and safe_exp is None:
                safe_exp = exp
                
            if lotto_exp and safe_exp:
                break
                
        if not lotto_exp: lotto_exp = expirations[0]
        if not safe_exp: safe_exp = expirations[-1] if len(expirations) > 1 else expirations[0]
        
        r = 0.045
        opt_type = 'call' if direction.upper() == 'LONG' else 'put'
        
        def process_chain(exp_date_str, max_price, name_label):
            chain = tk.option_chain(exp_date_str)
            df = chain.calls if opt_type == 'call' else chain.puts
            
            # Filter for liquidity and budget
            df = df[(df['ask'] > 0.05) & (df['ask'] <= max_price) & (df['openInterest'] > 10) & (df['impliedVolatility'] > 0.01)].copy()
            if df.empty:
                return f"No suitable {name_label} contracts under ${max_price:.2f}."
                
            exp_d = datetime.datetime.strptime(exp_date_str, '%Y-%m-%d').date()
            T = max((exp_d - today).days / 365.0, 1/365.0)
            
            # Calculate Delta for leverage sorting
            df['delta'] = df.apply(lambda row: abs(calc_bs_delta(entry_price, row['strike'], T, r, row['impliedVolatility'], opt_type)), axis=1)
            # We want the highest delta within our budget
            best_opt = df.sort_values(by='delta', ascending=False).iloc[0]
            
            strike = best_opt['strike']
            iv = best_opt['impliedVolatility']
            ask = best_opt['ask']
            
            # Project Prices
            proj_tp1 = calc_bs_price(tp1, strike, T, r, iv, opt_type)
            proj_tp2 = calc_bs_price(tp2, strike, T, r, iv, opt_type)
            proj_sl = calc_bs_price(sl, strike, T, r, iv, opt_type)
            
            # Calculate ROIs
            roi_tp1 = ((proj_tp1 - ask) / ask) * 100
            roi_tp2 = ((proj_tp2 - ask) / ask) * 100
            loss_sl = ((proj_sl - ask) / ask) * 100
            
            return f"""**{name_label} Strategy (Exp: {exp_date_str})**
- Contract: {ticker_symbol} ${strike} {opt_type.capitalize()}
- Current Entry (Ask): ${ask:.2f} (${ask*100:.0f})
- Projected Value at TP1 (${tp1}): ${proj_tp1:.2f} ({roi_tp1:+.1f}%)
- Projected Value at TP2 (${tp2}): ${proj_tp2:.2f} ({roi_tp2:+.1f}%)
- Stop Loss Value at SL (${sl}): ${proj_sl:.2f} ({loss_sl:+.1f}%)"""

        output = "### 🎯 AUTOMATED OPTIONS STRATEGY\n\n"
        output += process_chain(lotto_exp, 1.00, "Explosive/Intraday (Budget < $100)")
        output += "\n\n"
        output += process_chain(safe_exp, 1.50, "Safe/Swing (Budget < $150)")
        return output
        
    except Exception as e:
        return f"Options Engine Error: {str(e)}"

if __name__ == "__main__":
    # Test
    print(recommend_options("AAPL", "LONG", 225.0, 230.0, 235.0, 222.0))
