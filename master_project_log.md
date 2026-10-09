# MASTER PROJECT LOG

## Core Mandate
1. Backtest and optimize charts to find clear confluence clusters (EMAs, GEX, Support/Resistance, ATR).
2. Optimize for >80% win rate or high consistency.
3. ZERO repeated mistakes.
4. Visual clarity: Charts MUST show exact entry arrow and exact TP1/SL exit markers.

## New Mandate: Multi-Timeframe Optimization & Quant Research Integration
5. **Multi-Timeframe Analysis (MTFA):** The backtest engine must pull and evaluate the past week's candles across the following timeframes: 1m, 3m, 5m, 15m, 1h, and 4h. The entry logic must adapt to or evaluate confluence across these time horizons.
6. **Continuous Genetic Learning:** The QA and Evaluator agents must explicitly analyze WHY losers lost and WHY winners won. Do not just look at win rate; deduce the structural reason for failure and rewrite the gating conditions to filter out those specific setups.
7. **Live Data Prep:** This entire historical optimization process is strictly to build a hardened, consistent execution model that will be deployed on live ticker data next week.
### Quant Research Report
**Purpose**: Algorithmic rules and execution constraints for Python backtesting scripts.

#### 1. Technical Analysis Confluences (Indicator Overlaps)
To build a high-probability setup, the algorithm must implement a hierarchical confluence structure to guarantee indicator independence. 
*   **Regime Filter (GEX - Gamma Exposure)**: 
    *   *Logic*: If GEX < 0 (Negative Gamma), dealers sell dips and buy rallies -> execute **Trend-Following** sub-routines. If GEX > 0 (Positive Gamma), dealers buy dips and sell rallies -> execute **Mean-Reversion** sub-routines.
*   **Directional Bias (EMA)**: 
    *   *Logic*: Long entries valid ONLY IF `Close > EMA_50` and `EMA_50 > EMA_200`. Short entries valid ONLY IF `Close < EMA_50`.
*   **Volatility and Risk Sizing (ATR)**: 
    *   *Logic*: `StopLoss = Entry_Price +/- (ATR_14 * 1.5)`. `Position_Size = Max_Risk_Dollar_Amount / (ATR_14 * 1.5)`. 
*   **Execution Rule**: Trade signal is generated `True` ONLY IF [GEX Regime matches Strategy] AND [EMA Trend aligns with Trade Direction] AND [ATR is within limits].

#### 2. Macro Trading and Fundamental Analysis
Modern systems do not rely solely on technicals; they filter technical setups using a "macro regime score."
*   **Macro Regime Scoring**: 
    *   *Logic*: Assign numerical weights to fundamental data streams. If `Macro_Score >= Bullish_Threshold`, immediately disable all Short technical triggers.
*   **Event-Driven Pauses**: 
    *   *Logic*: Algorithm must parse economic calendars. Set `Trading_Enabled = False` 30 minutes before and after high-impact events (e.g., FOMC, NFP).

#### 3. Internal Logic of Top Algorithmic Screener Bots
*   **Screener Query Engine**: 
    *   *Logic*: Run lightweight vector operations (e.g., `Volume > 1M AND Price > SMA_200`) across the entire universe FIRST, then pass the filtered subset to the complex Signal Generation layer.
*   **Strict Risk Management Layer**: 
    *   *Logic*: Even if a valid technical/macro signal is fired, execution layer must verify: `Current_Drawdown < Max_Allowed` and `Daily_Exposure < Account_Limit`. If false, drop the signal.

8. **GitHub Live Sync:** All code changes, agent memory logs, and chart outputs MUST be pushed to GitHub at the end of every single execution cycle. No exceptions. This allows the human supervisor to monitor progress in real-time.

## Credit Optimization & Runaway Prevention
9. **Smart Sleep Protocol (Credit Conservation):** DeepSeek agents are strictly forbidden from rewriting code or running deep heuristic evaluations if the current backtest script achieves the target >80% win rate with structurally sound charts. If a cycle receives a `PASS` grade from the QA Analyst, the optimization engine MUST halt and enter standby mode. Do not waste API tokens over-optimizing a working system. The orchestrator is hard-limited to prevent infinite runaway loops.

## Anti-Overfitting & Diverse Regime Learning
10. **Success Memory & Rotation:** Do not overfit to a single timeframe or chart. Once a confluence cluster achieves >80% on a specific timeframe (e.g., 5Min), append the winning parameters to `agent_logs/proven_strategies.md`. The orchestrator will then rotate the backtester to a DIFFERENT timeframe (e.g., 15Min, 1Hour) or a different market condition. The Coder must read the `proven_strategies.md` log to deduce universal regime rules based on these verified successes.
