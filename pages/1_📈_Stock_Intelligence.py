import streamlit as st
import sqlite3
import pandas as pd
from src.database import get_alerts, DB_PATH
import os

st.set_page_config(page_title="Stock Intelligence", layout="wide")

st.markdown("""
<style>
    footer {visibility: hidden;}
    
    h1, h2, h3 { color: #4da6ff !important; font-weight: 600; letter-spacing: 0.5px; }
    div.stExpander { border: 1px solid #2d3748 !important; border-radius: 8px !important;  }
    div.stExpander p, div.stExpander li { color: #e2e8f0 !important; font-size: 1.15em !important; line-height: 1.7; }
</style>
""", unsafe_allow_html=True)

st.title("📈 Stock Intelligence")
st.markdown("---")

tab1, tab2 = st.tabs(["📊 Screener Reports", "🎯 Watchlist Manager"])

with tab1:
    st.header("Quant Agent Output")
    # Fetch only STOCK alerts
    alerts = get_alerts(category="STOCK_SWEEP")
    if not alerts:
        st.info("Awaiting stock intelligence reports...")
    else:
        for alert in alerts:
            timestamp, category, message, status = alert
            st.markdown(f"### 🕒 Report • {timestamp[:16]}")
            
            # Split the message if it contains our delimiter
            if "---THOUGHT PROCESS---" in message:
                results, thoughts = message.split("---THOUGHT PROCESS---", 1)
                
                st.markdown(results)
                
                with st.expander("🧠 View Agent Thought Process", expanded=False):
                    st.markdown(thoughts)
            else:
                st.markdown(message)
            st.markdown("---")

with tab2:
    st.header("Target Acquisition (Watchlist)")
    st.markdown("Input tickers for the Market Agent to scan on 5m, 15m, 1H, and 1D timeframes.")
    
    conn = sqlite3.connect(DB_PATH)
    df_watch = pd.read_sql_query("SELECT * FROM stock_watchlist", conn)
    
    edited_watch = st.data_editor(df_watch, num_rows="dynamic", use_container_width=True, hide_index=True)
    
    if st.button("Update Targets", type="primary"):
        edited_watch.to_sql("stock_watchlist", conn, if_exists="replace", index=False)
        st.success("Target list synchronized.")
    conn.close()
