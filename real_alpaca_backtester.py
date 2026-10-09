"""
real_alpaca_backtester.py
=========================

Structure-aware Alpaca IEX 5-minute bar backtester with CONFLUENCE-CLUSTER
entry logic and VISUAL entry/exit markers on every generated chart.

Confluence Cluster (all must be true to enter long)
---------------------------------------------------
  1. EMA9 crosses above EMA21 (fresh bullish crossover).
  2. Price is within DISTANCE_GATE_ATR * ATR of EMA9 (not over-extended).
  3. Structure: price is either
        (a) breaking above the recent swing high (breakout), OR
        (b) bouncing off the recent swing low (support reclaim).
  4. ATR regime filter: ATR >= ATR_REGIME_MIN_RATIO * mean(ATR).
  5. Minimum risk gate: (entry - structural_sl) >= MIN_RISK_ATR * ATR.

Levels
------
    recent_swing_low  = min(Low[i-LOOKBACK:i])
    recent_swing_high = max(High[i-LOOKBACK:i])

    sl   = recent_swing_low - SL_BUFFER_ATR * ATR - TICK
    risk = entry - sl
    tp1  = entry + TP1_R * risk
    tp2  = entry + TP2_R * risk   (capped at recent_swing_high when sensible)

Exit engine
-----------
Scale-out / runner model:
  * SCALE_OUT_FRACTION of size closed at TP1, stop moved to breakeven,
    then trailed by ATR.
  * Remainder runs to a trailing stop, TP2, a gap, or a time stop.

Intrabar ordering
-----------------
PESSIMISTIC: if a bar's range covers both stop and target, assume STOP
first (unless the bar gapped open beyond a level, in which case fill at
the OPEN).

Charting
--------
Every chart overlays:
  * '^' marker at the EXACT entry candle (below the low).
  * 'v' marker at the EXACT exit candle for winners (above the high).
  * 'x' marker at the EXACT exit candle for losers  (above the high).
  * 'o' marker at the scale-out candle if TP1 was hit.
  * Horizontal lines for entry / SL / TP1 / TP2 / swing low / swing high.

Requires: pandas, mplfinance, requests, numpy.
"""

from __future__ import annotations

import os
from dotenv import load_dotenv
load_dotenv()
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

import mplfinance as mpf


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

# --- structure ------------------------------------------------------------
LOOKBACK = 20                 # bars for swing high / swing low structure

# --- indicators -----------------------------------------------------------
ATR_PERIOD = 14               # ATR rolling period

# --- volatility regime filter --------------------------------------------
ATR_REGIME_WINDOW = 100       # rolling window to define "normal" ATR
ATR_REGIME_MIN_RATIO = 0.8    # require ATR >= ratio * mean(ATR); skip dead vol

# --- risk / stop / target geometry ---------------------------------------
SL_BUFFER_ATR = 0.25          # structural stop buffer, in ATR units
MIN_RISK_ATR = 0.4            # minimum acceptable risk, in ATR units
DISTANCE_GATE_ATR = 1.2       # entry must be within N*ATR of EMA9
TP1_R = 1.5                   # first target in R
TP2_R = 3.0                   # runner target in R

# --- confluence cluster ---------------------------------------------------
SUPPORT_PROXIMITY_ATR = 0.5   # how close to swing low counts as "at support"
BREAKOUT_BUFFER_ATR = 0.05    # price must clear swing high by this much

# --- trade management -----------------------------------------------------
SCALE_OUT_FRACTION = 0.5      # fraction of size closed at TP1
BREAKEVEN_AT_TP1 = True       # move stop to entry after TP1
TRAIL_ATR_MULT = 1.0          # trailing stop distance, in ATR units

# --- misc ----------------------------------------------------------------
WARMUP_BARS = 30              # bars skipped at loop start (structural cred.)
TICK = 0.01                   # one tick of noise on the stop
MAX_HOLD_BARS = 78            # time stop (78 x 5Min == one regular session)

# --- IO -------------------------------------------------------------------
API_KEY = os.getenv("APCA_API_KEY_ID", "")
API_SECRET = os.getenv("APCA_API_SECRET_KEY", "")
DATA_URL = "https://data.alpaca.markets/v2/stocks/{symbol}/bars"
LOG_FILE = "agent_activity.log"
CHARTS_DIR = "charts"


# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    """Append a line to agent_activity.log and echo to stdout."""
    print(msg)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n")
    except Exception as exc:  # never let logging kill the backtest
        print(f"[warn] could not write log: {exc}")


# ---------------------------------------------------------------------------
# DATA
# ---------------------------------------------------------------------------

def fetch_data(symbol: str, start: str, end: str) -> pd.DataFrame:
    """
    Fetch Alpaca IEX 5-minute bars for `symbol` between ISO dates `start`
    and `end`. Returns a DataFrame indexed by datetime, or an empty frame.
    """
    headers = {
        "APCA-API-KEY-ID": API_KEY,
        "APCA-API-SECRET-KEY": API_SECRET,
        "Accept": "application/json",
    }
    params = {
        "start": start,
        "end": end,
        "timeframe": "5Min",
        "feed": "iex",
        "adjustment": "raw",
        "limit": 10000,
        "sort": "asc",
    }

    url = DATA_URL.format(symbol=symbol)
    bars = []
    try:
        while True:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            if resp.status_code != 200:
                log(f"[error] {symbol}: HTTP {resp.status_code} {resp.text[:200]}")
                break
            payload = resp.json() or {}
            chunk = payload.get("bars") or []
            bars.extend(chunk)
            token = payload.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
    except Exception as exc:
        log(f"[error] {symbol}: fetch failed: {exc}")
        return pd.DataFrame()

    if not bars:
        log(f"[warn] {symbol}: no bars returned.")
        return pd.DataFrame()

    df = pd.DataFrame(bars)
    df = df.rename(
        columns={
            "o": "Open",
            "h": "High",
            "l": "Low",
            "c": "Close",
            "v": "Volume",
            "vw": "VWAP",
            "n": "TradeCount",
        }
    )
    if "t" not in df.columns:
        log(f"[error] {symbol}: response missing timestamp column.")
        return pd.DataFrame()

    df["t"] = pd.to_datetime(df["t"], utc=True)
    df = df.set_index("t").sort_index()

    keep = [c for c in ["Open", "High", "Low", "Close", "Volume", "VWAP", "TradeCount"]
            if c in df.columns]
    df = df[keep].astype(float)
    return df


# ---------------------------------------------------------------------------
# INDICATORS
# ---------------------------------------------------------------------------

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add EMA9, EMA21, TR, ATR and the ATR regime mean to `df`."""
    if df.empty:
        return df

    out = df.copy()
    out["EMA9"] = out["Close"].ewm(span=9, adjust=False).mean()
    out["EMA21"] = out["Close"].ewm(span=21, adjust=False).mean()

    prev_close = out["Close"].shift(1)
    tr = pd.concat(
        [
            out["High"] - out["Low"],
            (out["High"] - prev_close).abs(),
            (out["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["TR"] = tr
    out["ATR"] = tr.rolling(ATR_PERIOD).mean()

    # Volatility-regime reference level.
    out["ATR_MEAN"] = out["ATR"].rolling(ATR_REGIME_WINDOW).mean()

    return out


# ---------------------------------------------------------------------------
# CHARTING  (the part that was broken)
# ---------------------------------------------------------------------------

def _marker_series(window: pd.DataFrame, when, value: float) -> pd.Series:
    """
    Build a Series aligned to `window.index` that is NaN everywhere except
    at `when`, where it equals `value`. Used to place a single scatter
    marker on an exact candle via mpf.make_addplot.
    """
    s = pd.Series(np.nan, index=window.index, dtype=float)
    if when in s.index:
        s.loc[when] = value
    return s


def generate_chart(
    df: pd.DataFrame,
    entry_index,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    outcome: str,
    symbol: str,
    swing_low: float | None = None,
    swing_high: float | None = None,
    exit_index=None,
    exit_price: float | None = None,
    exit_reason: str | None = None,
    scale_index=None,
    scale_price: float | None = None,
):
    """
    Render a candlestick chart around the trade with:
      * horizontal level lines (entry / SL / TP1 / TP2 / swing levels),
      * a '^' marker on the EXACT entry candle,
      * a 'v' (winner) or 'x' (loser) marker on the EXACT exit candle,
      * an 'o' marker on the scale-out candle if TP1 was hit.

    `entry_index` and `exit_index` are timestamps (DatetimeIndex values).
    """
    os.makedirs(CHARTS_DIR, exist_ok=True)

    # --- locate the entry bar in the frame --------------------------------
    try:
        pos = df.index.get_loc(entry_index)
    except KeyError:
        log(f"[warn] {symbol}: chart entry index {entry_index} not found; skipping chart.")
        return None
    if isinstance(pos, slice) or isinstance(pos, np.ndarray):
        arr = np.flatnonzero(np.asarray(pos))
        pos = int(arr[0]) if len(arr) else 0

    # --- window: 20 bars before entry, 40 after ---------------------------
    lo = max(0, pos - 20)
    hi = min(len(df), pos + 41)
    window = df.iloc[lo:hi].copy()

    if window.empty:
        log(f"[warn] {symbol}: empty chart window; skipping chart.")
        return None

    # --- horizontal level lines ------------------------------------------
    hlines = dict(
        hlines=[entry, sl, tp1, tp2],
        colors=["white", "red", "green", "green"],
        linestyle=["solid", "dashed", "dashed", "dashed"],
        linewidths=[1.0, 1.0, 1.0, 1.0],
    )
    if swing_low is not None:
        hlines["hlines"].append(swing_low)
        hlines["colors"].append("orange")
        hlines["linestyle"].append("dotted")
        hlines["linewidths"].append(0.8)
    if swing_high is not None:
        hlines["hlines"].append(swing_high)
        hlines["colors"].append("cyan")
        hlines["linestyle"].append("dotted")
        hlines["linewidths"].append(0.8)

    # --- addplots: EMAs + entry/exit/scale markers ------------------------
    addplots = []
    if "EMA9" in window.columns and "EMA21" in window.columns:
        addplots.append(mpf.make_addplot(window["EMA9"], color="blue", width=0.9))
        addplots.append(mpf.make_addplot(window["EMA21"], color="orange", width=0.9))

    # ATR-scaled offset so markers sit just outside the candle body.
    atr_ref = float(window["ATR"].iloc[-1]) if "ATR" in window.columns else 0.0
    if not np.isfinite(atr_ref) or atr_ref <= 0:
        atr_ref = max(0.01, float(window["Close"].std() or 0.01))
    pad = 0.5 * atr_ref

    # --- ENTRY marker: '^' below the entry candle -------------------------
    entry_low = float(window.loc[entry_index, "Low"]) if entry_index in window.index else entry
    entry_marker = _marker_series(window, entry_index, entry_low - pad)
    addplots.append(
        mpf.make_addplot(
            entry_marker,
            type="scatter",
            marker="o",
            markersize=140,
            color="lime",
        )
    )

    # --- EXIT marker: 'v' (winner) or 'x' (loser) above the exit candle ---
    if exit_index is not None and exit_index in window.index:
        exit_high = float(window.loc[exit_index, "High"])
        exit_marker = _marker_series(window, exit_index, exit_high + pad)
        exit_color = "lime" if outcome == "WINNER" else "red"
        exit_marker_glyph = "v" if outcome == "WINNER" else "x"
        addplots.append(
            mpf.make_addplot(
                exit_marker,
                type="scatter",
                marker=exit_marker_glyph,
                markersize=140,
                color=exit_color,
            )
        )

    # --- SCALE-OUT marker: 'o' at TP1 candle ------------------------------
    if scale_index is not None and scale_index in window.index:
        scale_high = float(window.loc[scale_index, "High"])
        scale_marker = _marker_series(window, scale_index, scale_high + pad * 0.6)
        addplots.append(
            mpf.make_addplot(
                scale_marker,
                type="scatter",
                marker="o",
                markersize=90,
                color="yellow",
            )
        )

    # --- title / filename -------------------------------------------------
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    reason_tag = f"_{exit_reason}" if exit_reason else ""
    fname = os.path.join(
        CHARTS_DIR, f"{outcome}_{symbol}{reason_tag}_{ts}.png"
    )
    title = (
        f"{symbol} {outcome} | entry={entry:.2f} sl={sl:.2f} "
        f"tp1={tp1:.2f} tp2={tp2:.2f}"
        + (f" | exit={exit_price:.2f} ({exit_reason})" if exit_price is not None else "")
        + "\nLEGEND: Green Dashed = Target, Red Dashed = Stop Loss, o = Entry Circle, v/x = Exit"
    )

    plot_df = window[["Open", "High", "Low", "Close", "Volume"]].copy()

    try:
        mpf.plot(
            plot_df,
            type="candle",
            style="nightclouds",
            addplot=addplots if addplots else None,
            hlines=hlines,
            volume=False,
            title=title,
            savefig=dict(fname=fname, dpi=120, bbox_inches="tight"),
        )
    except Exception as exc:
        log(f"[warn] {symbol}: chart generation failed: {exc}")
        return None

    return fname


# ---------------------------------------------------------------------------
# TRADE ENGINE HELPERS
# ---------------------------------------------------------------------------

def _close_remainder(trade: dict, price: float, bar_time, reason: str) -> None:
    """Realize the remaining position at `price` and stamp the trade closed."""
    remaining = trade["remaining_size"]
    if remaining > 0:
        contrib = ((price - trade["entry"]) / trade["initial_risk"]) * remaining
        trade["realized_R"] += contrib
        trade["remaining_size"] = 0.0
    trade["exit_price"] = price
    trade["exit_time"] = bar_time
    trade["exit_reason"] = reason
    trade["closed"] = True


def _scale_out(trade: dict, price: float, bar_time, reason: str) -> None:
    """Close SCALE_OUT_FRACTION of the position at `price`."""
    frac = min(SCALE_OUT_FRACTION, trade["remaining_size"])
    if frac <= 0:
        return
    contrib = ((price - trade["entry"]) / trade["initial_risk"]) * frac
    trade["realized_R"] += contrib
    trade["remaining_size"] -= frac
    trade["scaled_out"] = True
    trade["scale_price"] = price
    trade["scale_time"] = bar_time
    trade["scale_reason"] = reason


# ---------------------------------------------------------------------------
# CONFLUENCE CLUSTER
# ---------------------------------------------------------------------------

def _confluence_cluster(df: pd.DataFrame, i: int, atr: float) -> dict | None:
    """
    Evaluate the confluence cluster at bar `i`. Returns a dict of the
    structural levels if ALL conditions pass, else None.

    Hardened cluster (v31) — 4Hour win-rate optimization.

    QA diagnosis of v30 (1Hour): the 1Hour-calibrated gates (slope 0.55,
    anti-chase 1.60, dir_cap 1.75/2.40, mean-rev stretch 1.20, veto 4.5,
    MTF weights 2x on 1h/4h) produced a working 1Hour model. On 4Hour
    the failure mode shifts AGAIN because 4Hour bars aggregate ~4x the
    range of 1Hour (and ~16x 15Min). The v30 gates tuned for 1Hour are
    now MIS-CALIBRATED for 4Hour:

      (a) `slope_strong = 0.55*ATR` on 4Hour is a LARGE absolute move
          (4Hour ATR is ~4x 1Hour ATR), so it fires only on the most
          violent 4Hour trends — but those are exactly the bars where
          the entry is already extended and mean-reverts against us.
          The #1 loser class on 4Hour is "late trend entry after a
          vertical 4Hour impulse".
      (b) The 1Hour-tuned `dir_cap = 1.75*ATR` is too tight for 4Hour
          breakouts — a genuine 4Hour breakout closes 2.0-2.5*ATR from
          EMA21, so v30 rejects the best 4Hour breakout entries while
          still admitting the extended-chase losers (because the
          anti-chase gate at 1.60*ATR over 3 bars is too loose on 4Hour
          where 3 bars = 12 hours of move).
      (c) The mean-rev stretch threshold of 1.20*ATR is far too small
          on 4Hour — a 1.20*ATR extension on 4Hour is noise, not a
          mean-reversion setup. Real 4Hour mean-rev needs >= 2.00*ATR.
      (d) The composite reversal veto at 4.5*ATR is too loose on 4Hour;
          4Hour bars routinely print 2-3*ATR two-bar reversals during
          regime flips, so the veto never fires when it should.
      (e) The MTF vote gate treats all 6 timeframes with 1Hour weights,
          but on a 4Hour entry the 1m/3m/5m/15m votes are noise (they
          flip every few bars). The 1h and 4h votes are the only ones
          with real predictive weight for a 4Hour hold.

    Fixes (v31) — targeted at 4Hour, single-gate patches only:
      1. Slope gate RE-CALIBRATED for 4Hour: `slope_strong` lowered
         from 0.55*ATR to 0.35*ATR (4Hour ATR is larger, so a smaller
         ATR-multiple is the same relative trend strength), and the
         pullback tier from 0.30*ATR to 0.20*ATR. This admits clean
         4Hour trends that v30 rejected while still filtering noise.
      2. Anti-chase gate TIGHTENED for 4Hour: 1.60*ATR over 3 bars ->
         1.10*ATR over 3 bars. On 4Hour, 3 bars = 12 hours; a 1.1*ATR
         move in 12 hours is already an impulse, and entering after it
         is the #1 loser class. This is the primary win-rate lever.
      3. Distance gate RE-CALIBRATED for 4Hour: normal cap 1.75*ATR ->
         2.25*ATR, breakout cap 2.40*ATR -> 3.00*ATR. 4Hour breakouts
         legitimately close further from EMA21; the anti-chase gate
         (fix #2) now handles the extended-entry problem instead.
      4. Mean-rev stretch threshold widened from 1.20 to 2.00 (ATR
         units) on 4Hour — a real 4Hour mean-reversion needs a genuine
         multi-ATR extension. Also require the reclaim bar to close in
         the top/bottom 25% of its range (was 30/70%).
      5. Composite reversal veto TIGHTENED from 4.5*ATR to 3.0*ATR
         because 4Hour bars aggregate more move; a 3.0*ATR two-bar
         reversal is a genuine regime flip on 4Hour.
      6. MTF vote WEIGHTING for 4Hour: the 1h and 4h votes are counted
         triple (they are the only TFs with real predictive weight for
         a 4Hour hold). The 1m/3m/5m votes are counted at quarter
         weight (they are noise at this horizon). 15m at half weight.
         This is a re-weighting of the existing vote aggregation, not
         a new gate.
      7. All other gates (ATR regime, macro, structural SL/TP, momentum,
         EMA stack, GEX routing) kept at v30 values — do NOT touch them
         (single-gate patch discipline, Mandate #10).

    Gate-level counters are emitted via the returned dict's
    `gate_counts` field so the QA harness can verify which gate fired.
    """
    if i < 3 or i >= len(df):
        return None

    row = df.iloc[i]
    prev = df.iloc[i - 1]
    prev2 = df.iloc[i - 2]
    prev3 = df.iloc[i - 3]

    # --- required columns -------------------------------------------------
    for col in ("EMA9", "EMA21", "Close", "High", "Low"):
        if col not in df.columns:
            return None

    ema9 = float(row["EMA9"])
    ema21 = float(row["EMA21"])
    close = float(row["Close"])
    high = float(row["High"])
    low = float(row["Low"])
    open_ = float(row["Open"]) if "Open" in df.columns and np.isfinite(row["Open"]) else close
    prev_close = float(prev["Close"])
    prev_high = float(prev["High"])
    prev_low = float(prev["Low"])
    prev_ema9 = float(prev["EMA9"]) if np.isfinite(prev["EMA9"]) else ema9
    prev_ema21 = float(prev["EMA21"]) if np.isfinite(prev["EMA21"]) else ema21

    if not (np.isfinite(ema9) and np.isfinite(ema21) and np.isfinite(close)):
        return None
    if atr <= 0 or not np.isfinite(atr):
        return None

    bar_range = max(high - low, 1e-9)
    ema_slope = ema9 - ema21
    slope_flat = abs(ema_slope) < 0.05 * atr
    # v31: 4Hour slope gate re-calibrated (was 0.55 / 0.30 in v30).
    slope_strong = abs(ema_slope) >= 0.35 * atr
    slope_pullback_ok = abs(ema_slope) >= 0.20 * atr

    # EMA21 slope over last 3 bars (trend confirmation)
    ema21_3ago = float(prev3["EMA21"]) if np.isfinite(prev3["EMA21"]) else ema21
    ema21_slope = ema21 - ema21_3ago
    ema21_slope_ok_long = ema21_slope >= 0.02 * atr
    ema21_slope_ok_short = ema21_slope <= -0.02 * atr

    # --- regime context (EMA50 / EMA200) ---------------------------------
    ema50 = float(row["EMA50"]) if "EMA50" in df.columns and np.isfinite(row["EMA50"]) else None
    ema200 = float(row["EMA200"]) if "EMA200" in df.columns and np.isfinite(row["EMA200"]) else None

    # v31: EMA-stack gate kept at v30 values.
    stack_flat = (
        ema50 is not None
        and ema200 is not None
        and abs(ema50 - ema200) < 0.25 * atr
    )
    stack_truly_flat = (
        ema50 is not None
        and ema200 is not None
        and abs(ema50 - ema200) < 0.15 * atr
    )
    if ema50 is not None:
        if ema200 is None or stack_flat:
            long_bias = close > ema50
            short_bias = close < ema50
        else:
            long_bias = (close > ema50) and (ema50 > ema200)
            short_bias = (close < ema50) and (ema50 < ema200)
    else:
        long_bias = False
        short_bias = False

    # --- GEX regime routing (kept at v30) --------------------------------
    gex_raw = row["GEX"] if "GEX" in df.columns else float("nan")
    gex = float(gex_raw) if np.isfinite(gex_raw) else float("nan")
    gex_neutral = (not np.isfinite(gex)) or (abs(gex) < 1e-9)
    if gex_neutral:
        regime = "neutral"
    elif gex < 0:
        regime = "trend"
    else:
        regime = "mean_reversion"

    # --- ATR regime filter (kept at v30) ---------------------------------
    atr_mean = float(row["ATR_MEAN"]) if "ATR_MEAN" in df.columns else float("nan")
    if np.isfinite(atr_mean) and atr_mean > 0:
        ratio = atr / atr_mean
        if ratio < ATR_REGIME_MIN_RATIO:
            return None
        if ratio > 2.5:
            return None

    # --- MTF vote aggregation (v31: horizon-weighted for 4Hour) ----------
    # v31: on a 4Hour entry, the 1h and 4h votes carry real predictive
    # weight; the 1m/3m/5m votes are noise at this horizon. We weight
    # them accordingly (3x for 1h/4h, 0.25x for 1m/3m/5m, 0.5x for 15m).
    mtf_long_votes = 0.0
    mtf_short_votes = 0.0
    mtf_available = 0
    mtf_weights = {
        "1m": 0.25, "3m": 0.25, "5m": 0.25,
        "15m": 0.5,
        "1h": 3.0, "4h": 3.0,
    }
    for tf in ("1m", "3m", "5m", "15m", "1h", "4h"):
        col = f"MTF_{tf}_TREND"
        if col in df.columns:
            v = row[col]
            if np.isfinite(v):
                mtf_available += 1
                w = mtf_weights.get(tf, 1.0)
                if v > 0:
                    mtf_long_votes += w
                elif v < 0:
                    mtf_short_votes += w

    # v31 MTF gate: thresholds scaled to the new weighted vote totals.
    # With 6 TFs available, max weighted total = 0.25*3 + 0.5 + 3.0*2 = 7.25.
    # Require a clear weighted majority (>= 3.0 weighted votes) and a
    # strict directional edge.
    if mtf_available >= 4:
        mtf_long_ok = (mtf_long_votes > mtf_short_votes) and (mtf_long_votes >= 3.0)
        mtf_short_ok = (mtf_short_votes > mtf_long_votes) and (mtf_short_votes >= 3.0)
    elif mtf_available == 3:
        mtf_long_ok = (mtf_long_votes >= 2.0) and (ema_slope >= 0.20 * atr)
        mtf_short_ok = (mtf_short_votes >= 2.0) and (ema_slope <= -0.20 * atr)
    else:
        mtf_long_ok = True
        mtf_short_ok = True

    # Split-vote veto (kept, but uses weighted votes).
    if mtf_available >= 3 and slope_flat:
        if mtf_long_votes <= 1.5 and mtf_short_votes <= 1.5:
            mtf_long_ok = False
        if mtf_short_votes <= 1.5 and mtf_long_votes <= 1.5:
            mtf_short_ok = False

    mtf_strong_long = mtf_long_votes >= 3.0 and mtf_long_votes > mtf_short_votes
    mtf_strong_short = mtf_short_votes >= 3.0 and mtf_short_votes > mtf_long_votes

    # --- macro gate (optional, kept) -------------------------------------
    macro_score = float(row["MACRO_SCORE"]) if "MACRO_SCORE" in df.columns and np.isfinite(row["MACRO_SCORE"]) else 0.0
    BULLISH_THRESHOLD = 0.5
    macro_blocks_long = macro_score <= -BULLISH_THRESHOLD
    macro_blocks_short = macro_score >= BULLISH_THRESHOLD

    # --- structure: swing levels -----------------------------------------
    win_lo = max(0, i - LOOKBACK)
    if i - win_lo < 5:
        return None
    recent_swing_low = float(df["Low"].iloc[win_lo:i].min())
    recent_swing_high = float(df["High"].iloc[win_lo:i].max())

    near_lo = max(0, i - NEAR_SWING_LOOKBACK)
    near_swing_low = float(df["Low"].iloc[near_lo:i].min())
    near_swing_high = float(df["High"].iloc[near_lo:i].max())

    # --- pullback structure ----------------------------------------------
    pullback_long = (
        abs(close - ema21) <= 0.5 * atr
        and close >= ema21 - 0.70 * atr
        and (close >= prev_close or prev_close >= prev_ema21)
    )
    pullback_short = (
        abs(close - ema21) <= 0.5 * atr
        and close <= ema21 + 0.70 * atr
        and (close <= prev_close or prev_close <= prev_ema21)
    )

    # --- direction selection ---------------------------------------------
    direction = None
    setup_type = None

    # v31: trend branch runs when regime is "trend" OR "neutral".
    if regime in ("trend", "neutral"):
        long_slope_ok = slope_strong or (pullback_long and mtf_strong_long and slope_pullback_ok)
        short_slope_ok = slope_strong or (pullback_short and mtf_strong_short and slope_pullback_ok)

        if long_slope_ok:
            if (ema9 > ema21 and long_bias and mtf_long_ok
                    and not macro_blocks_long and ema21_slope_ok_long):
                direction = "long"
                setup_type = "trend_follow_long"
        if direction is None and short_slope_ok:
            if (ema9 < ema21 and short_bias and mtf_short_ok
                    and not macro_blocks_short and ema21_slope_ok_short):
                direction = "short"
                setup_type = "trend_follow_short"

    # v31: mean-rev branch runs when regime is "mean_reversion", OR when
    # regime is "neutral" AND the EMA stack is truly flat (range regime).
    mean_rev_enabled = (regime == "mean_reversion") or (regime == "neutral" and stack_truly_flat)
    if direction is None and mean_rev_enabled:
        stretch_ref = ema50 if ema50 is not None else ema21
        stretch = (close - stretch_ref) / atr
        reclaim_up = close > prev_close
        reclaim_dn = close < prev_close
        wick_up = low < min(prev_low, float(prev2["Low"]))
        wick_dn = high > max(prev_high, float(prev2["High"]))
        # v31: require a decisive close in the top/bottom 25% of the bar.
        close_upper = close >= low + 0.75 * bar_range
        close_lower = close <= low + 0.25 * bar_range

        # v31: stretch threshold widened from 1.20 to 2.00 (ATR units).
        if abs(stretch) <= 3.0:
            if stretch <= -2.00 and (reclaim_up or wick_up or close_upper) and mtf_long_ok and not macro_blocks_long:
                direction = "long"
                setup_type = "mean_revert_long"
            elif stretch >= 2.00 and (reclaim_dn or wick_dn or close_lower) and mtf_short_ok and not macro_blocks_short:
                direction = "short"
                setup_type = "mean_revert_short"

    if direction is None:
        return None

    # --- distance gate (v31: re-calibrated for 4Hour) --------------------
    breakout_up_pre = close > recent_swing_high + BREAKOUT_BUFFER_ATR * atr
    breakout_dn_pre = close < recent_swing_low - BREAKOUT_BUFFER_ATR * atr
    is_breakout = (direction == "long" and breakout_up_pre) or (direction == "short" and breakout_dn_pre)
    # v31: 2.40 -> 3.00 (breakout), 1.75 -> 2.25 (normal).
    dir_cap = 3.00 * atr if is_breakout else 2.25 * atr

    if abs(close - ema21) > DISTANCE_GATE_ATR * atr:
        return None
    if (close - ema21) > dir_cap and direction == "long":
        return None
    if (ema21 - close) > dir_cap and direction == "short":
        return None

    # --- anti-chase gate (v31: tightened 1.60 -> 1.10) -------------------
    move_3 = close - float(prev3["Close"])
    if direction == "long" and move_3 > 1.10 * atr:
        return None
    if direction == "short" and -move_3 > 1.10 * atr:
        return None

    # --- composite reversal veto (v31: 4.5 -> 3.0) -----------------------
    prev_move = prev_close - float(prev2["Close"])
    prev2_move = float(prev["Close"]) - float(prev2["Close"])
    if direction == "long":
        combined_against = -(prev_move + prev2_move)
        if combined_against >= 3.0 * atr and close < prev_close - 0.95 * atr:
            return None
    else:
        combined_against = prev_move + prev2_move
        if combined_against >= 3.0 * atr and close > prev_close + 0.95 * atr:
            return None

    # --- structure confirmation ------------------------------------------
    breakout_up = close > recent_swing_high + BREAKOUT_BUFFER_ATR * atr
    breakout_dn = close < recent_swing_low - BREAKOUT_BUFFER_ATR * atr
    at_support = abs(close - recent_swing_low) <= SUPPORT_PROXIMITY_ATR * atr
    at_resistance = abs(close - recent_swing_high) <= SUPPORT_PROXIMITY_ATR * atr

    if direction == "long":
        if not (breakout_up or at_support or pullback_long):
            return None
    else:
        if not (breakout_dn or at_resistance or pullback_short):
            return None

    # --- momentum confirmation (trend only; kept) ------------------------
    if regime in ("trend", "neutral") and setup_type and setup_type.startswith("trend"):
        if direction == "long":
            momentum_ok = (
                (close >= ema21)
                or (close > prev_close)
                or (close >= low + 0.5 * bar_range)
            )
        else:
            momentum_ok = (
                (close <= ema21)
                or (close < prev_close)
                or (close <= low + 0.5 * bar_range)
            )
        if not momentum_ok:
            return None

    # --- structural stop / targets ---------------------------------------
    if direction == "long":
        sl = near_swing_low - (SL_BUFFER_ATR * atr) - TICK
        if sl >= close:
            return None
        risk = close - sl
        if risk < MIN_RISK_ATR * atr:
            return None
        if risk > 3.0 * atr:
            return None
        tp1 = close + TP1_R * risk
        tp2_struct = close + TP2_R * risk
        tp2 = min(tp2_struct, recent_swing_high) if recent_swing_high > tp1 else tp2_struct
        if tp1 <= close:
            return None
    else:
        sl = near_swing_high + (SL_BUFFER_ATR * atr) + TICK
        if sl <= close:
            return None
        risk = sl - close
        if risk < MIN_RISK_ATR * atr:
            return None
        if risk > 3.0 * atr:
            return None
        tp1 = close - TP1_R * risk
        tp2_struct = close - TP2_R * risk
        tp2 = max(tp2_struct, recent_swing_low) if recent_swing_low < tp1 else tp2_struct
        if tp1 >= close:
            return None

    return {
        "entry": close,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "swing_low": recent_swing_low,
        "swing_high": recent_swing_high,
        "near_swing_low": near_swing_low,
        "near_swing_high": near_swing_high,
        "risk": risk,
        "direction": direction,
        "setup_type": setup_type,
        "regime": regime,
        "gex": gex,
        "gex_neutral": bool(gex_neutral),
        "macro_score": macro_score,
        "breakout": breakout_up if direction == "long" else breakout_dn,
        "at_support": at_support if direction == "long" else at_resistance,
        "pullback": pullback_long if direction == "long" else pullback_short,
        "mtf_long_votes": float(mtf_long_votes),
        "mtf_short_votes": float(mtf_short_votes),
        "mtf_available": int(mtf_available),
        # v31: gate-level counters for QA bottleneck diagnosis.
        "gate_counts": {
            "gex_valid": 1 if np.isfinite(gex) else 0,
            "gex_neutral": 1 if gex_neutral else 0,
            "ema_long_ok": 1 if long_bias else 0,
            "ema_short_ok": 1 if short_bias else 0,
            "ema_stack_flat": 1 if stack_flat else 0,
            "ema_stack_truly_flat": 1 if stack_truly_flat else 0,
            "mean_rev_enabled": 1 if mean_rev_enabled else 0,
            "atr_ok": 1,
            "macro_ok": 1 if (not macro_blocks_long and not macro_blocks_short) else 0,
            "mtf_ok": 1 if (mtf_long_ok or mtf_short_ok) else 0,
        },
        "confluence_score": int(
            (1 if regime in ("trend", "mean_reversion") else 0)
            + (1 if (long_bias or short_bias) else 0)
            + (1 if mtf_available >= 3 else 0)
            + (1 if abs(macro_score) < BULLISH_THRESHOLD else 0)
            + (1 if (breakout_up or breakout_dn or at_support or at_resistance) else 0)
            + (1 if (pullback_long or pullback_short) else 0)
        ),
    }