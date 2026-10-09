import streamlit as st
from src.database import get_alerts

st.set_page_config(page_title="Flight Intelligence", layout="wide")

st.markdown("""
<style>
    footer {visibility: hidden;}
    
    h1, h2, h3 { color: #4da6ff !important; font-weight: 600; letter-spacing: 0.5px; }
    div.stExpander { border: 1px solid #2d3748 !important; border-radius: 8px !important;  }
    div.stExpander p, div.stExpander li, div.stExpander a { color: #e2e8f0 !important; font-size: 1.05em; line-height: 1.6; }
    div.stExpander a { color: #00f0ff !important; text-decoration: underline; }
</style>
""", unsafe_allow_html=True)

st.title("✈️ Flight Intelligence")
st.markdown("---")

st.header("Vacation Deal Finder Output")
# Fetch only FLIGHT alerts
alerts = get_alerts(category="FLIGHT_SWEEP")
if not alerts:
    st.info("Awaiting flight intelligence reports...")
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
