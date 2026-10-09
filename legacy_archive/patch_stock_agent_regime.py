import re

with open("src/agents/stock_agent.py", "r") as f:
    content = f.read()

old_dossier_scores = """- BuildUp_Score: {overall_score}
- SMC Structure: {smc_structure}
- RSI Divergence: {rsi_div}
- Confidence_Level: {screener_report.get('Confidence_Level', 'N/A')}"""

new_dossier_scores = """- SMC Structure: {smc_structure}
- RSI Divergence: {rsi_div}
- SMC Regime: {screener_report.get('SMC_Regime', 'N/A')}
- Confidence_Level: {screener_report.get('Confidence_Level', 'N/A')}"""

content = content.replace(old_dossier_scores, new_dossier_scores)

with open("src/agents/stock_agent.py", "w") as f:
    f.write(content)
