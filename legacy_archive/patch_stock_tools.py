import re

with open("src/tools/stock_tools.py", "r") as f:
    content = f.read()

old_logic = """    if score >= 85:
        report["Trade_Ready"] = "YES - Criteria Met!"
        report["Suggested_StopLoss"] = round(current_close - (1.5 * atr), 2)
        report["Suggested_Target1 (2R)"] = round(current_close + (3.0 * atr), 2)
        report["Suggested_Target2 (4R)"] = round(current_close + (6.0 * atr), 2)"""

new_logic = """    if score >= 85:
        report["Trade_Ready"] = "YES - Criteria Met!"
        if "Uptrend" in trend:
            report["Suggested_StopLoss"] = round(current_close - (1.5 * atr), 2)
            report["Suggested_Target1 (2R)"] = round(current_close + (3.0 * atr), 2)
            report["Suggested_Target2 (4R)"] = round(current_close + (6.0 * atr), 2)
        else: # Downtrend (Short Setup)
            report["Suggested_StopLoss"] = round(current_close + (1.5 * atr), 2)
            report["Suggested_Target1 (2R)"] = round(current_close - (3.0 * atr), 2)
            report["Suggested_Target2 (4R)"] = round(current_close - (6.0 * atr), 2)"""

content = content.replace(old_logic, new_logic)

with open("src/tools/stock_tools.py", "w") as f:
    f.write(content)
