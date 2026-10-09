import re

with open("src/tools/stock_tools.py", "r") as f:
    content = f.read()

old_logic = """    # Ribbons
    current_open = df['open'].iloc[-1]
    is_green = current_close > current_open
    
    if current_close > df['EMA20'].iloc[-1] > df['EMA50'].iloc[-1] > df['SMA200'].iloc[-1]:
        trend = "Strong Uptrend"
        score = 80 if is_green else 65  # Downgrade if it's a red candle despite the macro uptrend
    elif current_close < df['EMA20'].iloc[-1] < df['EMA50'].iloc[-1] < df['SMA200'].iloc[-1]:
        trend = "Strong Downtrend"
        score = 80 if not is_green else 65  # Downgrade if it's a green candle despite the macro downtrend
    else:
        trend = "Chop / Transition State"
        score = 40"""

new_logic = """    # Dynamic Ribbons (Ignore 200 SMA on intraday, it lags too much)
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
        score = 40"""

content = content.replace(old_logic, new_logic)


# Now fix the database yo-yo loop
old_db_logic = """                # Check historical momentum
                score = tf_report.get("BuildUp_Score", 40)
                cursor.execute("SELECT score FROM historical_scores WHERE ticker=? AND timeframe=? ORDER BY id DESC LIMIT 2", (ticker, tf))
                history = cursor.fetchall()
                
                momentum_str = "Neutral"
                if len(history) >= 1:
                    last_score = history[0][0]
                    if score > last_score:
                        momentum_str = f"Increasing (was {last_score})"
                        tf_report["BuildUp_Score"] = min(100, score + 5)  # Momentum bonus
                    elif score < last_score:
                        momentum_str = f"Decreasing (was {last_score})"
                        tf_report["BuildUp_Score"] = max(0, score - 5)  # Momentum penalty
                    else:
                        momentum_str = "Stagnant"
                        
                tf_report["Score_Momentum"] = momentum_str
                
                # Save new score
                cursor.execute("INSERT INTO historical_scores (ticker, timeframe, score) VALUES (?, ?, ?)", (ticker, tf, tf_report["BuildUp_Score"]))"""

new_db_logic = """                # Check historical momentum against the RAW base score
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
                cursor.execute("INSERT INTO historical_scores (ticker, timeframe, score) VALUES (?, ?, ?)", (ticker, tf, raw_score))"""

content = content.replace(old_db_logic, new_db_logic)

with open("src/tools/stock_tools.py", "w") as f:
    f.write(content)
