import streamlit as st
import sqlite3
import pandas as pd
from src.database import get_optimizations, DB_PATH

st.set_page_config(page_title="Optimization Insights", layout="wide")

st.markdown("""
<style>
    footer {visibility: hidden;}
    
    h1, h2, h3 { color: #4da6ff !important; font-weight: 600; letter-spacing: 0.5px; }
    div.stExpander { border: 1px solid #2d3748 !important; border-radius: 8px !important;  }
    div.stExpander p, div.stExpander li { color: #e2e8f0 !important; font-size: 1.15em !important; line-height: 1.7; }

</style>
""", unsafe_allow_html=True)

st.title("💡 Optimization Insights")
st.markdown("---")
st.markdown("Passive DeepSeek Architectural Reviews of system performance and data output.")

opts = get_optimizations()
if not opts:
    st.info("Awaiting the first architectural review sweep...")
else:
    for opt in opts:
        timestamp, project, suggestion = opt
        with st.expander(f"Review: {project} ({timestamp[:16]})", expanded=False):
            st.markdown(suggestion)
