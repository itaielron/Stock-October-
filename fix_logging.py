import re

with open("deepseek_orchestrator.py", "r") as f:
    code = f.read()

# Replace print() calls with a custom log_activity function that writes to agent_activity.log
inject = """
def log_activity(msg):
    print(msg)
    with open("agent_activity.log", "a") as f:
        f.write(f"\\n[{time.strftime('%H:%M:%S')}] {msg}")

"""

code = code.replace('def extract_confluence_function(code):', inject + 'def extract_confluence_function(code):')

code = code.replace('print(f"\\n=== CYCLE {cycle} ===")', 'log_activity(f"\\n=== CYCLE {cycle} ===")')
code = code.replace('print("[1] Asking Coder for optimized function...")', 'log_activity("[1] Coder evaluating Master Logs & QA feedback...")')
code = code.replace('print("[2] Successfully injected new confluence logic.")', 'log_activity("[2] Coder actively rewriting real_alpaca_backtester.py...")')
code = code.replace('print("[2] Regex failed. No changes made.")', 'log_activity("[2] Regex failed. Coder retry triggered.")')
code = code.replace('print("[3] Running Backtest...")', 'log_activity("[3] Executing Walk-Forward Backtest on 5m, 15m, 1H, 4H data...")')
code = code.replace('print(f"[SMART SLEEP]', 'log_activity(f"[SMART SLEEP]')
code = code.replace('print("[4] Waking up QA Analyst...")', 'log_activity("[4] QA Analyst grading backtest output and writing constraints...")')
code = code.replace('print("[5] Syncing to GitHub...")', 'log_activity("[5] Auto-Syncing Agent Memory & Code to GitHub main branch...")')
code = code.replace('print("[6] Cycle Complete. Resting 5 seconds.")', 'log_activity("[6] Cycle Complete. Preparing next genetic mutation...")')

with open("deepseek_orchestrator.py", "w") as f:
    f.write(code)
