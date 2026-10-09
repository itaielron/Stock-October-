import re

with open("src/tools/stock_tools.py", "r") as f:
    content = f.read()

old_sig = """def advanced_screener_engine(ticker: str, dfs: dict) -> dict:"""
new_sig = """def advanced_screener_engine(ticker: str, dfs: dict, macro_score: int = 0, news_score: int = 0) -> dict:"""
content = content.replace(old_sig, new_sig)

old_return = """    conn.commit()
    conn.close()
    return report"""

new_return = """    # Calculate SMC Regime-Based Confidence
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

    conn.commit()
    conn.close()
    return report"""

content = content.replace(old_return, new_return)

with open("src/tools/stock_tools.py", "w") as f:
    f.write(content)
