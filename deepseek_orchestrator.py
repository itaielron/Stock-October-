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

def read_log(agent_name):
    path = f"agent_logs/{agent_name}.log"
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read()
    return "No past memory. This is your first task."

def ask_deepseek(role, backstory, task, agent_name):
    master_log = open("master_project_log.md").read()
    agent_history = read_log(agent_name)
    
    system_prompt = f"""You are {role}.
Your Backstory: {backstory}

--- MASTER PROJECT MANDATE ---
{master_log}

--- YOUR PAST MEMORY LOG (DO NOT REPEAT MISTAKES) ---
{agent_history}

You must output your thought process, and if writing code, wrap it ONLY in a single ```python block. Do not add markdown around it, just the raw code.
"""
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task}
        ],
        temperature=0.1
    )
    answer = response.choices[0].message.content
    append_log(agent_name, f"TASK:\n{task}\nRESPONSE:\n{answer}")
    return answer

if __name__ == "__main__":
    for i in range(1, 4):
        print(f"\n=== CYCLE {i} ===")
        print("[1] Waking up DeepSeek Backend Coder...")
        
        current_code = open("real_alpaca_backtester.py").read()
        qa_feedback = read_log("qa_analyst")
        
        coder_task = f"""
The QA Analyst just reviewed your last backtest. Here is their memory bank:
{qa_feedback[-2000:]}

You MUST fix the zero-trade issue. Loosen the confluence constraints if necessary, or fix any bugs in your logic. 
Make sure you still use `mpf.make_addplot` for the '^' and 'v' scatter markers for entries and exits!
Do NOT just return a snippet. Return the full, updated Python file in a single ```python block.

Here is the current code to fix:
```python
{current_code}
```
"""
        coder_response = ask_deepseek(
            role="DeepSeek Backend Engineer",
            backstory="You write quantitative trading Python scripts. You are flawless with mplfinance and pandas.",
            task=coder_task,
            agent_name="backend_coder"
        )
        
        match = re.search(r"```python\n(.*?)```", coder_response, re.DOTALL)
        if match:
            new_code = match.group(1)
            with open("real_alpaca_backtester.py", "w") as f:
                f.write(new_code)
            print("[2] Coder successfully rewrote real_alpaca_backtester.py")
        else:
            print("[2] Failed to extract code from Coder.")

        print("[3] Running the backtest...")
        os.system("source venv/bin/activate && python real_alpaca_backtester.py > backtest_temp.log 2>&1")
        
        backtest_out = open("backtest_temp.log").read()
        
        print("[4] Waking up QA Analyst...")
        qa_task = f"""
The Backend Coder just ran the backtest again. 
Here is the console output:
{backtest_out}

Evaluate the output. If trades=0, explain why. If there are trades, check the win rate and if charts were actually generated.
Log your findings so the Coder can fix it next round.
"""
        qa_response = ask_deepseek(
            role="DeepSeek QA Analyst",
            backstory="You verify backtest integrity and log structural mistakes.",
            task=qa_task,
            agent_name="qa_analyst"
        )
        print("[5] QA Analyst logged findings.")
        time.sleep(5)

        print("[6] Synchronizing Memory Banks and Scripts to GitHub...")
        os.system("git add . && git commit -m 'Auto-Sync: Agent optimization cycle complete' && git push origin main")
        print("[7] Cycle complete. Sleeping...")
        time.sleep(5)
