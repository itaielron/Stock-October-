import re

with open("real_alpaca_backtester.py", "r") as f:
    content = f.read()

# Fix the broken crossover logic block
bad_block = """    crossover = (float(row["EMA9"]) > float(row["EMA21"])) # 
        float(prev["EMA9"]) <= float(prev["EMA21"])
        and float(row["EMA9"]) > float(row["EMA21"])
    )"""
    
good_block = """    crossover = (float(row["EMA9"]) > float(row["EMA21"]))"""

content = content.replace(bad_block, good_block)

with open("real_alpaca_backtester.py", "w") as f:
    f.write(content)
