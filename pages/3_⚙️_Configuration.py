import streamlit as st
import sqlite3
import pandas as pd
from src.database import DB_PATH

st.set_page_config(page_title="Configuration", layout="wide")

st.markdown("""
<style>
    footer {visibility: hidden;}
    
    h1, h2, h3 { color: #4da6ff !important; font-weight: 600; letter-spacing: 0.5px; }
    .stDataFrame { border-radius: 8px; overflow: hidden; border: 1px solid #2d3748; }
</style>
""", unsafe_allow_html=True)

st.title("⚙️ Neural Configuration")
st.markdown("---")
st.markdown("Tweak agent instructions. The background daemon updates automatically on the next sweep.")

conn = sqlite3.connect(DB_PATH)
df_agents = pd.read_sql_query("SELECT * FROM agent_config", conn)

edited_agents = st.data_editor(df_agents, num_rows="dynamic", use_container_width=True, hide_index=True)

if st.button("Flash Memory", type="primary"):
    edited_agents.to_sql("agent_config", conn, if_exists="replace", index=False)
    st.success("Agent neural pathways updated.")
conn.close()
