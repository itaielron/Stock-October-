import re

with open("src/daemon.py", "r") as f:
    content = f.read()

discord_logic = """
        discord_content = stock_result
        if "---THOUGHT PROCESS---" in stock_result:
            discord_content = stock_result.split("---THOUGHT PROCESS---")[0].strip()
            
        send_discord_message(f"🚨 **Stock Intelligence Alert** 🚨\\n\\n{discord_content}")
"""

new_discord_logic = """
        # Strip out conversational fluff and Thought Process for Discord
        discord_content = stock_result.split("---THOUGHT PROCESS---")[0].strip()
        
        # Only extract the actual signals starting with 🟢 or 🔴
        signals = []
        for block in discord_content.split('FINAL VERIFIED RESULTS'):
            if '🟢' in block or '🔴' in block:
                signals.append(block.strip())
                
        if signals:
            clean_signals = "\\n\\n".join(signals)
            send_discord_message(f"🚨 **Stock Intelligence Alert** 🚨\\n\\n# FINAL VERIFIED RESULTS\\n{clean_signals}")
        else:
            send_discord_message("🚨 **Stock Intelligence Alert** 🚨\\n\\nNo tickers passed the strict criteria today. None qualify.")
    else:
        send_discord_message("🚨 **Stock Intelligence Alert** 🚨\\n\\nNo tickers passed the strict criteria today. None qualify.")
"""

# We need to replace the if block correctly.
# Let's just use sed or Python to parse and replace the exact lines in daemon.py
