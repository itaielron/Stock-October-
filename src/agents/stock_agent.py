from crewai import Agent
from crewai.tools import BaseTool
import json
import os
import datetime
import numpy as np
import pandas as pd
import pandas_ta as ta
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

def find_swings(df, window=5):
    """Find local swing highs and lows"""
    highs = []
    lows = []
    for i in range(window, len(df)-window):
        if df['high'].iloc[i] == max(df['high'].iloc[i-window:i+window+1]):
            highs.append(df['high'].iloc[i])
        if df['low'].iloc[i] == min(df['low'].iloc[i-window:i+window+1]):
            lows.append(df['low'].iloc[i])
    return highs, lows

class AdvancedSMCAlpacaTool(BaseTool):
    name: str = "Live SMC Market Engine"
    description: str = "Fetch pre-calculated technical dossiers including RSI, EMAs, Fib Clusters, and Options GEX."
    
    def _run(self, symbols: str) -> str:
        import ast
        try:
            tickers = ast.literal_eval(symbols) if '[' in symbols else [symbols]
        except Exception:
            tickers = [symbols]

        client = StockHistoricalDataClient(
            api_key=os.getenv("APCA_API_KEY_ID"),
            secret_key=os.getenv("APCA_API_SECRET_KEY")
        )

        from src.tools.sentiment_tracker import get_sentiment_tracker
        from src.tools.sentiment_tools import get_news_sentiment
        from src.tools.gex_calculator import get_gex_walls
        
        macro_score = 0
        news_score = 0
        try: 
            macro_text = get_sentiment_tracker()
            m = __import__('re').search(r"TOTAL MARKET PULSE SCORE: ([-+]?\d+)", macro_text)
            if m: macro_score = int(m.group(1))
            # Normalize from -36/+36 to -4/+4 for the engine
            macro_score = max(-4, min(4, round(macro_score / 9)))
        except: 
            macro_text = "Macro Data Unavailable"
            
        try: 
            news_text = get_news_sentiment()
            if "BULLISH" in news_text.upper(): news_score = 1
            if "BEARISH" in news_text.upper(): news_score = -1
        except: 
            news_text = "News Data Unavailable"
            
        results = [f"=== SYSTEM INJECTION: MACRO & NEWS ===\n{macro_text}\n\n--- TOP FINANCIAL HEADLINES ---\n{news_text}\n====================================\n\n"]

        for ticker in tickers:
            try:
                # 250 bars for 1D
                req_1d = StockBarsRequest(symbol_or_symbols=[ticker], timeframe=TimeFrame.Day, start=datetime.datetime.now()-datetime.timedelta(days=365))
                df_1d = client.get_stock_bars(req_1d).df.reset_index(level=0, drop=True)
                
                req_1h = StockBarsRequest(symbol_or_symbols=[ticker], timeframe=TimeFrame.Hour, start=datetime.datetime.now()-datetime.timedelta(days=30))
                df_1h = client.get_stock_bars(req_1h).df.reset_index(level=0, drop=True)
                
                req_15m = StockBarsRequest(symbol_or_symbols=[ticker], timeframe=TimeFrame(15, TimeFrameUnit.Minute), start=datetime.datetime.now()-datetime.timedelta(days=10))
                df_15m = client.get_stock_bars(req_15m).df.reset_index(level=0, drop=True)
                
                req_5m = StockBarsRequest(symbol_or_symbols=[ticker], timeframe=TimeFrame(5, TimeFrameUnit.Minute), start=datetime.datetime.now()-datetime.timedelta(days=5))
                df_5m = client.get_stock_bars(req_5m).df.reset_index(level=0, drop=True)
                
                current_price = df_5m['close'].iloc[-1]
                
                # Indicators
                for df in [df_1d, df_1h, df_15m, df_5m]:
                    df.ta.ema(length=50, append=True)
                    df.ta.ema(length=200, append=True)
                    df.ta.rsi(length=14, append=True)
                    df.ta.atr(length=14, append=True)
                
                # Fibs
                highs, lows = find_swings(df_1d, window=10)
                macro_high = max(highs[-3:]) if len(highs) >= 3 else df_1d['high'].max()
                macro_low = min(lows[-3:]) if len(lows) >= 3 else df_1d['low'].min()
                fib_38 = macro_high - (0.382 * (macro_high - macro_low))
                fib_50 = macro_high - (0.500 * (macro_high - macro_low))
                fib_61 = macro_high - (0.618 * (macro_high - macro_low))
                
                ema50_15m = df_15m['EMA_50'].iloc[-1] if 'EMA_50' in df_15m.columns and not pd.isna(df_15m['EMA_50'].iloc[-1]) else 0
                cluster_alert = "None"
                for fib, name in [(fib_38, "38.2%"), (fib_50, "50%"), (fib_61, "61.8%")]:
                    if fib > 0 and abs(ema50_15m - fib) / fib < 0.005:
                        cluster_alert = f"🔥 HIGH CONFLUENCE CLUSTER: ${fib:.2f} ({name} Fib + 15m 50-EMA) -> EXTREME LIQUIDITY ZONE"
                
                # GEX
                gex_info = get_gex_walls(ticker)
                
                from src.tools.stock_tools import advanced_screener_engine
                screener_report = advanced_screener_engine(ticker, {'1D': df_1d, '1H': df_1h, '15m': df_15m, '5m': df_5m}, macro_score, news_score)
                
                # Extract scores from report for easy Manager parsing
                tf_scores = []
                for tf in ['5m', '15m', '1H', '1D']:
                    tf_key = f"Timeframe_{tf}"
                    if tf_key in screener_report:
                        tf_scores.append(f"{tf}: {screener_report[tf_key].get('BuildUp_Score', 'N/A')}")
                    else:
                        tf_scores.append(f"{tf}: N/A")
                tf_scores_str = " | ".join(tf_scores)
                
                # We'll use 15m as the main summary for the dossier since that's what's typically traded
                main_tf_report = screener_report.get('Timeframe_15m', {})
                overall_score = main_tf_report.get('BuildUp_Score', 'N/A')
                smc_structure = main_tf_report.get('SMC_Structure', 'N/A')
                rsi_div = main_tf_report.get('RSI_Divergence', 'N/A')
                
                dossier = f"""[{ticker} - COMPREHENSIVE TECHNICAL DOSSIER]
- Live Price: ${current_price:.2f}
- 1D Trend: {'Bullish' if 'EMA_50' in df_1d.columns and current_price > df_1d['EMA_50'].iloc[-1] and df_1d['close'].iloc[-1] > df_1d['open'].iloc[-1] else ('Neutral (Weakening Bull)' if 'EMA_50' in df_1d.columns and current_price > df_1d['EMA_50'].iloc[-1] else ('Neutral (Bouncing Bear)' if df_1d['close'].iloc[-1] > df_1d['open'].iloc[-1] else 'Bearish'))}
- 15m RSI: {df_15m['RSI_14'].iloc[-1]:.1f}
- 5m RSI: {df_5m['RSI_14'].iloc[-1]:.1f}
- ATR (5m Volatility): ${df_5m['ATRr_14'].iloc[-1]:.2f}
- OPTIONS: {gex_info}
- KEY LIQUIDITY ZONES (90-Day Lookback):
    -> Macro High Resistance: ${macro_high:.2f}
    -> Macro Low Support: ${macro_low:.2f}
    -> {cluster_alert}

[PRE-CALCULATED SCREENER MATH (USE THESE SCORES EXACTLY)]
- Timeframe Scores: {tf_scores_str}
- SMC Structure: {smc_structure}
- RSI Divergence: {rsi_div}
- SMC Regime: {screener_report.get('SMC_Regime', 'N/A')}
- Confidence_Level: {screener_report.get('Confidence_Level', 'N/A')}
- Suggested Entry: {screener_report.get('Entry', 'N/A')}
- Suggested Stop Loss: {screener_report.get('Stop Loss', 'N/A')}
- Suggested Target 1: {screener_report.get('Target 1 (1R)', 'N/A')}
- Suggested Target 2: {screener_report.get('Target 2 (2R)', 'N/A')}
"""
                results.append(dossier)
            except Exception as e:
                results.append(f"Error for {ticker}: {str(e)}")
                
        return "\n\n".join(results)

def create_stock_agent(llm):
    return Agent(
        role='Quant Trading Engineer',
        goal='Analyze the pre-calculated Technical Dossiers. Assign a 0-100 Build-Up Score to EVERY ticker based on its structural confluence. Output explicit Long/Short setups with Entry/Stop/Target levels if the Confidence Level is > 80%.',
        backstory="""You are an elite quantitative algorithm.
1. You review the highly compressed Technical Dossiers (which contain pre-calculated EMAs, RSI, GEX Walls, and Fib Clusters).
2. You respect the HTF Bias (Never long into a bearish 1D trend).
3. If a setup aligns with the Macro Pulse Score and has strong Confluence Clusters, output a detailed setup with Exact Limits (SL must be 1.5x ATR).""",
        verbose=True,
        allow_delegation=False,
        tools=[AdvancedSMCAlpacaTool()],
        llm=llm
    )
