import re

with open('src/agents/stock_agent.py', 'r') as f:
    content = f.read()

# Replace `return "\n\n".join(results)` with the injection code
new_return = '''
        from src.tools.stock_tools import get_macro_sentiment
        from src.tools.sentiment_tools import get_news_sentiment
        try:
            macro_text = get_macro_sentiment()
        except:
            macro_text = "Macro Data Unavailable"
            
        try:
            news_text = get_news_sentiment()
        except:
            news_text = "News Data Unavailable"
            
        results.insert(0, f"=== SYSTEM INJECTION: MACRO & NEWS ===\\n{macro_text}\\n\\n--- TOP FINANCIAL HEADLINES ---\\n{news_text}\\n====================================\\n\\n")
        return "\\n\\n".join(results)
'''

content = content.replace('        return "\\n\\n".join(results)', new_return.lstrip())

with open('src/agents/stock_agent.py', 'w') as f:
    f.write(content)
