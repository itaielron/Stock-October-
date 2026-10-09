import os
import re
import time
from dotenv import load_dotenv
from openai import OpenAI
from orchestrator_helpers import get_function_source, replace_function_source

load_dotenv()
client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")

def log_activity(msg):
    print(msg)
    with open("agent_activity.log", "a") as f:
        f.write(f"\n[{time.strftime('%H:%M:%S')}] {msg}")

def read_recent_log(agent_name, chars=2000):
    path = f"agent_logs/{agent_name}.log"
    if os.path.exists(path):
        with open(path, "r") as f:
            content = f.read()
            return content[-chars:] if len(content) > chars else content
    return "No past memory."

def ask_deepseek(role, system_msg, task, agent_name):
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": task}
        ],
        temperature=0.1
    )
    answer = response.choices[0].message.content
    with open(f"agent_logs/{agent_name}.log", "a") as f:
        f.write(f"\n--- {time.ctime()} ---\nTASK:\n{task[:500]}...\nRESPONSE:\n{answer}\n")
    return answer

if __name__ == "__main__":
    master_log = open("master_project_log.md").read()
    cycle = 1
    tf_list = ["1Min", "5Min", "15Min", "1Hour", "4Hour"]
    
    while True:
        log_activity(f"\n=== CYCLE {cycle} ===")
        current_tf = tf_list[(cycle - 1) % len(tf_list)]
        cycle += 1
        
        target_func = get_function_source("real_alpaca_backtester.py", "_confluence_cluster")
        qa_feedback = read_recent_log("qa_analyst")
        
        system_prompt = f"""You are DeepSeek Backend Engineer.
--- MASTER MANDATE ---
{master_log}

You MUST output ONLY a single ```python block containing the rewritten `def _confluence_cluster(df: pd.DataFrame, i: int, atr: float) -> dict | None:` function.
"""
        task = f"QA Feedback:\n{qa_feedback}\n\nCurrent Function:\n```python\n{target_func}\n```\nRewrite it to improve win rate for timeframe {current_tf}."
        
        log_activity(f"[1] Coder evaluating feedback for {current_tf}...")
        coder_response = ask_deepseek("DeepSeek Backend Engineer", system_prompt, task, "backend_coder")
        
        match = re.search(r"```python\n(def _confluence_cluster.*?)\n```", coder_response, re.DOTALL)
        if match:
            new_func = match.group(1)
            success = replace_function_source("real_alpaca_backtester.py", "_confluence_cluster", new_func)
            if success:
                log_activity("[2] Coder actively injected new confluence logic.")
                # FOOLPROOF: Ensure __main__ exists!
                with open("real_alpaca_backtester.py", "r") as rfile:
                    if 'if __name__ == "__main__":' not in rfile.read():
                        with open("real_alpaca_backtester.py", "a") as afile:
                            afile.write('\n\nif __name__ == "__main__":\n    _start = sys.argv[1] if len(sys.argv) > 1 else None\n    _end = sys.argv[2] if len(sys.argv) > 2 else None\n    run_backtest(start=_start, end=_end)\n')
            else:
                log_activity("[2] AST replacement failed. Retry triggered.")
        else:
            log_activity("[2] Regex failed to find python block. Retry triggered.")

        log_activity(f"[3] Executing Backtest on {current_tf} data...")
        os.system(f"export BACKTEST_TF={current_tf} && source venv/bin/activate && python real_alpaca_backtester.py > backtest_temp.log 2>&1")
        backtest_out = open("backtest_temp.log").read()
        
        if "win_rate=" in backtest_out:
            try:
                wr = float(re.search(r"win_rate=([0-9\.]+)", backtest_out).group(1))
                trades = int(re.search(r"trades=([0-9]+)", backtest_out).group(1))
                if trades >= 5 and wr >= 80.0:
                    log_activity(f"[SUCCESS] Target achieved on {current_tf}! Trades: {trades}, WR: {wr}%. Logging to proven_strategies.md...")
                    with open("agent_logs/proven_strategies.md", "a") as f:
                        f.write(f"\n\n### Successful Regime: {current_tf} (WR: {wr}%, Trades: {trades})\n```python\n{new_func}\n```\n")
                    log_activity(f"[ROTATING] Moving to next timeframe...")
                    continue
            except Exception as e:
                pass

        log_activity("[4] QA Analyst grading backtest...")
        qa_sys = f"You are DeepSeek QA Analyst.\n--- MASTER MANDATE ---\n{master_log}\nKeep feedback under 500 words."
        qa_task = f"Backtest Output:\n{backtest_out}\nEvaluate. If trades=0, explain why."
        ask_deepseek("DeepSeek QA Analyst", qa_sys, qa_task, "qa_analyst")
        
        log_activity("[5] Auto-Syncing Agent Memory & Code to GitHub main branch...")
        os.system("git add . && git commit -m 'Auto-Sync: Agent optimization cycle' && git push origin main")
        
        log_activity("[6] Cycle Complete. Preparing next genetic mutation...")
        time.sleep(5)
