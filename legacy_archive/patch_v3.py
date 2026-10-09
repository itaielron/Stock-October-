with open("generate_charts_alpaca.py", "r") as f:
    content = f.read()

# Fix the timezone mapping to Asia/Jerusalem
tz_logic = """        if data.index.tz is not None:
            alert_dt = alert_dt.astimezone(data.index.tz)
        else:
            alert_dt = alert_dt.replace(tzinfo=None)"""

new_tz_logic = """        import pytz
        israel_tz = pytz.timezone('Asia/Jerusalem')
        
        # Convert dataframe index to Israel time
        if data.index.tz is None:
            data.index = data.index.tz_localize('UTC')
        data.index = data.index.tz_convert(israel_tz)
        
        # Convert alert_dt to Israel time
        alert_dt = alert_dt.astimezone(israel_tz)"""

content = content.replace(tz_logic, new_tz_logic)

# Fix title cutoff
plot_logic = "mpf.plot(data, type='candle', style=s, addplot=ap, hlines=hlines, vlines=vlines, title=title, savefig=fname, figsize=(10, 6))"
new_plot_logic = """
        fig, axes = mpf.plot(data, type='candle', style=s, addplot=ap, hlines=hlines, vlines=vlines, title=title, figsize=(10, 7), returnfig=True)
        fig.subplots_adjust(top=0.85) # Prevent title cutoff
        fig.savefig(fname)
"""
content = content.replace(plot_logic, new_plot_logic)

# Update filename to v3
content = content.replace("chart_v2_", "chart_v3_")

with open("generate_charts_alpaca.py", "w") as f:
    f.write(content)
