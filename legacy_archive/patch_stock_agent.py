import re

with open("src/agents/stock_agent.py", "r") as f:
    content = f.read()

# Add 1H fetching
old_fetch = """                req_1d = StockBarsRequest(symbol_or_symbols=[ticker], timeframe=TimeFrame.Day, start=datetime.datetime.now()-datetime.timedelta(days=365))
                df_1d = client.get_stock_bars(req_1d).df.reset_index(level=0, drop=True)
                
                req_15m = StockBarsRequest(symbol_or_symbols=[ticker], timeframe=TimeFrame(15, TimeFrameUnit.Minute), start=datetime.datetime.now()-datetime.timedelta(days=10))
                df_15m = client.get_stock_bars(req_15m).df.reset_index(level=0, drop=True)
                
                req_5m = StockBarsRequest(symbol_or_symbols=[ticker], timeframe=TimeFrame(5, TimeFrameUnit.Minute), start=datetime.datetime.now()-datetime.timedelta(days=5))
                df_5m = client.get_stock_bars(req_5m).df.reset_index(level=0, drop=True)"""

new_fetch = """                req_1d = StockBarsRequest(symbol_or_symbols=[ticker], timeframe=TimeFrame.Day, start=datetime.datetime.now()-datetime.timedelta(days=365))
                df_1d = client.get_stock_bars(req_1d).df.reset_index(level=0, drop=True)
                
                req_1h = StockBarsRequest(symbol_or_symbols=[ticker], timeframe=TimeFrame.Hour, start=datetime.datetime.now()-datetime.timedelta(days=30))
                df_1h = client.get_stock_bars(req_1h).df.reset_index(level=0, drop=True)
                
                req_15m = StockBarsRequest(symbol_or_symbols=[ticker], timeframe=TimeFrame(15, TimeFrameUnit.Minute), start=datetime.datetime.now()-datetime.timedelta(days=10))
                df_15m = client.get_stock_bars(req_15m).df.reset_index(level=0, drop=True)
                
                req_5m = StockBarsRequest(symbol_or_symbols=[ticker], timeframe=TimeFrame(5, TimeFrameUnit.Minute), start=datetime.datetime.now()-datetime.timedelta(days=5))
                df_5m = client.get_stock_bars(req_5m).df.reset_index(level=0, drop=True)"""

content = content.replace(old_fetch, new_fetch)

# Add 1H indicators
old_indicators = """                # Indicators
                for df in [df_1d, df_15m, df_5m]:
                    df.ta.ema(length=50, append=True)
                    df.ta.ema(length=200, append=True)
                    df.ta.rsi(length=14, append=True)
                    df.ta.atr(length=14, append=True)"""

new_indicators = """                # Indicators
                for df in [df_1d, df_1h, df_15m, df_5m]:
                    df.ta.ema(length=50, append=True)
                    df.ta.ema(length=200, append=True)
                    df.ta.rsi(length=14, append=True)
                    df.ta.atr(length=14, append=True)"""

content = content.replace(old_indicators, new_indicators)

# Pass 1H to screener
old_screener = """screener_report = advanced_screener_engine(ticker, {'1D': df_1d, '15m': df_15m, '5m': df_5m})"""
new_screener = """screener_report = advanced_screener_engine(ticker, {'1D': df_1d, '1H': df_1h, '15m': df_15m, '5m': df_5m})"""

content = content.replace(old_screener, new_screener)

# Add Confidence to dossier
old_dossier = """- BuildUp_Score: {overall_score}
- SMC Structure: {smc_structure}
- RSI Divergence: {rsi_div}"""

new_dossier = """- BuildUp_Score: {overall_score}
- SMC Structure: {smc_structure}
- RSI Divergence: {rsi_div}
- Confidence_Level: {screener_report.get('Confidence_Level', 'N/A')}"""

content = content.replace(old_dossier, new_dossier)


with open("src/agents/stock_agent.py", "w") as f:
    f.write(content)
