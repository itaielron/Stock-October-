import re

with open("src/tools/stock_tools.py", "r") as f:
    content = f.read()

# Replace the historical score block
old_block = """            # Check historical momentum
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

new_block = """            if "Error" in tf_report:
                tf_report["BuildUp_Score"] = 0
                tf_report["Score_Momentum"] = "N/A"
            else:
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
                cursor.execute("INSERT INTO historical_scores (ticker, timeframe, score) VALUES (?, ?, ?)", (ticker, tf, tf_report["BuildUp_Score"]))"""

content = content.replace(old_block, new_block)

with open("src/tools/stock_tools.py", "w") as f:
    f.write(content)
