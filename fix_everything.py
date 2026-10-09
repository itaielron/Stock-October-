# 1. Fix Kanban App (Scrollable Charts)
with open("kanban_app.py", "r") as f:
    kanban = f.read()

if "with st.container(height=600):" not in kanban:
    old_chart_loop = '''        chart_cols = st.columns(3)
        for i, chart in enumerate(charts[:9]): 
            with chart_cols[i % 3]:'''
    new_chart_loop = '''        with st.container(height=600):
            chart_cols = st.columns(3)
            for i, chart in enumerate(charts[:30]): 
                with chart_cols[i % 3]:'''
    kanban = kanban.replace(old_chart_loop, new_chart_loop)
    with open("kanban_app.py", "w") as f:
        f.write(kanban)


# 2. Fix Orchestrator (Foolproof Main Block)
with open("deepseek_orchestrator.py", "r") as f:
    orch = f.read()

foolproof = """            if success:
                log_activity("[2] Coder actively injected new confluence logic.")
                # FOOLPROOF: Ensure __main__ exists!
                with open("real_alpaca_backtester.py", "r") as rfile:
                    if 'if __name__ == "__main__":' not in rfile.read():
                        with open("real_alpaca_backtester.py", "a") as afile:
                            afile.write('\\n\\nif __name__ == "__main__":\\n    _start = sys.argv[1] if len(sys.argv) > 1 else None\\n    _end = sys.argv[2] if len(sys.argv) > 2 else None\\n    run_backtest(start=_start, end=_end)\\n')
            else:"""

orch = orch.replace("""            if success:
                log_activity("[2] Coder actively injected new confluence logic.")
            else:""", foolproof)

with open("deepseek_orchestrator.py", "w") as f:
    f.write(orch)

