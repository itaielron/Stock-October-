import re

with open("src/daemon.py", "r") as f:
    content = f.read()

old_format = """        | Ticker | TICKER |
        | Signal Timeframe | 15m |
        | HTF Gate (1D Bias) | Bullish/Bearish ✅ |
        | Timeframe Scores | 5m: XX \\| 15m: XX \\| 1H: XX \\| 1D: XX |
        | Trend | Strong Uptrend / etc |
        | RSI Divergence | Bullish RSI Divergence Detected / etc |
        | SMC Structure | Description |
        | BuildUp_Score | 95 (> 85 ✅) |"""

new_format = """        | Ticker | TICKER |
        | Signal Timeframe | 15m |
        | Confidence Level | XX% |
        | HTF Gate (1D Bias) | Bullish/Bearish ✅ |
        | Timeframe Scores | 5m: XX \\| 15m: XX \\| 1H: XX \\| 1D: XX |
        | Trend | Strong Uptrend / etc |
        | RSI Divergence | Bullish RSI Divergence Detected / etc |
        | SMC Structure | Description |
        | BuildUp_Score | 95 (> 85 ✅) |"""

content = content.replace(old_format, new_format)

old_rule = """Start exactly with "FINAL VERIFIED RESULTS". CRITICAL RULE: DO NOT CONTRADICT YOUR MATH. If you suggest a Target 1 that is HIGHER than the Entry, you MUST label the title as a "LONG SETUP". If your Target 1 is LOWER than the Entry, you MUST label the title as a "SHORT SETUP". NEVER output a "SHORT SETUP" if your targets are above your entry price. NEVER set your Stop Loss to the exact same price as your Entry."""

new_rule = """Start exactly with "FINAL VERIFIED RESULTS". CRITICAL RULE: DO NOT CONTRADICT YOUR MATH. If you suggest a Target 1 that is HIGHER than the Entry, you MUST label the title as a "LONG SETUP". If your Target 1 is LOWER than the Entry, you MUST label the title as a "SHORT SETUP". NEVER output a "SHORT SETUP" if your targets are above your entry price. NEVER set your Stop Loss to the exact same price as your Entry. SECOND CRITICAL RULE: You are a strict compiler. Do NOT hallucinate the Confidence Level or BuildUp_Score. You MUST extract them EXACTLY from the `[PRE-CALCULATED SCREENER MATH (USE THESE SCORES EXACTLY)]` section of each ticker's dossier."""

content = content.replace(old_rule, new_rule)

with open("src/daemon.py", "w") as f:
    f.write(content)
