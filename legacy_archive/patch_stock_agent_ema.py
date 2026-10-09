import re

with open("src/agents/stock_agent.py", "r") as f:
    content = f.read()

old_dossier = """- 1D Trend: {'Bullish' if current_price > df_1d['EMA_50'].iloc[-1] and df_1d['close'].iloc[-1] > df_1d['open'].iloc[-1] else ('Neutral (Weakening Bull)' if current_price > df_1d['EMA_50'].iloc[-1] else ('Neutral (Bouncing Bear)' if df_1d['close'].iloc[-1] > df_1d['open'].iloc[-1] else 'Bearish'))}"""

new_dossier = """- 1D Trend: {'Bullish' if 'EMA_50' in df_1d.columns and current_price > df_1d['EMA_50'].iloc[-1] and df_1d['close'].iloc[-1] > df_1d['open'].iloc[-1] else ('Neutral (Weakening Bull)' if 'EMA_50' in df_1d.columns and current_price > df_1d['EMA_50'].iloc[-1] else ('Neutral (Bouncing Bear)' if df_1d['close'].iloc[-1] > df_1d['open'].iloc[-1] else 'Bearish'))}"""

content = content.replace(old_dossier, new_dossier)

old_ema_15m = """                ema50_15m = df_15m['EMA_50'].iloc[-1] if not pd.isna(df_15m['EMA_50'].iloc[-1]) else 0"""
new_ema_15m = """                ema50_15m = df_15m['EMA_50'].iloc[-1] if 'EMA_50' in df_15m.columns and not pd.isna(df_15m['EMA_50'].iloc[-1]) else 0"""
content = content.replace(old_ema_15m, new_ema_15m)

with open("src/agents/stock_agent.py", "w") as f:
    f.write(content)
