import streamlit as st
import json
import os
import time

st.set_page_config(page_title="Stock-October- Kanban", layout="wide")
st.title("🚀 Blissful Carson - Autonomous Agent Dashboard")

KANBAN_FILE = "kanban.json"
LOG_FILE = "agent_activity.log"

if not os.path.exists(KANBAN_FILE):
    st.error("Kanban file not found. Waiting for initialization...")
else:
    with open(KANBAN_FILE, 'r') as f:
        board = json.load(f)

    cols = st.columns(4)
    statuses = ["To Do", "In Progress", "In Review", "Done"]

    for i, status in enumerate(statuses):
        with cols[i]:
            st.subheader(status)
            for task in board.get(status, []):
                st.info(f"**{task['id']}: {task['title']}**\n\n*{task['desc']}*\n\n**Assigned:** 🤖 {task['agent']}")

st.divider()
st.subheader("🧠 Live Agent Activity Log (Newest at the Top)")

try:
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        # Reverse the lines so the newest output is at the top
        lines.reverse()
        
        # Display in a scrollable container so they never disappear
        with st.container(height=600):
            st.code("".join(lines), language="markdown")
    else:
        st.code("Waiting for agent activity... (Log file not found yet)", language="markdown")
except Exception as e:
    st.code(f"Error reading logs: {e}")

st.sidebar.markdown("### Agent Memory Logs")
st.sidebar.markdown("Agents are writing their core alignments to `./agent_memory/` to prevent LLM hallucination and context bloat.")

# Auto-refresh the dashboard every 3 seconds
time.sleep(3)
st.rerun()
