import json

with open('valid_signals_v10.json', 'r') as f:
    signals = json.load(f)

md = "# All Verified Live Signals (Full Historical Backtest V10)\n\n"
md += "Here is the complete historical performance log of every single valid, non-hallucinated signal generated during live trading hours over the past several days.\n\n"
md += "*(Note: Any signals where the LLM hallucinated the entry price have been strictly quarantined and removed from this report.)*\n\n"
md += "````carousel\n"

for i, sig in enumerate(signals):
    md += f"![{sig['ticker']} {sig['direction']} Setup]({sig['path']})\n"
    md += f"**{sig['ticker']} - {sig['direction']}**\n"
    md += f"- **Signal Time:** {sig['time']}\n"
    md += f"- **Entry:** ${sig['entry']:.2f}\n"
    md += f"- **Stop Loss:** ${sig['sl']:.2f}\n"
    md += f"- **Target 1:** ${sig['tp1']:.2f}\n"
    if sig['tp2']:
        md += f"- **Target 2:** ${sig['tp2']:.2f}\n"
    md += f"- **Trade Outcome:** **{sig['outcome']}**\n\n"
    
    if i < len(signals) - 1:
        md += "<!-- slide -->\n"

md += "````\n"

with open('/Users/itaielron/.gemini/antigravity/brain/c0df299c-545f-4292-b580-1c4542af62c7/visualizations_v10.md', 'w') as f:
    f.write(md)
    
