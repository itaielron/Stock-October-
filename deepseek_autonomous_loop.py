import os
import time
import json
import re
from datetime import datetime
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool

load_dotenv()
deepseek_key = os.getenv("DEEPSEEK_API_KEY")
llm = LLM(model="deepseek/deepseek-chat", api_key=deepseek_key, base_url="https://api.deepseek.com")

def write_log(msg):
    with open("agent_activity.log", "a") as f:
        f.write(f"\n[{datetime.now().strftime('%H:%M:%S')}] {msg}")

@tool("Alpaca Executor Tool")
def run_alpaca_scan(dummy: str) -> str:
    """Executes the Python script that pulls live Alpaca data and generates charts."""
    write_log("[ACT] DeepSeek executing real_alpaca_backtester.py...")
    os.system("source venv/bin/activate && python real_alpaca_backtester.py")
    return "Alpaca scan complete. Charts saved in /charts directory."

@tool("Observation Tool")
def observe_results(dummy: str) -> str:
    """Observes the generated charts and outcomes."""
    if not os.path.exists("charts"): return "0 winners, 0 losers."
    charts = os.listdir("charts")
    winners = [c for c in charts if "winner" in c]
    losers = [c for c in charts if "loser" in c]
    res = f"Observed {len(winners)} winners and {len(losers)} losers."
    write_log(f"[OBSERVE] {res}")
    return res

@tool("Code Optimization Tool")
def optimize_code(new_ema_dist: str) -> str:
    """Modifies real_alpaca_backtester.py to tighten the EMA distance filter. Pass a float value like '1.2'."""
    try:
        with open("real_alpaca_backtester.py", "r") as f:
            content = f.read()
        
        # Replace the EMA distance logic dynamically
        new_content = re.sub(r"<= \d+\.\d+ \* atr:", f"<= {new_ema_dist} * atr:", content)
        
        with open("real_alpaca_backtester.py", "w") as f:
            f.write(new_content)
        
        # Clear old charts for the fresh backtest
        os.system("rm -rf charts/*")
        
        msg = f"Successfully tightened EMA parameter to {new_ema_dist} ATR."
        write_log(f"[CORRECT] {msg}")
        return msg
    except Exception as e:
        return str(e)

planner = Agent(
    role="Master Planner",
    goal="Plan the market scan cycle.",
    backstory="You direct the autonomous cycle.",
    verbose=True,
    allow_delegation=False,
    llm=llm
)

actor = Agent(
    role="Screener Executor",
    goal="Execute the Alpaca scans.",
    backstory="You run the raw Python API tools.",
    verbose=True,
    allow_delegation=False,
    tools=[run_alpaca_scan],
    llm=llm
)

observer = Agent(
    role="QA Observer",
    goal="Count the winners and losers from the charts.",
    backstory="You analyze the visual outputs.",
    verbose=True,
    allow_delegation=False,
    tools=[observe_results],
    llm=llm
)

evaluator = Agent(
    role="Evaluator & Corrector",
    goal="Tweak the entry parameter if win rate is under 80%.",
    backstory="You use 'Code Optimization Tool' to rewrite the algorithm dynamically. If win rate is bad, tighten the EMA distance to 1.2 or 0.8 to only catch perfect setups.",
    verbose=True,
    allow_delegation=False,
    tools=[optimize_code],
    llm=llm
)

def build_tasks():
    t1 = Task(description="Plan the next scan.", expected_output="Scan Plan", agent=planner)
    t2 = Task(description="Use 'Alpaca Executor Tool' to run the scan.", expected_output="Scan Execution Status", agent=actor)
    t3 = Task(description="Use 'Observation Tool' to get the Win/Loss ratio.", expected_output="Win/Loss Ratio", agent=observer)
    t4 = Task(description="If the Win Rate is under 80%, you MUST use 'Code Optimization Tool' to lower the EMA distance multiplier (e.g., 1.2, 0.8).", expected_output="Correction Decision", agent=evaluator)
    return [t1, t2, t3, t4]

if __name__ == "__main__":
    write_log("🚀 Initiating Self-Correcting Genetic Loop (Code Editing Enabled)")
    
    for cycle in range(1, 10):
        write_log(f"\n--- STARTING OPTIMIZATION CYCLE {cycle} ---")
        crew = Crew(agents=[planner, actor, observer, evaluator], tasks=build_tasks(), process=Process.sequential, verbose=True, output_log_file=True)
        crew.kickoff()
        write_log(f"--- CYCLE {cycle} COMPLETE. Re-scanning in 20 seconds ---")
        time.sleep(20)
