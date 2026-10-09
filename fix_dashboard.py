with open("kanban_app.py", "r") as f:
    code = f.read()

# Add import
if "streamlit_autorefresh" not in code:
    code = code.replace("import streamlit as st", "import streamlit as st\nfrom streamlit_autorefresh import st_autorefresh")

# Replace stupid tip with autorefresh call
old_tip = 'st.info("💡 Tip: Press \'R\' or refresh your browser to see the latest agent updates.")'
new_code = 'st_autorefresh(interval=2000, limit=None, key="dashboard_autorefresh")\nst.success("🟢 LIVE: Seamless real-time agent updates enabled.")'

code = code.replace(old_tip, new_code)

with open("kanban_app.py", "w") as f:
    f.write(code)
