import json

with open('kanban.json', 'r') as f:
    board = json.load(f)

# Move M1 to Done
m1_task = None
for t in board['In Progress']:
    if t['id'] == 'M1':
        m1_task = t
        board['In Progress'].remove(t)
        break

if m1_task:
    board['Done'].append(m1_task)

# Move T2 to In Progress
t2_task = None
for t in board['To Do']:
    if t['id'] == 'T2':
        t2_task = t
        board['To Do'].remove(t)
        break

if t2_task:
    board['In Progress'].append(t2_task)

with open('kanban.json', 'w') as f:
    json.dump(board, f, indent=4)
