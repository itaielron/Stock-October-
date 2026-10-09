import json

with open('kanban.json', 'r') as f:
    board = json.load(f)

# Add new tasks to To Do
new_tasks = [
    {"id": "T3-B", "title": "Add signal cooldown & dedup", "desc": "15-30 min per ticker+direction", "agent": "Math Engine"},
    {"id": "T3-C", "title": "Implement bracket sanity validator", "desc": "Reject inverted TP1/SL sides of entry", "agent": "Math Engine"},
    {"id": "T3-D", "title": "Fix ATR stop scaling", "desc": "Add floor, consistent multiplier per timeframe", "agent": "Math Engine"},
    {"id": "T3-E", "title": "EMA Extension Filter", "desc": "Block chasing entries", "agent": "Math Engine"},
    {"id": "T3-F", "title": "Rework S/R stop placement", "desc": "Stop must sit beyond swing level + buffer", "agent": "Math Engine"},
    {"id": "T3-G", "title": "Recalibrate GEX gate", "desc": "Re-derive thresholds", "agent": "Math Engine"}
]

board['To Do'].extend(new_tasks)

with open('kanban.json', 'w') as f:
    json.dump(board, f, indent=4)
