import streamlit as st
import os
from src.database import init_db, DB_PATH

if not os.path.exists(DB_PATH):
    init_db()

st.set_page_config(page_title="Orbital Command", page_icon="🌐", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    /* Hide the right-side toolbar and Deploy button, but KEEP the header so the sidebar expander button is clickable! */
    
    footer {visibility: hidden;}
    
    h1, h2, h3 { color: #4da6ff !important; font-weight: 600; letter-spacing: 0.5px; }
    div.stExpander { border: 1px solid #2d3748 !important; border-radius: 8px !important;  }
    div.stExpander p, div.stExpander li { color: #e2e8f0 !important; font-size: 1.15em !important; line-height: 1.7; }
    .stDataFrame { border-radius: 8px; overflow: hidden; border: 1px solid #2d3748; }
</style>
""", unsafe_allow_html=True)

st.title("🌐 ORBITAL COMMAND - HUB")
st.markdown("---")
st.markdown("Welcome to the Autonomous Agent OS. Navigate to specific intelligence sectors using the sidebar.")

st.header("System Diagnostics")
col1, col2, col3 = st.columns(3)
col1.metric("Database", "ONLINE", "Latency: 2ms")
col2.metric("DeepSeek Uplink", "CONNECTED", "Ping: 45ms")
col3.metric("Daemon Status", "ACTIVE", "Schedule: Active Market Hours")
