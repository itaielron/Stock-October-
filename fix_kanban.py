with open("kanban_app.py", "r") as f:
    code = f.read()

# Replace the entire charts block so it's guaranteed scrollable
old_block = """st.subheader("📈 Verified Alpaca Backtest Charts")
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
        st.info("No charts generated yet.")"""

new_block = """st.subheader("📈 Verified Alpaca Backtest Charts")
chart_dir = "charts"
if os.path.exists(chart_dir):
    charts = sorted([c for c in os.listdir(chart_dir) if c.endswith(".png")], key=lambda x: os.path.getmtime(os.path.join(chart_dir, x)), reverse=True)
    if charts:
        with st.container(height=600):
            chart_cols = st.columns(3)
            for i, chart in enumerate(charts[:12]): 
                with chart_cols[i % 3]:
                    with open(os.path.join(chart_dir, chart), "rb") as img_file:
                        img_bytes = img_file.read()
                    st.image(img_bytes, caption=chart, use_container_width=True)
    else:
        st.info("No charts generated yet.")"""

if old_block in code:
    code = code.replace(old_block, new_block)
elif 'for i, chart in enumerate(charts[:9]):' in code: # Check if it's still 9
    code = code.replace('for i, chart in enumerate(charts[:9]):', 'for i, chart in enumerate(charts[:12]):')

with open("kanban_app.py", "w") as f:
    f.write(code)

