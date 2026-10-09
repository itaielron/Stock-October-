import re

with open("src/tools/stock_tools.py", "r") as f:
    content = f.read()
    
# We need to pass the ticker and tf into analyze_timeframe so it can query the DB.
# Let's just modify advanced_screener_engine to do the DB lookup and insert.

# First, add sqlite3 import at the top
if 'import sqlite3' not in content:
    content = "import sqlite3\n" + content

engine_old = """    # Analyze all timeframes
    timeframes = ['1D', '1H', '15m', '5m']
    for tf in timeframes:
        if tf in dfs:
            report[f"Timeframe_{tf}"] = analyze_timeframe(dfs[tf], htf_bias)

    return report"""

engine_new = """    # Analyze all timeframes
    timeframes = ['1D', '1H', '15m', '5m']
    
    conn = sqlite3.connect("hub.db")
    cursor = conn.cursor()
    
    for tf in timeframes:
        if tf in dfs:
            tf_report = analyze_timeframe(dfs[tf], htf_bias)
            
            # Check historical momentum
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
            cursor.execute("INSERT INTO historical_scores (ticker, timeframe, score) VALUES (?, ?, ?)", (ticker, tf, tf_report["BuildUp_Score"]))
            
            report[f"Timeframe_{tf}"] = tf_report

    conn.commit()
    conn.close()
    return report"""

content = content.replace(engine_old, engine_new)

with open("src/tools/stock_tools.py", "w") as f:
    f.write(content)
