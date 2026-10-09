import re

with open("src/agents/stock_agent.py", "r") as f:
    content = f.read()

old_block = """        try: macro_text = get_sentiment_tracker()
        except: macro_text = "Macro Data Unavailable"
        try: news_text = get_news_sentiment()
        except: news_text = "News Data Unavailable"
        
        results = [f"=== SYSTEM INJECTION: MACRO & NEWS ===\\n{macro_text}\\n\\n--- TOP FINANCIAL HEADLINES ---\\n{news_text}\\n====================================\\n\\n"]"""

new_block = """        macro_score = 0
        news_score = 0
        try: 
            macro_text = get_sentiment_tracker()
            m = __import__('re').search(r"TOTAL MACRO SCORE: ([-+]?\d+)", macro_text)
            if m: macro_score = int(m.group(1))
        except: 
            macro_text = "Macro Data Unavailable"
            
        try: 
            news_text = get_news_sentiment()
            if "BULLISH" in news_text.upper(): news_score = 1
            if "BEARISH" in news_text.upper(): news_score = -1
        except: 
            news_text = "News Data Unavailable"
            
        results = [f"=== SYSTEM INJECTION: MACRO & NEWS ===\\n{macro_text}\\n\\n--- TOP FINANCIAL HEADLINES ---\\n{news_text}\\n====================================\\n\\n"]"""

content = content.replace(old_block, new_block)

old_call = """screener_report = advanced_screener_engine(ticker, {'1D': df_1d, '1H': df_1h, '15m': df_15m, '5m': df_5m})"""
new_call = """screener_report = advanced_screener_engine(ticker, {'1D': df_1d, '1H': df_1h, '15m': df_15m, '5m': df_5m}, macro_score, news_score)"""

content = content.replace(old_call, new_call)

with open("src/agents/stock_agent.py", "w") as f:
    f.write(content)
