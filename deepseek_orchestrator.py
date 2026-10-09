import os
import re
import time
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")

def append_log(agent_name, content):
    with open(f"agent_logs/{agent_name}.log", "a") as f:
        f.write(f"\n--- {time.ctime()} ---\n{content}\n")

def read_recent_log(agent_name, chars=2000):
    path = f"agent_logs/{agent_name}.log"
    if os.path.exists(path):
        with open(path, "r") as f:
            content = f.read()
            return content[-chars:] if len(content) > chars else content
    return "No past memory."


def log_activity(msg):
    print(msg)
    with open("agent_activity.log", "a") as f:
        f.write(f"\n[{time.strftime('%H:%M:%S')}] {msg}")

def extract_confluence_function(code):
    # Extracts the _confluence_cluster function from the file
    match = re.search(r"(def _confluence_cluster.*?)(?=^def |\Z)", code, re.MULTILINE | re.DOTALL)
    return match.group(1) if match else ""

def ask_deepseek(role, system_msg, task, agent_name):
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task}
        ],
        temperature=0.1
    )
    answer = response.choices[0].message.content
    # Truncate append to prevent massive bloat
    append_log(agent_name, f"TASK:\n{task[:500]}...\nRESPONSE:\n{answer}")
    return answer

if __name__ == "__main__":
    master_log = open("master_project_log.md").read()
    cycle = 1
    
    while True:
        log_activity(f"\n=== CYCLE {cycle} ===")
        cycle += 1
        
        current_code = open("real_alpaca_backtester.py").read()
        target_func = extract_confluence_function(current_code)
        qa_feedback = read_recent_log("qa_analyst")
        
        system_prompt = f"""You are DeepSeek Backend Engineer.
--- MASTER MANDATE ---
{master_log}

You MUST output ONLY a single ```python block containing the rewritten `def _confluence_cluster(df: pd.DataFrame, i: int, atr: float) -> dict | None:` function. Do NOT output the entire file.
"""
        task = f"""
Here is the QA Analyst's recent feedback:
{qa_feedback}

Here is the current confluence function:
```python
{target_func}
```
Rewrite it to improve the win rate and generate trades, respecting the feedback.
"""
        log_activity("[1] Coder evaluating Master Logs & QA feedback...")
        coder_response = ask_deepseek("DeepSeek Backend Engineer", system_prompt, task, "backend_coder")
        
        match = re.search(r"```python\n(def _confluence_cluster.*?)\n```", coder_response, re.DOTALL)
        if match:
            new_func = match.group(1)
            new_code = current_code.replace(target_func, new_func)
            with open("real_alpaca_backtester.py", "w") as f:
                f.write(new_code)
            log_activity("[2] Coder actively rewriting real_alpaca_backtester.py...")
        else:
            log_activity("[2] Regex failed. Coder retry triggered.")

        log_activity("[3] Executing Walk-Forward Backtest on 5m, 15m, 1H, 4H data...")
        os.system("source venv/bin/activate && python real_alpaca_backtester.py > backtest_temp.log 2>&1")
        backtest_out = open("backtest_temp.log").read()
        
        # Check Smart Sleep Protocol
        if "win_rate=" in backtest_out:
            try:
                wr_str = re.search(r"win_rate=([0-9\.]+)", backtest_out).group(1)
                wr = float(wr_str)
                trades_str = re.search(r"trades=([0-9]+)", backtest_out).group(1)
                trades = int(trades_str)
                if trades >= 5 and wr >= 80.0:
                    log_activity(f"[SMART SLEEP] Target achieved! Trades: {trades}, WR: {wr}%. Sleeping for 1 hour.")
                    time.sleep(3600)
                    continue
            except:
                pass

        log_activity("[4] QA Analyst grading backtest output and writing constraints...")
        qa_sys = f"You are DeepSeek QA Analyst.\n--- MASTER MANDATE ---\n{master_log}\nKeep feedback under 500 words."
        qa_task = f"Backtest Output:\n{backtest_out}\nEvaluate the run. If trades=0, explain why. Log findings."
        ask_deepseek("DeepSeek QA Analyst", qa_sys, qa_task, "qa_analyst")
        
        log_activity("[5] Auto-Syncing Agent Memory & Code to GitHub main branch...")
        os.system("git add . && git commit -m 'Auto-Sync: Agent optimization cycle' && git push origin main")
        
        log_activity("[6] Cycle Complete. Preparing next genetic mutation...")
        time.sleep(5)
