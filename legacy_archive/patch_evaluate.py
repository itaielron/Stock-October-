with open("src/evaluate_trades.py", "r") as f:
    content = f.read()
    
# Replace the old float regex with one that requires digits
content = content.replace("r'\\|\\s*Entry[^\\|]*\\|\\s*~?([\\d\\.]+)'", "r'\\|\\s*Entry[^\\|]*\\|\\s*~?([\\d]+\\.[\\d]+)'")

with open("src/evaluate_trades.py", "w") as f:
    f.write(content)
