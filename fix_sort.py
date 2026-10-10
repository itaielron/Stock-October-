import os
import re

with open("kanban_app.py", "r") as f:
    code = f.read()

# Fix the sorting logic to sort by os.path.getmtime (newest first) instead of alphabetically
old_sort = 'charts = sorted([c for c in os.listdir(chart_dir) if c.endswith(".png")], reverse=True)'
new_sort = 'charts = sorted([c for c in os.listdir(chart_dir) if c.endswith(".png")], key=lambda x: os.path.getmtime(os.path.join(chart_dir, x)), reverse=True)'
code = code.replace(old_sort, new_sort)

# Change limit to 12 as requested
code = code.replace('for i, chart in enumerate(charts[:30]):', 'for i, chart in enumerate(charts[:12]):')

with open("kanban_app.py", "w") as f:
    f.write(code)
