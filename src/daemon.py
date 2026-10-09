import os
import time
import sqlite3
from datetime import datetime, timedelta
import pytz
import random
from crewai import Agent, Task, Crew, Process
from src.database import get_agent_config, log_alert
from src.agents.flight_agent import create_flight_agent
from src.agents.stock_agent import create_stock_agent
from src.alert_manager import send_imessage, send_discord_message

def run_ss_tracker():
    stock_config = get_agent_config("StockAgent")
    manager_config = get_agent_config("ChiefIntelligenceOfficer")
    
    from src.database import get_watchlist, get_agent_feedback
    watchlist_targets = get_watchlist()
    if not watchlist_targets:
        watchlist_targets = ["SPY", "QQQ", "AAPL"]

    # Initialize Manager
    manager_agent = Agent(role=manager_config[1], goal=manager_config[2], backstory=manager_config[3], verbose=True, allow_delegation=False, llm=manager_config[0])

    print(f"Running Native Stock Scraper for {len(watchlist_targets)} tickers...")
    
    # Fetch recent feedback from the Systems Architect
    manager_feedback = get_agent_feedback("ChiefIntelligenceOfficer", limit=3)
    feedback_str = "\n".join(manager_feedback) if manager_feedback else "No recent feedback."
    
    # OPTIMIZATION: Bypass the middleman LLM agent. Call the Python Alpaca tool natively!
    from src.agents.stock_agent import AdvancedSMCAlpacaTool
    raw_smc_data = AdvancedSMCAlpacaTool()._run(str(watchlist_targets))

    stock_format_task = Task(
        description=f'''
        Read the following raw data from the Stock Scraper. VERIFY it. 
        
        <SYSTEMS_ARCHITECT_FEEDBACK>
        Pay close attention to this past feedback to avoid repeating mistakes:
        {feedback_str}
        </SYSTEMS_ARCHITECT_FEEDBACK>
        
        RAW DATA:
        {raw_smc_data}
        
        You MUST format your output EXACTLY like the following example. ONLY list trades that meet strict criteria (Confidence Level > 80%). Do NOT list or mention the tickers that failed. Do NOT add any conversational fluff (no "Here are the results"). Start exactly with "FINAL VERIFIED RESULTS". CRITICAL RULE: DO NOT CONTRADICT YOUR MATH. If you suggest a Target 1 that is HIGHER than the Entry, you MUST label the title as a "LONG SETUP". If your Target 1 is LOWER than the Entry, you MUST label the title as a "SHORT SETUP". NEVER output a "SHORT SETUP" if your targets are above your entry price. NEVER set your Stop Loss to the exact same price as your Entry. SECOND CRITICAL RULE: You are a strict compiler. Do NOT hallucinate the Confidence Level. You MUST extract it EXACTLY from the `[PRE-CALCULATED SCREENER MATH (USE THESE SCORES EXACTLY)]` section of each ticker's dossier.
        
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
        | Suggested Target 1 (1R) | VALUE |
        | Suggested Target 2 (2R) | VALUE |
        
        ---THOUGHT PROCESS---
        [Detailed step-by-step journal of the scores for all timeframes (5m, 15m, 1H, 1D) for every ticker, and why you made the final decision.]
        ''',
        agent=manager_agent,
        expected_output="A perfectly formatted report containing FINAL VERIFIED RESULTS (only containing valid trades formatted exactly as the tabbed text) and THOUGHT PROCESS."
    )

    print("Running Manager Verification Phase...")
    stock_crew = Crew(agents=[manager_agent], tasks=[stock_format_task], process=Process.sequential)
    stock_result = str(stock_crew.kickoff())
    
    # --- INJECT AUTOMATED OPTIONS STRATEGY ENGINE ---
    import re
    from src.tools.options_recommender import recommend_options
    
    try:
        # Look for the strict SMC signal format: 🟢 TICKER LONG | Entry: 100 | SL: 95 | TP1: 105 | TP2: 110
        signal_pattern = r'([🟢🔴])\s+([A-Z]+)\s+(LONG|SHORT)\s+\|\s+Entry:\s+\$?([\d\.]+)\s+\|\s+SL:\s+\$?([\d\.]+)\s+\|\s+TP1:\s+\$?([\d\.]+)\s+\|\s+TP2:\s+\$?([\d\.]+)'
        matches = re.finditer(signal_pattern, stock_result)
        
        options_additions = ""
        for match in matches:
            emoji, ticker, direction, entry, sl, tp1, tp2 = match.groups()
            options_recommendation = recommend_options(ticker, direction, float(entry), float(tp1), float(tp2), float(sl))
            options_additions += f"\n\n{options_recommendation}\n"
            
        if options_additions:
            # Insert before the THOUGHT PROCESS divider
            if "---THOUGHT PROCESS---" in stock_result:
                parts = stock_result.split("---THOUGHT PROCESS---")
                stock_result = parts[0] + options_additions + "\n---THOUGHT PROCESS---\n" + parts[1]
            else:
                stock_result += options_additions
    except Exception as e:
        print(f"Options Engine Injection Error: {e}")
    # ------------------------------------------------

    log_alert("STOCK_SWEEP", stock_result)

    
    # CREDIT OPTIMIZATION: Only run the Optimization Reviewer if there's an anomaly or a 10% random upkeep chance
    import random
    if "ERROR" in stock_result.upper() or "NO FLIGHT DATA" in stock_result.upper() or "UNABLE TO VERIFY" in stock_result.upper() or random.random() < 0.1:
        run_optimization_review("STOCK_SWEEP", stock_result)
        
    # Forward strictly formatted alerts to Discord
    if "FINAL VERIFIED RESULTS" in stock_result and ("🟢" in stock_result or "🔴" in stock_result):
        discord_content = stock_result.split("---THOUGHT PROCESS---")[0].strip()
        
        # Extract everything from FINAL VERIFIED RESULTS onwards to drop fluff
        if "FINAL VERIFIED RESULTS" in discord_content:
            discord_content = "FINAL VERIFIED RESULTS\n" + discord_content.split("FINAL VERIFIED RESULTS")[1].strip()
            
        send_discord_message(f"🚨 **Stock Intelligence Alert** 🚨\n\n{discord_content}")
    else:
        send_discord_message("🚨 **Stock Intelligence Alert** 🚨\n\nNo setups passed the strict verification criteria today. None qualify.")


def run_flight_sweep():
    flight_config = get_agent_config("FlightAgent")
    manager_config = get_agent_config("ChiefIntelligenceOfficer")
    
    # Initialize Manager
    manager_agent = Agent(role=manager_config[1], goal=manager_config[2], backstory=manager_config[3], verbose=True, allow_delegation=False, llm=manager_config[0])

    target_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")

    print("Running Native Flight Scraper...")
    from src.agents.flight_agent import GoogleFlightsTool
    # Scrape 4 target destinations natively
    raw_flight_data = []
    tool = GoogleFlightsTool()
    for dest in ['AMS', 'BER', 'FCO', 'BCN']:
        raw_flight_data.append(tool._run("TLV", dest, target_date))
    
    raw_flight_str = "\n".join(raw_flight_data)
    
    from src.database import get_agent_feedback
    manager_feedback = get_agent_feedback("ChiefIntelligenceOfficer", limit=3)
    feedback_str = "\n".join(manager_feedback) if manager_feedback else "No recent feedback."

    flight_format_task = Task(
        description=f'''
        Read the following raw flight data found by the Flight Scraper. 
        
        <SYSTEMS_ARCHITECT_FEEDBACK>
        Pay close attention to this past feedback to avoid repeating mistakes:
        {feedback_str}
        </SYSTEMS_ARCHITECT_FEEDBACK>
        
        RAW DATA:
        {raw_flight_str}
        
        1. Ensure prices are listed in USD (e.g., $150 USD).
        2. DO NOT hallucinate historical prices or averages. If the tool does not provide price history, you MUST state "Historical Average: N/A".
        3. You MUST display the exact Outbound Date and Return Date.
        4. Include a clickable Google Flights URL for every flight: [Book on Google Flights](https://www.google.com/travel/flights?q=Flights%20to%20DESTINATION%20from%20TLV%20on%20{target_date})
        
        You MUST format your output EXACTLY like this:
        
        # FINAL VERIFIED RESULTS
        [Clear list of flights, with Dates, USD prices, baggage fees (if available), and Booking Links.]
        
        ---THOUGHT PROCESS---
        [Detailed journal explaining how you verified the prices.]
        ''',
        agent=manager_agent,
        expected_output="A perfectly formatted report containing FINAL VERIFIED RESULTS and THOUGHT PROCESS."
    )

    print("Running Manager Verification Phase...")
    flight_crew = Crew(agents=[manager_agent], tasks=[flight_format_task], process=Process.sequential)
    flight_result = str(flight_crew.kickoff())
    log_alert("FLIGHT_SWEEP", flight_result)
    
    if "ERROR" in flight_result.upper() or "NO FLIGHT DATA" in flight_result.upper() or "UNABLE TO VERIFY" in flight_result.upper() or random.random() < 0.1:
        run_optimization_review("FLIGHT_SWEEP", flight_result)
        
    if "Book on Google" in flight_result:
        # send_imessage("YOUR_PHONE_NUMBER_HERE", f"🤖 Flight Alert: Cheap flights found!")
        pass


def run_optimization_review(project, final_report):
    from src.database import get_agent_config, log_optimization
    from src.tools.opt_tools import LogConstructiveFeedbackTool
    
    opt_config = get_agent_config("OptimizationAgent")
    opt_agent = Agent(
        role=opt_config[1], 
        goal=opt_config[2], 
        backstory=opt_config[3], 
        verbose=True, 
        allow_delegation=False, 
        tools=[LogConstructiveFeedbackTool()],
        llm=opt_config[0]
    )
    
    task = Task(
        description=f'''
        Review the following final report generated by the {project} intelligence sweep:
        
        {final_report}
        
        Analyze the output for inefficiencies, analytical flaws, or bad math. Do NOT complain about formatting blocks that are required by the system (such as the THOUGHT PROCESS block). Focus on analytical quality and logic.
        1. Identify the agent responsible (e.g., 'ChiefIntelligenceOfficer', 'StockAgent', 'FlightAgent').
        2. If you find a flaw, you MUST use the 'Log Constructive Feedback' tool to write a critique into the agent's memory database. 
           (Input format: AgentName|FeedbackText)
        3. Provide a concise summary of the feedback you logged.
        ''',
        agent=opt_agent,
        expected_output="A concise summary of the autonomous prompt updates you executed, or Python code optimizations the developer should make."
    )
    crew = Crew(agents=[opt_agent], tasks=[task], process=Process.sequential)
    suggestion = str(crew.kickoff())
    log_optimization(project, suggestion)

def is_market_open():
    ny_time = datetime.now(pytz.timezone('America/New_York'))
    if ny_time.weekday() > 4:
        return False
    market_open = ny_time.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = ny_time.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= ny_time <= market_close

def start_daemon():
    print("Starting Autonomous Background Daemon...")
    print("Executing mandatory startup sweeps...")
    try:
        if is_market_open():
            run_ss_tracker()
        else:
            print("Skipping startup stock sweep (Market is closed)")
        run_flight_sweep()
    except Exception as e:
        print(f"Startup sweep encountered an error: {e}")
        
    last_flight_run = datetime.now()
    
    print("Entering scheduled daemon loop...")
    while True:
        try:
            now = datetime.now()
            
            # 1. Flight Sweep (Every 12 hours)
            if (now - last_flight_run).total_seconds() >= 43200:
                print("12-Hour interval reached. Running Flight Sweep...")
                run_flight_sweep()
                last_flight_run = now
                
            # 2. Stock Sweep (Every 15 minutes during market hours)
            if is_market_open():
                print("Market is OPEN. Running 5-minute SS Tracker Sweep...")
                run_ss_tracker()
                time.sleep(300)
            else:
                time.sleep(300)
                
        except Exception as e:
            print(f"Daemon encountered an error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    start_daemon()
