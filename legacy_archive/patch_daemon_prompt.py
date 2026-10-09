import re

with open("src/daemon.py", "r") as f:
    content = f.read()

old_format = """        You MUST format your output EXACTLY like the following example. ONLY list trades that meet strict criteria (Score > 85). Do NOT list or mention the tickers that failed. Do NOT add any conversational fluff (no "Here are the results"). Start exactly with "FINAL VERIFIED RESULTS". CRITICAL RULE: DO NOT CONTRADICT YOUR MATH. If you suggest a Target 1 that is HIGHER than the Entry, you MUST label the title as a "LONG SETUP". If your Target 1 is LOWER than the Entry, you MUST label the title as a "SHORT SETUP". NEVER output a "SHORT SETUP" if your targets are above your entry price. NEVER set your Stop Loss to the exact same price as your Entry. SECOND CRITICAL RULE: You are a strict compiler. Do NOT hallucinate the Confidence Level or BuildUp_Score. You MUST extract them EXACTLY from the `[PRE-CALCULATED SCREENER MATH (USE THESE SCORES EXACTLY)]` section of each ticker's dossier.
        
        # FINAL VERIFIED RESULTS
        
        🟢 TICKER_SYMBOL (Company Name) — LONG/SHORT SETUP — VERIFIED ✅
        | Parameter | Value (USD) |
        | --- | --- |
        | Ticker | TICKER |
        | Signal Timeframe | 15m |
        | Confidence Level | XX% |
        | HTF Gate (1D Bias) | Bullish/Bearish ✅ |
        | Timeframe Scores | 5m: XX \| 15m: XX \| 1H: XX \| 1D: XX |
        | Trend | Strong Uptrend / etc |
        | RSI Divergence | Bullish RSI Divergence Detected / etc |
        | SMC Structure | Description |
        | BuildUp_Score | 95 (> 85 ✅) |
        | Trade_Ready | YES - Criteria Met! ✅ |
        | Entry (Current Price zone) | ~VALUE |
        | Suggested Stop Loss | VALUE |
        | Suggested Target 1 (2R) | VALUE |
        | Suggested Target 2 (4R) | VALUE |"""

new_format = """        You MUST format your output EXACTLY like the following example. ONLY list trades that meet strict criteria (Confidence Level > 80%). Do NOT list or mention the tickers that failed. Do NOT add any conversational fluff (no "Here are the results"). Start exactly with "FINAL VERIFIED RESULTS". CRITICAL RULE: DO NOT CONTRADICT YOUR MATH. If you suggest a Target 1 that is HIGHER than the Entry, you MUST label the title as a "LONG SETUP". If your Target 1 is LOWER than the Entry, you MUST label the title as a "SHORT SETUP". NEVER output a "SHORT SETUP" if your targets are above your entry price. NEVER set your Stop Loss to the exact same price as your Entry. SECOND CRITICAL RULE: You are a strict compiler. Do NOT hallucinate the Confidence Level. You MUST extract it EXACTLY from the `[PRE-CALCULATED SCREENER MATH (USE THESE SCORES EXACTLY)]` section of each ticker's dossier.
        
        # FINAL VERIFIED RESULTS
        
        🟢 TICKER_SYMBOL (Company Name) — LONG/SHORT SETUP — VERIFIED ✅
        | Parameter | Value (USD) |
        | --- | --- |
        | Ticker | TICKER |
        | Signal Timeframe | 15m |
        | Confidence Level | 87% (> 80% ✅) |
        | SMC Regime | Regime B (LTF Confirmed Reversal) / etc |
        | HTF Gate (1D Bias) | Bullish/Bearish ✅ |
        | Timeframe Scores | 5m: XX \| 15m: XX \| 1H: XX \| 1D: XX |
        | Trend | Strong Uptrend / etc |
        | RSI Divergence | Bullish RSI Divergence Detected / etc |
        | SMC Structure | Description |
        | Trade_Ready | YES - Criteria Met! ✅ |
        | Entry (Current Price zone) | ~VALUE |
        | Suggested Stop Loss | VALUE |
        | Suggested Target 1 (2R) | VALUE |
        | Suggested Target 2 (4R) | VALUE |"""

content = content.replace(old_format, new_format)

with open("src/daemon.py", "w") as f:
    f.write(content)
