import os
import time
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

@tool("Read File Tool")
def read_file(filepath: str) -> str:
    """Reads the content of a Python file."""
    with open(filepath, "r") as f:
        return f.read()

@tool("Write File Tool")
def write_file(data: str) -> str:
    """Overwrites real_alpaca_backtester.py with new Python code. Pass the raw python code as the argument."""
    # Strip markdown code blocks if the LLM includes them
    clean_data = re.sub(r"^```python\n|```$", "", data.strip(), flags=re.MULTILINE)
    with open("real_alpaca_backtester.py", "w") as f:
        f.write(clean_data)
    return "Successfully wrote to real_alpaca_backtester.py"

@tool("Alpaca Backtest Executor")
def run_backtest(dummy: str) -> str:
    """Executes real_alpaca_backtester.py and returns the stdout results."""
    os.system("source venv/bin/activate && python real_alpaca_backtester.py > backtest_temp.log 2>&1")
    with open("backtest_temp.log", "r") as f:
        return f.read()

backend_coder = Agent(
    role="DeepSeek Backend Engineer",
    goal="Write and optimize the Python logic for the SignalGate and Alpaca backtester.",
    backstory="You are an expert quantitative developer. You write raw Python code to calculate structurally sound entry/exit gates.",
    tools=[read_file, write_file],
    llm=llm,
    verbose=True
)

qa_analyst = Agent(
    role="DeepSeek QA Analyst",
    goal="Verify that the green (Take Profit) and red (Stop Loss) lines make structural market sense.",
    backstory="You analyze the backtest logic to ensure the SL/TP logic respects real price action (swing highs/lows) and isn't just blind ATR math.",
    tools=[run_backtest, read_file],
    llm=llm,
    verbose=True
)

t1 = Task(
    description="Read real_alpaca_backtester.py. Identify if the Stop Loss (red lines) and Take Profit (green lines) logic is blindly based on ATR without respecting actual price structure.",
    expected_output="Analysis of structural flaws in the current TP/SL logic.",
    agent=qa_analyst
)

t2 = Task(
    description="Using the QA Analyst's findings, rewrite real_alpaca_backtester.py using the Write File Tool. Ensure the Python logic accurately calculates structurally sound entry/exit lines (e.g. tracking local swing lows for Stops instead of just blind multipliers).",
    expected_output="Confirmation that the Python file was successfully rewritten.",
    agent=backend_coder
)

t3 = Task(
    description="Run the 'Alpaca Backtest Executor' tool to generate the new charts and observe the output. Verify the win rate improved.",
    expected_output="Final pass/fail grade of the new logic.",
    agent=qa_analyst
)

if __name__ == "__main__":
    write_log("🚀 DeepSeek Hierarchical Manager assumes control of the codebase...")
    crew = Crew(
        agents=[backend_coder, qa_analyst],
        tasks=[t1, t2, t3],
        process=Process.hierarchical,
        manager_llm=llm,
        verbose=True,
        output_log_file=True
    )
    
    while True:
        try:
            crew.kickoff()
            write_log("[DEEPSEEK MANAGER] Cycle Complete. Waiting 5m for next market scan.")
            time.sleep(300)
        except Exception as e:
            write_log(f"[DEEPSEEK MANAGER] Error: {e}")
            time.sleep(60)
