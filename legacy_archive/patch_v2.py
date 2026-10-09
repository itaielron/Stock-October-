with open("generate_charts_alpaca.py", "r") as f:
    content = f.read()

# Change the filename output
content = content.replace('fname = f"{OUT_DIR}/chart_{i}_{ticker}_{sig[\'direction\']}.png"', 'fname = f"{OUT_DIR}/chart_v2_{i}_{ticker}_{sig[\'direction\']}.png"')

with open("generate_charts_alpaca.py", "w") as f:
    f.write(content)
