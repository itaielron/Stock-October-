import re

with open("real_alpaca_backtester.py", "r") as f:
    code = f.read()

# Make timeframe dynamic
code = code.replace('timeframe: str = "5Min"', 'timeframe: str = os.getenv("BACKTEST_TF", "5Min")')
code = code.replace('"timeframe": "5Min",', '"timeframe": os.getenv("BACKTEST_TF", "5Min"),')
# Make sure run_backtest accepts it, though environment variable is easier so we don't have to change the function signature everywhere.

with open("real_alpaca_backtester.py", "w") as f:
    f.write(code)

with open("deepseek_orchestrator.py", "r") as f:
    orch = f.read()

# Update orchestrator to rotate timeframes and save successes instead of sleeping
new_orch_logic = """
        tf_list = ["1Min", "5Min", "15Min", "1Hour", "4Hour"]
        current_tf = tf_list[(cycle - 1) % len(tf_list)]
        print(f"[3] Executing Walk-Forward Backtest on {current_tf} data...")
        os.system(f"export BACKTEST_TF={current_tf} && source venv/bin/activate && python real_alpaca_backtester.py > backtest_temp.log 2>&1")
        backtest_out = open("backtest_temp.log").read()
        
        # Check Smart Sleep Protocol -> Changed to Success Logging & Rotation
        if "win_rate=" in backtest_out:
            try:
                wr_str = re.search(r"win_rate=([0-9\.]+)", backtest_out).group(1)
                wr = float(wr_str)
                trades_str = re.search(r"trades=([0-9]+)", backtest_out).group(1)
                trades = int(trades_str)
                if trades >= 5 and wr >= 80.0:
                    log_activity(f"[SUCCESS] Target achieved on {current_tf}! Trades: {trades}, WR: {wr}%. Logging to proven_strategies.md...")
                    with open("agent_logs/proven_strategies.md", "a") as f:
                        f.write(f"\\n\\n### Successful Regime: {current_tf} (WR: {wr}%, Trades: {trades})\\n```python\\n{target_func}\\n```\\n")
                    log_activity(f"[ROTATING] Moving to next timeframe...")
                    continue
            except:
                pass
"""

# Replace the old backtest execution and sleep logic
import re
orch = re.sub(r'print\("\[3\] Executing Walk-Forward Backtest.*?\n.*?\n.*?\n.*?\n.*?\n.*?\n.*?\n.*?\n.*?\n.*?\n.*?\n.*?\n.*?\n.*?\n.*?\n.*?\n.*?\n', new_orch_logic.lstrip(), orch, flags=re.DOTALL)

with open("deepseek_orchestrator.py", "w") as f:
    f.write(orch)
