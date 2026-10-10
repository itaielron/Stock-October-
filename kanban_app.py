import streamlit as st
from streamlit_autorefresh import st_autorefresh
import json
import os

st.set_page_config(page_title="Stock-October- Kanban", layout="wide")
st.title("🚀 Blissful Carson - Autonomous Agent Dashboard")
st_autorefresh(interval=2000, limit=None, key="dashboard_autorefresh")
st.success("🟢 LIVE: Seamless real-time agent updates enabled.")

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
st.subheader("📈 Verified Alpaca Backtest Charts")
chart_dir = "charts"
if os.path.exists(chart_dir):
    charts = sorted([c for c in os.listdir(chart_dir) if c.endswith(".png")], key=lambda x: os.path.getmtime(os.path.join(chart_dir, x)), reverse=True)
    if charts:
        chart_cols = st.columns(3)
        for i, chart in enumerate(charts[:12]): 
            with chart_cols[i % 3]:
                with open(os.path.join(chart_dir, chart), "rb") as img_file:
                    img_bytes = img_file.read()
                st.image(img_bytes, caption=chart, use_container_width=True)
    else:
        st.info("No charts generated yet.")

st.divider()
st.subheader("🧠 Live Agent Activity Log (Newest at the Top)")
try:
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        lines.reverse()
        with st.container(height=600):
            st.code("".join(lines), language="markdown")
    else:
        st.code("Waiting for agent activity... (Log file not found yet)", language="markdown")
except Exception as e:
    st.code(f"Error reading logs: {e}")
