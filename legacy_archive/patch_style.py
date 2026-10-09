with open("generate_charts_alpaca.py", "r") as f:
    content = f.read()

content = content.replace("base_mpf_style='cyberpunk'", "base_mpf_style='nightclouds'")

with open("generate_charts_alpaca.py", "w") as f:
    f.write(content)
