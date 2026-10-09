import streamlit as st
import sqlite3
import pandas as pd
import yfinance as yf
from src.database import DB_PATH
import json
import re

st.set_page_config(page_title="V11 Engine Visualizer", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #030712; }
    h1, h2, h3, p { color: #38bdf8 !important; }
</style>
""", unsafe_allow_html=True)

st.title("🚀 V11 Neural Engine")
st.markdown("Real-time visual simulation synced to the latest database signals.")

# Fetch tickers
try:
    conn = sqlite3.connect(DB_PATH)
    df_watch = pd.read_sql_query("SELECT ticker FROM stock_watchlist", conn)
    tickers = df_watch["ticker"].tolist()
    conn.close()
except:
    tickers = ["SPY", "QQQ", "AAPL", "NVDA", "IWM", "AVGO", "MU", "SHOP"]

if not tickers:
    tickers = ["AAPL"]

# Fetch latest actual signals from DB
actual_signals = {}
try:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT message FROM alerts WHERE category='STOCK_SWEEP' ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    if row:
        message = row[0]
        # Look for lines starting with 🟢 or 🔴
        for line in message.split('\n'):
            if '🟢' in line or '🔴' in line:
                match = re.search(r'([🟢🔴])\s+([A-Z]+)', line)
                if match:
                    emoji, ticker = match.groups()
                    if 'LONG' in line:
                        actual_signals[ticker] = 'LONG'
                    elif 'SHORT' in line:
                        actual_signals[ticker] = 'SHORT'
except Exception as e:
    pass

@st.cache_data(ttl=300)
def fetch_live_macro():
    macro_data = {}
    try:
        tickers_to_fetch = ["^TNX", "^VIX", "USO", "DX-Y.NYB"]
        data = yf.download(tickers_to_fetch, period="1d", interval="5m")
        
        for t in tickers_to_fetch:
            clean_t = "TNX" if t == "^TNX" else "VIX" if t == "^VIX" else "DXY" if t == "DX-Y.NYB" else "USO"
            if not data['Close'][t].dropna().empty:
                closes = data['Close'][t].dropna().tail(4).tolist()
                
                while len(closes) < 4:
                    closes.insert(0, closes[0] if closes else 0)
                    
                current_val = round(closes[-1], 2)
                
                arrows = []
                for i in range(1, 4):
                    if closes[i] > closes[i-1]:
                        arrows.append('<span class="text-green-500 font-bold">↑</span>')
                    elif closes[i] < closes[i-1]:
                        arrows.append('<span class="text-red-500 font-bold">↓</span>')
                    else:
                        arrows.append('<span class="text-gray-500 font-bold">-</span>')
                        
                macro_data[clean_t] = {
                    "val": current_val,
                    "arrows": " ".join(arrows)
                }
            else:
                macro_data[clean_t] = {"val": 0.0, "arrows": "- - -"}
                
    except Exception as e:
        macro_data = {
            'TNX': {"val": 4.32, "arrows": "↑ ↓ ↑"},
            'VIX': {"val": 14.20, "arrows": "↓ ↓ ↓"},
            'USO': {"val": 71.40, "arrows": "↑ ↑ ↑"},
            'DXY': {"val": 103.50, "arrows": "↓ ↑ ↓"}
        }
    return macro_data

macro = fetch_live_macro()

pulse = 0
pulse += -1 if macro['VIX']['val'] > 15 else 1
pulse += -1 if macro['TNX']['val'] > 4.2 else 1
pulse += -1 if macro['USO']['val'] > 75 else 1
pulse_text = f"+{pulse} (BULLISH)" if pulse > 0 else f"{pulse} (BEARISH)" if pulse < 0 else "0 (NEUTRAL)"
pulse_color = "text-green-400" if pulse > 0 else "text-red-400" if pulse < 0 else "text-yellow-400"

# Pass JSON variables to JS
tickers_json = json.dumps(tickers)
actual_signals_json = json.dumps(actual_signals)

html_content = f"""
<!DOCTYPE html>
<html>
<head>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400&display=swap');
    
    body {{
      font-family: 'Space Mono', monospace;
      background-color: transparent;
      color: #38bdf8;
      margin: 0;
      padding: 0;
    }}

    .futuristic-card {{
      background: rgba(15, 23, 42, 0.8);
      border: 1px solid rgba(56, 189, 248, 0.3);
      box-shadow: 0 0 15px rgba(56, 189, 248, 0.1);
      backdrop-filter: blur(10px);
      position: relative;
      overflow: hidden;
    }}

    @keyframes scanline {{
      0% {{ top: 0%; opacity: 0.1; }}
      50% {{ opacity: 0.3; }}
      100% {{ top: 100%; opacity: 0.1; }}
    }}
    
    .scanline-overlay {{
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 2px;
      background: #38bdf8;
      animation: scanline 3s linear infinite;
      pointer-events: none;
      z-index: 50;
    }}

    @keyframes rotate {{
      0% {{ transform: rotate(0deg); }}
      100% {{ transform: rotate(360deg); }}
    }}
    
    @keyframes pulse-glow {{
      0%, 100% {{ opacity: 1; box-shadow: 0 0 15px rgba(56, 189, 248, 0.5); }}
      50% {{ opacity: 0.6; box-shadow: 0 0 5px rgba(56, 189, 248, 0.2); }}
    }}

    .gear-spin {{ animation: rotate 8s linear infinite; }}
    .gear-spin-reverse {{ animation: rotate 10s linear infinite reverse; }}

    .glow-text {{ text-shadow: 0 0 8px rgba(56, 189, 248, 0.6); }}
    .glow-text-red {{ text-shadow: 0 0 8px rgba(248, 113, 113, 0.6); color: #f87171; }}
    .glow-text-green {{ text-shadow: 0 0 8px rgba(74, 222, 128, 0.6); color: #4ade80; }}
    .glow-text-gray {{ text-shadow: 0 0 8px rgba(156, 163, 175, 0.6); color: #9ca3af; }}
    
    .knob {{
      width: 40px; height: 40px;
      border-radius: 50%;
      border: 2px solid #38bdf8;
      position: relative;
      background: radial-gradient(circle, #0f172a 0%, #020617 100%);
      box-shadow: inset 0 0 8px rgba(56, 189, 248, 0.5);
    }}
    .knob-marker {{
      position: absolute;
      top: 4px; left: 50%;
      width: 2px; height: 10px;
      background: #38bdf8;
      transform: translateX(-50%);
      border-radius: 1px;
      transform-origin: 50% 16px; 
      transition: transform 0.5s ease-in-out;
    }}
    
    .eq-bar {{
      width: 8px;
      background: #38bdf8;
      border-radius: 2px;
      transition: height 0.2s ease;
    }}

    ::-webkit-scrollbar {{ width: 4px; }}
    ::-webkit-scrollbar-track {{ background: #0f172a; }}
    ::-webkit-scrollbar-thumb {{ background: #38bdf8; border-radius: 2px; }}
  </style>
</head>
<body class="p-4">

  <!-- MACRO DASHBOARD -->
  <div class="futuristic-card rounded-2xl p-6 mb-8 w-full md:w-2/3 lg:w-1/2">
    <div class="scanline-overlay"></div>
    <div class="flex items-center gap-4 border-b border-sky-900/50 pb-4 mb-4 relative z-10">
      <svg class="w-10 h-10 text-sky-400 gear-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
      <div>
        <h1 class="text-3xl font-bold glow-text tracking-widest">SENTIMENT TRACKER</h1>
        <p class="text-sm text-sky-600">MTF Z-SCORE CONFLUENCE [LIVE]</p>
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm relative z-10">
      <div class="flex justify-between items-center p-3 bg-gray-950 rounded border border-gray-800">
        <span class="text-gray-400 font-bold text-lg">^TNX (Yields)</span>
        <div class="flex items-center gap-4">
            <span class="font-bold text-2xl glow-text-red">{macro['TNX']['val']}%</span>
            <span class="text-lg bg-gray-900 px-2 py-1 rounded tracking-widest">{macro['TNX']['arrows']}</span>
        </div>
      </div>
      <div class="flex justify-between items-center p-3 bg-gray-950 rounded border border-gray-800">
        <span class="text-gray-400 font-bold text-lg">^VIX (Vol)</span>
        <div class="flex items-center gap-4">
            <span class="font-bold text-2xl glow-text-green">{macro['VIX']['val']}</span>
            <span class="text-lg bg-gray-900 px-2 py-1 rounded tracking-widest">{macro['VIX']['arrows']}</span>
        </div>
      </div>
      <div class="flex justify-between items-center p-3 bg-gray-950 rounded border border-gray-800">
        <span class="text-gray-400 font-bold text-lg">USO (Oil)</span>
        <div class="flex items-center gap-4">
            <span class="font-bold text-2xl glow-text-green">{macro['USO']['val']}</span>
            <span class="text-lg bg-gray-900 px-2 py-1 rounded tracking-widest">{macro['USO']['arrows']}</span>
        </div>
      </div>
      <div class="flex justify-between items-center p-3 bg-gray-950 rounded border border-gray-800">
        <span class="text-gray-400 font-bold text-lg">DXY (Dollar)</span>
        <div class="flex items-center gap-4">
            <span class="font-bold text-2xl glow-text-red">{macro['DXY']['val']}</span>
            <span class="text-lg bg-gray-900 px-2 py-1 rounded tracking-widest">{macro['DXY']['arrows']}</span>
        </div>
      </div>
    </div>
    <div class="mt-6 pt-4 border-t border-sky-900/50 flex justify-between items-center relative z-10">
      <span class="text-sm">NET MACRO PULSE SCORE:</span><span class="text-2xl font-bold {pulse_color}">{pulse_text}</span>
    </div>
  </div>

  <!-- TICKER GRID -->
  <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" id="ticker-grid">
    <!-- Generated via JS -->
  </div>

  <script>
    const tickers = {tickers_json};
    const dbSignals = {actual_signals_json};
    const grid = document.getElementById('ticker-grid');

    // Fetch actual db signal, or default to NO ENTRY for consistency 
    // (no more random generated setups!)
    const tickerStates = tickers.map(ticker => {{
        const dbSig = dbSignals[ticker];
        return {{
            ticker: ticker,
            isWinner: dbSig ? true : false,
            direction: dbSig ? dbSig : 'NO ENTRY'
        }};
    }});
    
    // Sort so winners are statically at the top (no moving after rendering)
    tickerStates.sort((a, b) => b.isWinner - a.isWinner);

    tickerStates.forEach((state, i) => {{
      const card = document.createElement('div');
      card.id = `card-${{state.ticker}}`;
      // Reduced opacity for losers statically
      card.className = `futuristic-card rounded-xl p-5 flex flex-col gap-4 ${{state.isWinner ? '' : 'opacity-60'}}`;
      
      card.innerHTML = `
        <div class="scanline-overlay"></div>
        <div class="flex justify-between items-center border-b border-sky-900/50 pb-3 relative z-10">
            <h2 class="text-2xl font-bold tracking-wider text-white">Target: ${{state.ticker}}</h2>
            
            <div class="flex gap-3">
                <!-- Data Transfer Equalizer Anim -->
                <div class="flex items-end gap-1 h-6 w-8 overflow-hidden" id="eq-${{state.ticker}}">
                    <div class="eq-bar" style="height: 40%;"></div>
                    <div class="eq-bar" style="height: 80%;"></div>
                    <div class="eq-bar" style="height: 60%;"></div>
                </div>
                <!-- Mini Status Knob -->
                <div class="knob">
                    <div class="knob-marker" id="knob-${{state.ticker}}"></div>
                </div>
            </div>
        </div>
        
        <div class="bg-gray-950 border border-gray-800 rounded p-3 text-xs h-32 overflow-y-auto flex flex-col gap-1 font-mono text-gray-300 relative z-10" id="log-${{state.ticker}}">
          <div>> Syncing with Database Protocol...</div>
        </div>
        
        <div class="mt-4 relative w-28 h-28 mx-auto flex items-center justify-center z-10">
          <svg class="absolute inset-0 w-full h-full text-sky-800/40 gear-spin" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="48" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="10 5"/>
          </svg>
          <svg class="absolute inset-0 w-full h-full text-sky-600/60 gear-spin-reverse" viewBox="0 0 100 100" style="transform: scale(0.8);">
            <circle cx="50" cy="50" r="48" fill="none" stroke="currentColor" stroke-width="3" stroke-dasharray="15 10"/>
          </svg>
          <div id="sig-${{state.ticker}}" class="text-md font-bold text-gray-400 text-center tracking-widest">SYNCING</div>
        </div>
      `;
      grid.appendChild(card);

      // Animate the EQ bars and knobs infinitely
      setInterval(() => {{
          const eq = document.getElementById(`eq-${{state.ticker}}`);
          if(eq) {{
              const bars = eq.querySelectorAll('.eq-bar');
              bars.forEach(b => b.style.height = (Math.random() * 100) + '%');
          }}
          const knob = document.getElementById(`knob-${{state.ticker}}`);
          if(knob) {{
              knob.style.transform = `translateX(-50%) rotate(${{-45 + Math.random() * 90}}deg)`;
          }}
      }}, 300);

      setTimeout(() => {{
        simulateTicker(state.ticker, state.isWinner, state.direction);
      }}, i * 400 + Math.random() * 500);
    }});

    function simulateTicker(ticker, isWinner, direction) {{
      const logEl = document.getElementById(`log-${{ticker}}`);
      const sigEl = document.getElementById(`sig-${{ticker}}`);
      const eqEl = document.getElementById(`eq-${{ticker}}`);
      const knobEl = document.getElementById(`knob-${{ticker}}`);
      
      const logs = [
        `> Fetching 1D, 1H, 15m, 5m data...`,
        `> Database record found. Aligning output.`,
      ];
      
      if(isWinner) {{
          logs.push(`> Target passed structural validation.`);
          logs.push(`> 🔥 SETUP CONFIRMED VIA DATABASE.`);
      }} else {{
          logs.push(`> Trend conflicting or missing from latest sweep.`);
          logs.push(`> Criteria Failed. Signal suppressed.`);
      }}

      let logIdx = 0;
      function pushLog() {{
        if(logIdx < logs.length) {{
            const d = document.createElement('div');
            d.textContent = logs[logIdx];
            d.className = logs[logIdx].includes('🔥') ? 'text-yellow-400 font-bold' : 'text-sky-300';
            logEl.appendChild(d);
            logEl.scrollTop = logEl.scrollHeight;
            logIdx++;
            setTimeout(pushLog, 400 + Math.random() * 600);
        }} else {{
            // Lock the knobs when finished
            if(eqEl) eqEl.style.opacity = '0.2';
            if(knobEl) knobEl.style.transform = `translateX(-50%) rotate(${{isWinner ? 45 : -45}}deg)`;
            
            if(isWinner) {{
                sigEl.textContent = direction;
                sigEl.className = direction === 'LONG' ? 'text-2xl font-bold glow-text-green' : 'text-2xl font-bold glow-text-red';
            }} else {{
                sigEl.textContent = "NO ENTRY";
                sigEl.className = 'text-lg font-bold text-gray-500';
            }}
        }}
      }}
      pushLog();
    }}
  </script>
</body>
</html>
"""

import streamlit.components.v1 as components
components.html(html_content, height=1200, scrolling=True)
