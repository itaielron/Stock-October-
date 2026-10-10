import os

with open("real_alpaca_backtester.py", "r") as f:
    code = f.read()

if 'os.system("rm -f charts/*.png")' not in code:
    code = code.replace('os.makedirs(CHARTS_DIR, exist_ok=True)', 'os.makedirs(CHARTS_DIR, exist_ok=True)\n    os.system(f"rm -f {CHARTS_DIR}/*.png")')

with open("real_alpaca_backtester.py", "w") as f:
    f.write(code)

