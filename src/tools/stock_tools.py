import sqlite3
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema

def calculate_rsi(data: pd.Series, window=14) -> pd.Series:
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_atr(df: pd.DataFrame, window=14) -> pd.Series:
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(window).mean()

def detect_pivots(df: pd.DataFrame, order=5):
    """Detects swing highs and lows"""
    highs = argrelextrema(df['high'].values, np.greater, order=order)[0]
    lows = argrelextrema(df['low'].values, np.less, order=order)[0]
    return highs, lows

def detect_smc_structure(df: pd.DataFrame):
    """
    Advanced engine for BOS/CHoCH.
    Simplified version for the agent to read.
    """
    highs, lows = detect_pivots(df, order=5)
    
    structure_signals = []
    
    if len(highs) >= 2 and len(lows) >= 2:
        # Check latest price action against last swing high/low
        last_high = df['high'].iloc[highs[-1]]
        last_low = df['low'].iloc[lows[-1]]
        current_close = df['close'].iloc[-1]
        
        if current_close > last_high:
            structure_signals.append("Bullish BOS/CHoCH detected (Price broke recent swing high).")
        elif current_close < last_low:
            structure_signals.append("Bearish BOS/CHoCH detected (Price broke recent swing low).")
        else:
            structure_signals.append(f"Price chopping between support ({last_low:.2f}) and resistance ({last_high:.2f}).")
            
    return " | ".join(structure_signals) if structure_signals else "Structure unclear (Not enough pivots)."

def check_rsi_divergence(df: pd.DataFrame):
    if 'RSI' not in df.columns:
        df['RSI'] = calculate_rsi(df['close'])
        
    highs, lows = detect_pivots(df, order=5)
    divergences = []
    
    if len(lows) >= 2:
        price_l1, price_l2 = df['low'].iloc[lows[-2]], df['low'].iloc[lows[-1]]
        rsi_l1, rsi_l2 = df['RSI'].iloc[lows[-2]], df['RSI'].iloc[lows[-1]]
        if price_l2 < price_l1 and rsi_l2 > rsi_l1:
            divergences.append("Bullish RSI Divergence Detected! (Lower Lows in Price, Higher Lows in RSI).")
            
    if len(highs) >= 2:
        price_h1, price_h2 = df['high'].iloc[highs[-2]], df['high'].iloc[highs[-1]]
        rsi_h1, rsi_h2 = df['RSI'].iloc[highs[-2]], df['RSI'].iloc[highs[-1]]
        if price_h2 > price_h1 and rsi_h2 < rsi_h1:
            divergences.append("Bearish RSI Divergence Detected! (Higher Highs in Price, Lower Highs in RSI).")
            
    # Resolve contradictions: if both appear, cancel them out to prevent LLM confusion
    if len(divergences) > 1:
        return "Contradictory Divergence (Chop) - Ignoring."
    return divergences[0] if divergences else "No significant RSI divergence detected."

def analyze_timeframe(df: pd.DataFrame, htf_bias: str, tf_label: str = '15m') -> dict:
    if df is None or len(df) < 50:
        return {"Error": "Not enough data"}
        
    df['EMA5'] = df['close'].ewm(span=5, adjust=False).mean()
    df['EMA20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['SMA200'] = df['close'].rolling(window=200).mean()
    df['ATR'] = calculate_atr(df)
    df['RSI'] = calculate_rsi(df['close'])
    
    current_close = df['close'].iloc[-1]
    atr = df['ATR'].iloc[-1]
    
    # Dynamic Ribbons (Ignore 200 SMA on intraday, it lags too much)
    current_open = df['open'].iloc[-1]
    is_green = current_close > current_open
    ema20 = df['EMA20'].iloc[-1]
    ema50 = df['EMA50'].iloc[-1]
    
    if tf_label in ['1D', '1H']:
        sma200 = df['SMA200'].iloc[-1]
        is_uptrend = current_close > ema20 > ema50 > sma200
        is_downtrend = current_close < ema20 < ema50 < sma200
    else:
        # Intraday (5m, 15m) ignores 200 SMA for basic trend structure
        is_uptrend = current_close > ema20 > ema50
        is_downtrend = current_close < ema20 < ema50

    if is_uptrend:
        trend = "Strong Uptrend"
        score = 80 if is_green else 65
    elif is_downtrend:
        trend = "Strong Downtrend"
        score = 80 if not is_green else 65
    elif current_close > ema50 and current_close < ema20:
        trend = "Pullback in Uptrend"
        score = 60
    elif current_close < ema50 and current_close > ema20:
        trend = "Pullback in Downtrend"
        score = 60
    else:
        trend = "Chop / Transition State"
        score = 40
        
    # Prevent engine quantization by adding a dynamic gradient based on RSI
    rsi = df['RSI'].iloc[-1]
    import pandas as pd
    if not pd.isna(rsi):
        score += int((rsi - 50) * 0.15) # Adds a small variance based on RSI
        
    tf_points = {'1D': 20, '1H': 15, '15m': 10, '5m': 5}.get(tf_label, 10)
    
    rsi_div = check_rsi_divergence(df)
    if "Bullish RSI Divergence Detected" in rsi_div and "Bull" in htf_bias:
        score += tf_points
    elif "Bearish RSI Divergence Detected" in rsi_div and "Bear" in htf_bias:
        score += tf_points
        
    smc = detect_smc_structure(df)
    if "Bullish BOS/CHoCH" in smc and "Bull" in htf_bias:
        score += tf_points
    elif "Bearish BOS/CHoCH" in smc and "Bear" in htf_bias:
        score += tf_points

        
    # Cap score at 100
    score = min(score, 100)
    
    report = {
        "Trend": trend,
        "Current_Price": round(current_close, 2),
        "RSI_Divergence": rsi_div,
        "SMC_Structure": smc,
        "BuildUp_Score": score
    }
    
    # Trade Setup (R-Multiples) if score is high
    if score >= 85:
        report["Trade_Ready"] = "YES - Criteria Met!"
        # Base the trade direction on the HTF Bias if the current trend is chop
        is_long_setup = "Uptrend" in trend or ("Chop" in trend and "Bull" in htf_bias)
        
        if is_long_setup:
            report["Suggested_StopLoss"] = round(current_close - (1.5 * atr), 2)
            report["Suggested_Target1 (2R)"] = round(current_close + (3.0 * atr), 2)
            report["Suggested_Target2 (4R)"] = round(current_close + (6.0 * atr), 2)
        else: # Downtrend (Short Setup)
            report["Suggested_StopLoss"] = round(current_close + (1.5 * atr), 2)
            report["Suggested_Target1 (2R)"] = round(current_close - (3.0 * atr), 2)
            report["Suggested_Target2 (4R)"] = round(current_close - (6.0 * atr), 2)
    else:
        report["Trade_Ready"] = "NO"
        
    return report

def advanced_screener_engine(ticker: str, dfs: dict, macro_score: int = 0, news_score: int = 0) -> dict:
    """
    dfs is a dictionary of dataframes by timeframe e.g., {'1D': df_1d, '1H': df_1h, '15m': df_15m, '5m': df_5m}
    """
    report = {"Ticker": ticker}
    
    # 1. Higher Timeframe (HTF) Hard-Gate
    htf_df = dfs.get('1D')
    htf_bias = "Neutral"
    if htf_df is not None and len(htf_df) > 50:
        htf_df['EMA50'] = htf_df['close'].ewm(span=50, adjust=False).mean()
        current_close = htf_df['close'].iloc[-1]
        current_open = htf_df['open'].iloc[-1]
        ema50 = htf_df['EMA50'].iloc[-1]
        
        if current_close > ema50:
            if current_close < current_open:
                htf_bias = "Neutral (Weakening Bull)"
            else:
                htf_bias = "Bullish"
        else:
            if current_close > current_open:
                htf_bias = "Neutral (Bouncing Bear)"
            else:
                htf_bias = "Bearish"
                
        report["HTF_Gate (1D Bias)"] = htf_bias
    
    # Analyze all timeframes
    timeframes = ['1D', '1H', '15m', '5m']
    
    conn = sqlite3.connect("hub.db")
    cursor = conn.cursor()
    
    for tf in timeframes:
        if tf in dfs:
            tf_report = analyze_timeframe(dfs[tf], htf_bias, tf)
            
            if "Error" in tf_report:
                tf_report["BuildUp_Score"] = 40  # Neutral instead of 0 to avoid engine stub artifact
                tf_report["Score_Momentum"] = "N/A"
            else:
                # Check historical momentum against the RAW base score
                raw_score = tf_report.get("BuildUp_Score", 40)
                cursor.execute("SELECT score FROM historical_scores WHERE ticker=? AND timeframe=? ORDER BY id DESC LIMIT 1", (ticker, tf))
                history = cursor.fetchall()
                
                momentum_str = "Neutral"
                final_score = raw_score
                
                if len(history) >= 1:
                    last_raw_score = history[0][0]
                    if raw_score > last_raw_score:
                        momentum_str = f"Increasing (was {last_raw_score})"
                        final_score = min(100, raw_score + 5)  # Momentum bonus
                    elif raw_score < last_raw_score:
                        momentum_str = f"Decreasing (was {last_raw_score})"
                        final_score = max(0, raw_score - 5)  # Momentum penalty
                    else:
                        momentum_str = "Stagnant"
                        
                tf_report["BuildUp_Score"] = final_score
                tf_report["Score_Momentum"] = momentum_str
                
                # Save RAW score to DB so it doesn't yo-yo recursively
                cursor.execute("INSERT INTO historical_scores (ticker, timeframe, score) VALUES (?, ?, ?)", (ticker, tf, raw_score))
            
            report[f"Timeframe_{tf}"] = tf_report

    # Calculate SMC Regime-Based Confidence
    score_1d = report.get('Timeframe_1D', {}).get('BuildUp_Score', 40)
    score_1h = report.get('Timeframe_1H', {}).get('BuildUp_Score', 40)
    score_15m = report.get('Timeframe_15m', {}).get('BuildUp_Score', 40)
    score_5m = report.get('Timeframe_5m', {}).get('BuildUp_Score', 40)
    
    tf_15m = report.get('Timeframe_15m', {})
    ltf_reversal = False
    if tf_15m:
        rsi_div = tf_15m.get('RSI_Divergence', '')
        smc_struct = tf_15m.get('SMC_Structure', '')
        # Regime B: 1D is weak but 15m prints strong confirmation
        if ("Divergence Detected" in rsi_div or "BOS/CHoCH" in smc_struct) and score_1d < 70:
            ltf_reversal = True
            
    if ltf_reversal:
        mtf_alignment = (score_1d * 0.1) + (score_1h * 0.2) + (score_15m * 0.4) + (score_5m * 0.3)
    else:
        mtf_alignment = (score_1d * 0.4) + (score_1h * 0.3) + (score_15m * 0.2) + (score_5m * 0.1)
        
    # Normalize macro score (-4 to +4) to a 0-100 scale impact modifier
    # e.g. +4 = 100, 0 = 50, -4 = 0
    macro_norm = ((macro_score + 4) / 8) * 100
    
    # Normalize news score (-1 to +1) to 0-100
    news_norm = ((news_score + 1) / 2) * 100
    
    # Final weighting: 70% MTF, 20% Macro, 10% News
    confidence = (mtf_alignment * 0.70) + (macro_norm * 0.20) + (news_norm * 0.10)
    report["Confidence_Level"] = f"{min(100, max(0, round(confidence)))}%"
    report["SMC_Regime"] = "Regime B (LTF Confirmed Reversal)" if ltf_reversal else "Regime A (Trend Following)"
    
    # Calculate arithmetic targets if 15m data exists
    if '15m' in dfs and len(dfs['15m']) > 0:
        current_price = dfs['15m']['close'].iloc[-1]
        atr = dfs['15m']['ATR'].iloc[-1]
        is_long = "Bull" in report.get("HTF_Gate (1D Bias)", "") or ltf_reversal
        
        report["Entry"] = round(current_price, 2)
        if is_long:
            report["Stop Loss"] = round(current_price - (atr * 1.5), 2)
            report["Target 1 (1R)"] = round(current_price + (atr * 1.5), 2)
            report["Target 2 (2R)"] = round(current_price + (atr * 3.0), 2)
        else:
            report["Stop Loss"] = round(current_price + (atr * 1.5), 2)
            report["Target 1 (1R)"] = round(current_price - (atr * 1.5), 2)
            report["Target 2 (2R)"] = round(current_price - (atr * 3.0), 2)

    conn.commit()
    conn.close()
    return report

def get_macro_sentiment():
    import yfinance as yf
    tickers = ["^VIX", "USO", "^TNX", "DX-Y.NYB"]
    output = "--- INTRADAY MACRO-ECONOMIC CONFLUENCE (15m Momentum) ---\n"
    score = 0
    
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            hist = tk.history(period="1d", interval="15m")
            if len(hist) < 2:
                output += f"{t}: Insufficient intraday data\n"
                continue
            
            close_now = hist['Close'].iloc[-1]
            close_prev = hist['Close'].iloc[0]
            if len(hist) >= 5:
                close_prev = hist['Close'].iloc[-5]
                
            pct_change = ((close_now - close_prev) / close_prev) * 100
            
            if t == "^TNX":
                impact = "BEARISH for Equities" if pct_change > 0 else "BULLISH for Equities"
                if pct_change > 0: score -= 1
                else: score += 1
            elif t == "^VIX":
                impact = "BEARISH for Equities" if pct_change > 0 else "BULLISH for Equities"
                if pct_change > 0: score -= 1
                else: score += 1
            elif t == "DX-Y.NYB":
                impact = "BEARISH for Equities (Strong Dollar)" if pct_change > 0 else "BULLISH for Equities (Weak Dollar)"
                if pct_change > 0: score -= 1
                else: score += 1
            elif t == "USO":
                impact = "BEARISH for Equities (Inflation Risk)" if pct_change > 0 else "BULLISH for Equities (Disinflationary)"
                if pct_change > 0: score -= 1
                else: score += 1
                
            output += f"{t}: {close_now:.2f} (1hr momentum: {pct_change:+.2f}%) -> {impact}\n"
        except Exception as e:
            output += f"{t}: Error fetching ({e})\n"
            
    output += f"\nTOTAL MACRO SCORE: {score} (-4 = Max Bearish, +4 = Max Bullish)\n"
    output += "INSTRUCTION: You must heavily weight your final trade decision based on this INTRADAY macro score. If Macro Score is >= +2, strictly prioritize LONG setups. If <= -2, strictly prioritize SHORT setups.\n"
    return output
