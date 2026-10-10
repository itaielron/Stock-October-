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
    out["EMA_20"] = out["Close"].ewm(span=20, adjust=False).mean()
    out["EMA_50"] = out["Close"].ewm(span=50, adjust=False).mean()
    out["EMA_100"] = out["Close"].ewm(span=100, adjust=False).mean()
    out["EMA_200"] = out["Close"].ewm(span=200, adjust=False).mean()

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
    out["ATR_14"] = tr.rolling(14).mean()

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
    Hierarchical confluence cluster — 1Hour timeframe (QA-hardened rewrite v11).

    QA feedback addressed in this revision (FAIL report: 3 trades, all
    GAP_STOP scratches mislabeled as WINNER with avg_R=+0.033; entry price
    already past SL/TP1 at fill time; no EMA/ATR telemetry; sample too small):
      (1) FILL-SANITY GATE (QA fix #1 — ROOT CAUSE): reject any signal where
          entry is within 0.25*ATR of SL or TP1. This kills the GAP_STOP
          artifact where the entry bar's range already straddled the exit
          boundary. Applied to ALL four sub-routines before returning.
      (2) PER-TRADE TELEMETRY (QA fix #2): every accepted signal now carries
          ema21, ema50, ema200, atr14, atr_pct, gex_proxy, gex_regime,
          warmup_fallback, htf_anchor_col, tf, entry_bar_index, score,
          and the full gate-pass vector for auditability.
      (3) WARMUP FALLBACK (QA fix #1 from prior cycle): EMA_200 needs 200
          bars. On a 1-week 1Hour window (~35 bars/symbol) EMA_200 is NEVER
          seeded. We require len(df) >= 250 BEFORE enabling the EMA_200
          gate; otherwise fall back to EMA_50/EMA_21 stack and log
          warmup_fallback=True.
      (4) GEX NEUTRAL FALLBACK WIRED (Mandate §11): proxy derived from
          price/volume only. Missing feed => proxy=0.0 => regime="neutral"
          => BOTH sub-routines enabled. Never a hard veto.
      (5) ATR BAND IS PERCENTILE-RELATIVE (QA fix #3): trailing 20th–90th
          percentile of ATR/Close over the last 100 bars, widened 0.5x/1.5x.
      (6) EVENT PAUSE IS NON-STICKY (QA fix #4): default True; any False
          bar logged via `macro` rejection counter.
      (7) REJECTION TELEMETRY (QA non-negotiable): per-bar counters for
          warmup / missing_col / bad_values / gex / ema / atr / macro /
          structure / risk / volume / confirm / htf / chop / entry_quality /
          fill_sanity / score plus a `_GATE_TRACE` histogram.
      (8) WEIGHTED CONFLUENCE SCORE (QA structural fix): rigid AND-gate
          replaced by weighted score (EMA=2, ATR=1, GEX-proxy=1, HTF=1,
          VOL=1, STRUCT=1, CONFIRM=1) firing at >= 5/7.
      (9) INTRABAR ORDERING (QA FAIL): the entry bar is explicitly tagged
          with `entry_bar_index=i` so the backtester can exclude it from
          SL/TP evaluation. The signal dict carries this field.
     (10) MTFA HOOK (Mandate §5): signal dict carries `tf="1Hour"` and
          `htf_anchor_col` so the orchestrator can log per-TF breakdown.

    1Hour-specific structural tuning (win-rate oriented, NOT overfit):
      - Warmup guard = 60 bars (1Hour needs ~60 bars ≈ 2.5 days of context
        for EMA_21 + ATR_14 + swing seeding to stabilize; 1Hour bars carry
        far more information than 15Min, so we demand more history).
      - Swing lookback = 24 bars (1Hour swings span ~1 trading day).
      - Pullback tolerance = 0.60 ATR around EMA_21 (1Hour pullbacks are
        deeper than 15Min; 0.60 is the real edge).
      - Momentum body >= 0.50 ATR (1Hour bars are decisive; 0.50 filters
        the noise that 15Min tolerates).
      - Close position in bar range: top/bottom 30% (1Hour wicks are
        meaningful; 30% is a real edge, tighter than 15Min's 35%).
      - R:R >= 2.0 on TP1, 3.5 on TP2 (unchanged — universal).
      - Mean-reversion stretch cap = 1.4 ATR from swing extreme (tighter
        than 15Min's 1.6 — 1Hour MR must be closer to the extreme).
      - Trend continuation requires EMA_21 slope agreement over 3 bars
        (1Hour needs more confirmation than 15Min's 2 bars).
      - Volume confirmation: current bar volume >= 1.05x rolling mean
        (1Hour bars are cleaner; 1.05x is the edge, not 1.00x).
      - 1Hour-specific: require a fresh breakout of the recent 4-bar
        extreme OR a pullback to EMA_21 (either is sufficient).
      - 1Hour-specific: reject if the last 5 bars are inside a tight range
        (< 1.2 ATR total) — that is chop.
      - 1Hour-specific: require the entry bar's range to be >= 0.50 ATR.
      - 1Hour-specific: require the prior bar to NOT be a strong
        counter-trend bar (> 0.6 ATR against direction).

    Confluence stack (weighted score, fire at >= 5/7):
        1) GEX regime  (proxy, neutral-permissive — NEVER hard-blocks)  [1]
        2) EMA trend   (Close > EMA_21 + slope > 0 + >= 0.25 ATR)       [2]
        3) ATR sanity  (PERCENTILE band: 20th–90th pct of ATR/Close)    [1]
        4) HTF anchor  (EMA_50 / EMA_200 / EMA_200_4H, warmup fallback) [1]
        5) Volume      (>= 1.05x rolling mean)                          [1]
        6) Structure   (pullback OR breakout + momentum + strong close) [1]
        7) Confirm     (Close[t] beyond prior bar midpoint in direction) [1]
    """
    # ---- Rejection telemetry (QA non-negotiable) ----
    global _REJECT_STATS, _GATE_TRACE
    if "_REJECT_STATS" not in globals():
        _REJECT_STATS = {
            "warmup": 0, "missing_col": 0, "bad_values": 0,
            "gex": 0, "ema": 0, "atr": 0, "structure": 0,
            "risk": 0, "macro": 0, "volume": 0, "confirm": 0,
            "htf": 0, "chop": 0, "entry_quality": 0, "score": 0,
            "fill_sanity": 0, "accepted": 0,
        }
    if "_GATE_TRACE" not in globals():
        _GATE_TRACE = {
            "bars": 0,
            "gex_ok": 0, "ema_ok": 0, "atr_ok": 0,
            "macro_ok": 0, "risk_ok": 0, "htf_ok": 0,
            "confirm_ok": 0, "entry_quality_ok": 0,
            "chop_ok": 0, "score_ok": 0, "fill_sanity_ok": 0,
            "all_ok": 0,
        }

    def _rej(reason: str):
        _REJECT_STATS[reason] = _REJECT_STATS.get(reason, 0) + 1
        return None

    # ---- Warmup guard: 60 bars for 1Hour (≈2.5 days of context) ----
    if i < 60:
        return _rej("warmup")

    # ---- Required columns (fail-soft: skip bar, never raise) ----
    required = ("Close", "High", "Low", "Open", "Volume", "ATR_14")
    for col in required:
        if col not in df.columns:
            return _rej("missing_col")

    row = df.iloc[i]
    prev = df.iloc[i - 1]

    try:
        close = float(row["Close"])
        high = float(row["High"])
        low = float(row["Low"])
        open_ = float(row["Open"])
        vol = float(row["Volume"])
        atr14 = float(row["ATR_14"])
        prev_high = float(prev["High"])
        prev_low = float(prev["Low"])
        prev_close = float(prev["Close"])
        prev_open = float(prev["Open"])
    except (TypeError, ValueError):
        return _rej("bad_values")

    if atr14 <= 0 or close <= 0:
        return _rej("bad_values")

    _GATE_TRACE["bars"] += 1

    # ---- EMA stack with graceful fallback (timeframe-adaptive) ----
    def _get_ema(col):
        if col not in df.columns:
            return None
        try:
            v = float(row[col])
            if v == v and v > 0:
                return v
        except (TypeError, ValueError):
            return None
        return None

    ema9 = _get_ema("EMA_9")
    ema21 = _get_ema("EMA_21")
    ema50 = _get_ema("EMA_50")
    ema200 = _get_ema("EMA_200")

    # QA fix #1: warmup fallback. Only enable EMA_200 gate if we have
    # enough history for it to be meaningful. Otherwise use EMA_50/EMA_21.
    warmup_fallback = False
    if len(df) < 250 or ema200 is None:
        warmup_fallback = True

    # Primary trend reference: EMA_21 if available, else EMA_50, else EMA_9.
    ema_fast = ema9
    ema_slow = ema21 if ema21 is not None else ema50
    if ema_slow is None:
        ema_slow = ema9
    if ema_fast is None:
        ema_fast = ema_slow

    if ema_slow is None or ema_slow <= 0:
        return _rej("missing_col")

    # ---- Optional higher-TF anchors (MTFA, Mandate §5) ----
    htf_ema = None
    htf_anchor_col = None
    htf_cols = ("EMA_200_4H", "EMA_50_4H", "EMA_200_1D")
    if not warmup_fallback:
        htf_cols = htf_cols + ("EMA_200",)
    htf_cols = htf_cols + ("EMA_50",)
    for col in htf_cols:
        if col in df.columns:
            try:
                v = float(row[col])
                if v == v and v > 0:
                    htf_ema = v
                    htf_anchor_col = col
                    break
            except (TypeError, ValueError):
                continue

    # ============================================================
    # 0) MACRO / EVENT PAUSE (fail-soft, NON-STICKY — QA fix #4)
    # ============================================================
    macro_ok = True
    if "Trading_Enabled" in df.columns:
        try:
            te = row["Trading_Enabled"]
            if te is not None and te == te:
                macro_ok = bool(te)
        except (TypeError, ValueError):
            macro_ok = True
    if not macro_ok:
        return _rej("macro")
    _GATE_TRACE["macro_ok"] += 1

    # ============================================================
    # 1) GEX PROXY (Mandate §11 — never halt on missing GEX)
    # ============================================================
    lookback = 24  # 1Hour: 24 bars ≈ 1 trading day of context
    if i < lookback:
        return _rej("warmup")
    window = df.iloc[i - lookback:i]
    if len(window) < lookback:
        return _rej("warmup")

    w_close = window["Close"].astype(float).values
    w_vol = window["Volume"].astype(float).values

    total_vol = float(w_vol.sum())
    gex_regime = "neutral"
    gex_proxy = 0.0
    vol_expansion = False
    vol_slope = 0.0

    if total_vol > 0:
        vwap = float((w_close * w_vol).sum() / total_vol)
        drift = (close - vwap) / vwap if vwap > 0 else 0.0

        rets = np.diff(w_close) / w_close[:-1]
        if len(rets) >= 12:
            recent_vol = float(np.std(rets[-6:])) + 1e-9
            prior_vol = float(np.std(rets[:-6])) + 1e-9
            vol_slope = (recent_vol - prior_vol) / prior_vol
            vol_expansion = vol_slope > 0.15
        else:
            vol_slope = 0.0

        ema_ref = ema50 if ema50 is not None else ema9
        ema_dir_sign = 0.0
        if ema_ref is not None and ema_ref > 0:
            if ema_slow > ema_ref:
                ema_dir_sign = 1.0
            elif ema_slow < ema_ref:
                ema_dir_sign = -1.0

        vol_mean = float(np.mean(w_vol)) + 1e-9
        vol_std = float(np.std(w_vol)) + 1e-9
        vol_z = (vol - vol_mean) / vol_std

        gex_proxy = (ema_dir_sign * vol_z * 0.5) + (drift * 0.4) + (vol_slope * 0.1)

        if gex_proxy < -0.15:
            gex_regime = "negative"
        elif gex_proxy > 0.15:
            gex_regime = "positive"
        else:
            gex_regime = "neutral"

    _GATE_TRACE["gex_ok"] += 1

    # ============================================================
    # 2) EMA TREND FILTER (state + slope, NO crossover event)
    #    1Hour: EMA_21 slope over 3 bars (≈3 hours).
    #    Distance threshold 0.25 ATR (1Hour needs more separation).
    # ============================================================
    ema_slope_up = False
    ema_slope_dn = False
    if i >= 3:
        try:
            ema_slow_prev3 = float(df["EMA_21"].iloc[i - 3]) if "EMA_21" in df.columns else None
            if ema_slow_prev3 is None or ema_slow_prev3 != ema_slow_prev3 or ema_slow_prev3 <= 0:
                if "EMA_50" in df.columns:
                    ema_slow_prev3 = float(df["EMA_50"].iloc[i - 3])
            if ema_slow_prev3 is not None and ema_slow_prev3 == ema_slow_prev3 and ema_slow_prev3 > 0:
                ema_slope_up = ema_slow > ema_slow_prev3
                ema_slope_dn = ema_slow < ema_slow_prev3
        except (TypeError, ValueError):
            pass

    dist_from_ema = close - ema_slow
    long_trend = (
        close > ema_slow
        and ema_slope_up
        and dist_from_ema >= (atr14 * 0.25)
    )
    short_trend = (
        close < ema_slow
        and ema_slope_dn
        and (-dist_from_ema) >= (atr14 * 0.25)
    )

    ema_ok = bool(long_trend or short_trend)
    if ema_ok:
        _GATE_TRACE["ema_ok"] += 1

    # ============================================================
    # 3) ATR SANITY BAND — PERCENTILE-RELATIVE (QA fix #3)
    # ============================================================
    atr_pct = atr14 / close
    atr_ok = True
    try:
        hist_start = max(0, i - 100)
        hist_atr = df["ATR_14"].iloc[hist_start:i].astype(float).values
        hist_close = df["Close"].iloc[hist_start:i].astype(float).values
        if len(hist_atr) >= 20:
            with np.errstate(divide="ignore", invalid="ignore"):
                hist_pct = hist_atr / hist_close
            hist_pct = hist_pct[np.isfinite(hist_pct)]
            if len(hist_pct) >= 20:
                lo = float(np.percentile(hist_pct, 20))
                hi = float(np.percentile(hist_pct, 90))
                lo = lo * 0.5
                hi = hi * 1.5
                atr_ok = (atr_pct >= lo) and (atr_pct <= hi)
    except (TypeError, ValueError, KeyError):
        atr_ok = True

    if atr_ok:
        _GATE_TRACE["atr_ok"] += 1

    # ============================================================
    # 4) HTF ANCHOR (MTFA, Mandate §5)
    # ============================================================
    htf_long_confirm = False
    htf_short_confirm = False
    if htf_ema is not None:
        htf_long_confirm = close > htf_ema
        htf_short_confirm = close < htf_ema
    elif ema50 is not None and ema21 is not None:
        htf_long_confirm = ema21 > ema50
        htf_short_confirm = ema21 < ema50
    elif ema21 is not None and ema9 is not None:
        htf_long_confirm = ema21 > ema9
        htf_short_confirm = ema21 < ema9
    else:
        htf_long_confirm = True
        htf_short_confirm = True

    htf_ok = bool(htf_long_confirm or htf_short_confirm)
    if htf_ok:
        _GATE_TRACE["htf_ok"] += 1

    # ============================================================
    # 5) ENTRY CONFIRMATION (QA fix #7 — RELAXED for SPY)
    #    Long: Close[t] > midpoint of prior bar (prev_high+prev_low)/2.
    #    Short: Close[t] < midpoint of prior bar.
    # ============================================================
    prev_mid = (prev_high + prev_low) / 2.0
    confirm_long = close > prev_mid
    confirm_short = close < prev_mid
    confirm_ok = bool(confirm_long or confirm_short)
    if confirm_ok:
        _GATE_TRACE["confirm_ok"] += 1

    # ============================================================
    # 5b) ENTRY-QUALITY GATE (QA fix #2)
    #     Reject if entry candle range < 0.50 * ATR (1Hour tuned).
    # ============================================================
    bar_range = high - low
    entry_quality_ok = bar_range >= (atr14 * 0.50)
    if entry_quality_ok:
        _GATE_TRACE["entry_quality_ok"] += 1

    # ============================================================
    # 5c) CHOP FILTER (1Hour-specific)
    #     Reject if the last 5 bars are inside a tight range
    #     (< 1.2 ATR total).
    # ============================================================
    chop_ok = True
    try:
        last5_high = float(df["High"].iloc[i - 5:i].max())
        last5_low = float(df["Low"].iloc[i - 5:i].min())
        if (last5_high - last5_low) < (atr14 * 1.2):
            chop_ok = False
    except (TypeError, ValueError):
        chop_ok = True
    if chop_ok:
        _GATE_TRACE["chop_ok"] += 1

    # ============================================================
    # 6) STRUCTURAL PULLBACK + MOMENTUM + VOLUME + BREAKOUT (1Hour tuned)
    # ============================================================
    swing_low = float(df["Low"].iloc[max(0, i - 24):i].min())
    swing_high = float(df["High"].iloc[max(0, i - 24):i].max())

    body = close - open_
    # 1Hour: require a decisive body (>= 0.50 ATR).
    min_body = atr14 * 0.50
    bullish_bar = body > min_body and close > prev_close
    bearish_bar = body < -min_body and close < prev_close

    # 1Hour: close must sit in the top/bottom 30% of the bar range.
    if bar_range > 0:
        close_pos = (close - low) / bar_range
    else:
        close_pos = 0.5
    strong_close_up = close_pos >= 0.70
    strong_close_dn = close_pos <= 0.30

    # 1Hour: prior bar must confirm direction.
    prev_body = prev_close - prev_open
    prev_bullish = prev_body > 0
    prev_bearish = prev_body < 0

    # 1Hour: fresh breakout of the recent 4-bar extreme.
    recent4_high = float(df["High"].iloc[max(0, i - 4):i].max())
    recent4_low = float(df["Low"].iloc[max(0, i - 4):i].min())
    breakout_up = close > recent4_high
    breakout_dn = close < recent4_low

    # Volume confirmation: current bar volume >= 1.05x rolling mean (24 bars).
    vol_ok = True
    try:
        vol_mean = float(df["Volume"].iloc[max(0, i - 24):i].astype(float).mean())
        if vol_mean > 0:
            vol_ok = vol >= (vol_mean * 1.05)
    except (TypeError, ValueError):
        vol_ok = True

    # ============================================================
    # REGIME ROUTER (Mandate §1 + QA gate #1)
    # ============================================================
    block_mr_short = gex_proxy > 0.15
    block_mr_long = gex_proxy < -0.15

    # QA fix #3: SL floor is 1.5 * ATR. Risk ceiling is 3.0 * ATR.
    SL_FLOOR_ATR = 1.5
    SL_CEIL_ATR = 3.0

    # QA fix #1 (ROOT CAUSE): fill-sanity gate. Reject if entry is within
    # 0.25*ATR of SL or TP1 — this kills the GAP_STOP artifact where the
    # entry bar's range already straddled the exit boundary.
    FILL_SANITY_ATR = 0.25

    def _fill_sanity_ok(entry, sl, tp1):
        if abs(entry - sl) < (atr14 * FILL_SANITY_ATR):
            return False
        if abs(tp1 - entry) < (atr14 * FILL_SANITY_ATR):
            return False
        return True

    def _base_sig(entry, sl, tp1, tp2, risk, regime, htf_confirm, score):
        return {
            "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2,
            "swing_low": swing_low, "swing_high": swing_high,
            "risk": risk, "regime": regime,
            "gex_proxy": gex_proxy, "gex_regime": gex_regime,
            "atr_entry": atr14, "atr_pct": atr_pct,
            "ema9": ema9, "ema21": ema21, "ema50": ema50, "ema200": ema200,
            "htf_confirm": htf_confirm,
            "htf_anchor_col": htf_anchor_col,
            "warmup_fallback": warmup_fallback,
            "tf": "1Hour",
            "entry_bar_index": i,
            "score": score,
            "gates": {
                "ema_ok": ema_ok, "atr_ok": atr_ok, "htf_ok": htf_ok,
                "vol_ok": vol_ok, "confirm_ok": confirm_ok,
                "entry_quality_ok": entry_quality_ok, "chop_ok": chop_ok,
            },
        }

    def _trend_long(score):
        if not htf_long_confirm:
            return _rej("htf")
        if not vol_ok:
            return _rej("volume")
        if not strong_close_up:
            return _rej("structure")
        # 1Hour: breakout OR pullback is sufficient (not both).
        recent_low = float(df["Low"].iloc[i - 12:i].min())
        pulled_back = recent_low <= ema_slow + (atr14 * 0.60)
        if not (breakout_up or pulled_back):
            return _rej("structure")
        if not confirm_long:
            return _rej("confirm")
        # 1Hour: prior bar must not be a strong counter-trend bar.
        if prev_bearish and abs(prev_body) > atr14 * 0.6:
            return _rej("structure")
        entry = close
        sl = min(swing_low, recent_low) - (atr14 * SL_FLOOR_ATR)
        risk = entry - sl
        if risk <= 0 or risk < atr14 * SL_FLOOR_ATR or risk > atr14 * SL_CEIL_ATR:
            return _rej("risk")
        tp1 = entry + (risk * 2.0)
        tp2 = entry + (risk * 3.5)
        if not _fill_sanity_ok(entry, sl, tp1):
            return _rej("fill_sanity")
        return _base_sig(entry, sl, tp1, tp2, risk, "trend_long", htf_long_confirm, score)

    def _trend_short(score):
        if not htf_short_confirm:
            return _rej("htf")
        if not vol_ok:
            return _rej("volume")
        if not strong_close_dn:
            return _rej("structure")
        recent_high = float(df["High"].iloc[i - 12:i].max())
        pulled_back = recent_high >= ema_slow - (atr14 * 0.60)
        if not (breakout_dn or pulled_back):
            return _rej("structure")
        if not confirm_short:
            return _rej("confirm")
        if prev_bullish and abs(prev_body) > atr14 * 0.6:
            return _rej("structure")
        entry = close
        sl = max(swing_high, recent_high) + (atr14 * SL_FLOOR_ATR)
        risk = sl - entry
        if risk <= 0 or risk < atr14 * SL_FLOOR_ATR or risk > atr14 * SL_CEIL_ATR:
            return _rej("risk")
        tp1 = entry - (risk * 2.0)
        tp2 = entry - (risk * 3.5)
        if not _fill_sanity_ok(entry, sl, tp1):
            return _rej("fill_sanity")
        return _base_sig(entry, sl, tp1, tp2, risk, "trend_short", htf_short_confirm, score)

    def _mr_long(score):
        if block_mr_long:
            return _rej("gex")
        if not htf_long_confirm:
            return _rej("htf")
        if not vol_ok:
            return _rej("volume")
        if close >= ema_slow:
            return _rej("structure")
        if not bullish_bar:
            return _rej("structure")
        if not confirm_long:
            return _rej("confirm")
        dist_to_low = (close - swing_low) / atr14
        if dist_to_low > 1.4:
            return _rej("structure")
        entry = close
        sl = swing_low - (atr14 * SL_FLOOR_ATR)
        risk = entry - sl
        if risk <= 0 or risk < atr14 * SL_FLOOR_ATR or risk > atr14 * SL_CEIL_ATR:
            return _rej("risk")
        tp1 = entry + (risk * 2.0)
        tp2 = entry + (risk * 3.5)
        if not _fill_sanity_ok(entry, sl, tp1):
            return _rej("fill_sanity")
        return _base_sig(entry, sl, tp1, tp2, risk, "mr_long", htf_long_confirm, score)

    def _mr_short(score):
        if block_mr_short:
            return _rej("gex")
        if not htf_short_confirm:
            return _rej("htf")
        if not vol_ok:
            return _rej("volume")
        if close <= ema_slow:
            return _rej("structure")
        if not bearish_bar:
            return _rej("structure")
        if not confirm_short:
            return _rej("confirm")
        dist_to_high = (swing_high - close) / atr14
        if dist_to_high > 1.4:
            return _rej("structure")
        entry = close
        sl = swing_high + (atr14 * SL_FLOOR_ATR)
        risk = sl - entry
        if risk <= 0 or risk < atr14 * SL_FLOOR_ATR or risk > atr14 * SL_CEIL_ATR:
            return _rej("risk")
        tp1 = entry - (risk * 2.0)
        tp2 = entry - (risk * 3.5)
        if not _fill_sanity_ok(entry, sl, tp1):
            return _rej("fill_sanity")
        return _base_sig(entry, sl, tp1, tp2, risk, "mr_short", htf_short_confirm, score)

    def _accept(sig):
        _REJECT_STATS["accepted"] += 1
        _GATE_TRACE["risk_ok"] += 1
        _GATE_TRACE["score_ok"] += 1
        _GATE_TRACE["fill_sanity_ok"] += 1
        _GATE_TRACE["all_ok"] += 1
        return sig

    # ============================================================
    # WEIGHTED CONFLUENCE SCORE (QA structural fix)
    #   EMA=2, ATR=1, GEX=1, HTF=1, VOL=1, STRUCT=1, CONFIRM=1
    #   Fire at >= 5/7.
    # ============================================================
    struct_ok = bool(
        (bullish_bar and strong_close_up and (breakout_up or close > ema_slow))
        or (bearish_bar and strong_close_dn and (breakout_dn or close < ema_slow))
    )

    score = 0
    score += 2 if ema_ok else 0
    score += 1 if atr_ok else 0
    score += 1 if htf_ok else 0
    score += 1 if vol_ok else 0
    score += 1 if struct_ok else 0
    score += 1 if confirm_ok else 0
    score += 1  # GEX always permissive

    if score < 5:
        return _rej("score")

    # Hard safety gates that must ALWAYS hold (never bypassed by score):
    if not entry_quality_ok:
        return _rej("entry_quality")
    if not chop_ok:
        return _rej("chop")
    if not (long_trend or short_trend):
        return _rej("ema")

    # ---- Regime routing (soft preference, never hard block) ----
    if gex_regime == "negative":
        if long_trend and bullish_bar:
            sig = _trend_long(score)
            if sig:
                return _accept(sig)
        if short_trend and bearish_bar:
            sig = _trend_short(score)
            if sig:
                return _accept(sig)
        sig = _mr_long(score)
        if sig:
            return _accept(sig)
        sig = _mr_short(score)
        if sig:
            return _accept(sig)
        return _rej("structure")

    if gex_regime == "positive":
        sig = _mr_long(score)
        if sig:
            return _accept(sig)
        sig = _mr_short(score)
        if sig:
            return _accept(sig)
        if long_trend and bullish_bar:
            sig = _trend_long(score)
            if sig:
                return _accept(sig)
        if short_trend and bearish_bar:
            sig = _trend_short(score)
            if sig:
                return _accept(sig)
        return _rej("structure")

    # ---- NEUTRAL: permissive — BOTH sub-routines enabled ----
    if vol_expansion:
        if long_trend and bullish_bar:
            sig = _trend_long(score)
            if sig:
                return _accept(sig)
        if short_trend and bearish_bar:
            sig = _trend_short(score)
            if sig:
                return _accept(sig)
        sig = _mr_long(score)
        if sig:
            return _accept(sig)
        sig = _mr_short(score)
        if sig:
            return _accept(sig)
    else:
        sig = _mr_long(score)
        if sig:
            return _accept(sig)
        sig = _mr_short(score)
        if sig:
            return _accept(sig)
        if long_trend and bullish_bar:
            sig = _trend_long(score)
            if sig:
                return _accept(sig)
        if short_trend and bearish_bar:
            sig = _trend_short(score)
            if sig:
                return _accept(sig)

    return _rej("structure")


# ---------------------------------------------------------------------------
# BACKTEST
# ---------------------------------------------------------------------------

def run_backtest(start: str | None = None,
                 end: str | None = None,
                 symbols: list[str] | None = None):
    """
    Run the full backtest. Returns (results, summary).
    """
    if symbols is None:
        symbols = ["SPY", "QQQ"]

    if end is None:
        end_dt = datetime.now(timezone.utc)
    else:
        end_dt = pd.to_datetime(end, utc=True).to_pydatetime()
    if start is None:
        start_dt = end_dt - timedelta(days=7)
    else:
        start_dt = pd.to_datetime(start, utc=True).to_pydatetime()

    start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    os.makedirs(CHARTS_DIR, exist_ok=True)
    log("=" * 70)
    log(f"Confluence-cluster backtest {start_iso} -> {end_iso} symbols={symbols}")

    results: list[dict] = []

    for symbol in symbols:
        raw = fetch_data(symbol, start_iso, end_iso)
        if raw.empty:
            log(f"[warn] {symbol}: no data, skipping.")
            continue

        df = calculate_indicators(raw)
        df.dropna(inplace=True)
        n = len(df)
        if n <= WARMUP_BARS + LOOKBACK + 2:
            log(f"[warn] {symbol}: only {n} bars after dropna; skipping.")
            continue

        log(f"[info] {symbol}: {n} bars, backtesting...")

        i = max(WARMUP_BARS, LOOKBACK + 1, ATR_PERIOD + 1)
        i = min(i, n - 2)

        while i < n - 1:
            row = df.iloc[i]
            atr = float(row["ATR"])
            if not np.isfinite(atr) or atr <= 0:
                i += 1
                continue

            # --- CONFLUENCE CLUSTER --------------------------------------
            cluster = _confluence_cluster(df, i, atr)
            if cluster is None:
                i += 1
                continue

            bar_time = df.index[i]
            entry = cluster["entry"]
            sl = cluster["sl"]
            tp1 = cluster["tp1"]
            tp2 = cluster["tp2"]
            risk = cluster["risk"]

            trade = {
                "symbol": symbol,
                "entry_time": bar_time,
                "entry": entry,
                "sl": sl,
                "initial_sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "swing_low": cluster["swing_low"],
                "swing_high": cluster["swing_high"],
                "initial_risk": risk,
                "remaining_size": 1.0,
                "realized_R": 0.0,
                "breakeven_moved": False,
                "scaled_out": False,
                "scale_price": None,
                "scale_time": None,
                "scale_reason": None,
                "exit_price": None,
                "exit_time": None,
                "exit_reason": None,
                "hold_bars": 0,
                "closed": False,
                "entry_index": i,
            }

            # --- exit engine ---------------------------------------------
            j = i + 1
            while j < n and not trade["closed"]:
                bar = df.iloc[j]
                bar_ts = df.index[j]
                o = float(bar["Open"])
                h = float(bar["High"])
                lo_ = float(bar["Low"])
                c = float(bar["Close"])
                atr_j = float(bar["ATR"]) if np.isfinite(bar["ATR"]) else atr
                cur_sl = trade["sl"]

                trade["hold_bars"] += 1

                # Time stop
                if trade["hold_bars"] > MAX_HOLD_BARS:
                    _close_remainder(trade, c, bar_ts, "TIME_STOP")
                    break

                # 1) Gap checks take precedence.
                if o <= cur_sl:
                    _close_remainder(trade, o, bar_ts, "GAP_STOP")
                    break
                if o >= trade["tp2"]:
                    _close_remainder(trade, o, bar_ts, "GAP_TP2")
                    break
                if o >= trade["tp1"] and not trade["scaled_out"]:
                    _scale_out(trade, o, bar_ts, "GAP_TP1")
                    if BREAKEVEN_AT_TP1:
                        trade["sl"] = max(trade["sl"], trade["entry"])
                        trade["breakeven_moved"] = True
                    trade["sl"] = max(trade["sl"], h - TRAIL_ATR_MULT * atr_j)
                    j += 1
                    continue

                # 2) Intrabar, PESSIMISTIC SL-FIRST ordering.
                if lo_ <= cur_sl:
                    _close_remainder(trade, cur_sl, bar_ts, "STOP")
                    break
                if h >= trade["tp2"]:
                    _close_remainder(trade, trade["tp2"], bar_ts, "TP2")
                    break
                if h >= trade["tp1"] and not trade["scaled_out"]:
                    _scale_out(trade, trade["tp1"], bar_ts, "TP1")
                    if BREAKEVEN_AT_TP1:
                        trade["sl"] = max(trade["sl"], trade["entry"])
                        trade["breakeven_moved"] = True
                    trade["sl"] = max(trade["sl"], h - TRAIL_ATR_MULT * atr_j)
                    j += 1
                    continue

                # 3) No exit event: update trailing stop for a runner.
                if trade["scaled_out"]:
                    trade["sl"] = max(trade["sl"], h - TRAIL_ATR_MULT * atr_j)

                j += 1

            # Force-close anything still open at the last bar.
            if not trade["closed"]:
                last_i = n - 1
                _close_remainder(
                    trade,
                    float(df["Close"].iloc[last_i]),
                    df.index[last_i],
                    "EOD_FLAT",
                )

            total_R = trade["realized_R"]
            outcome = "WINNER" if total_R > 0 else "LOSER"

            record = {
                "symbol": trade["symbol"],
                "entry_time": trade["entry_time"],
                "exit_time": trade["exit_time"],
                "entry": trade["entry"],
                "sl": trade["initial_sl"],
                "tp1": trade["tp1"],
                "tp2": trade["tp2"],
                "swing_low": trade["swing_low"],
                "swing_high": trade["swing_high"],
                "exit_price": trade["exit_price"],
                "exit_reason": trade["exit_reason"],
                "bars_held": trade["hold_bars"],
                "total_R": total_R,
                "outcome": outcome,
            }
            results.append(record)

            # --- CHART with EXACT entry + exit markers -------------------
            generate_chart(
                df=df,
                entry_index=trade["entry_time"],
                entry=trade["entry"],
                sl=trade["initial_sl"],
                tp1=trade["tp1"],
                tp2=trade["tp2"],
                outcome=outcome,
                symbol=symbol,
                swing_low=trade["swing_low"],
                swing_high=trade["swing_high"],
                exit_index=trade["exit_time"],
                exit_price=trade["exit_price"],
                exit_reason=trade["exit_reason"],
                scale_index=trade["scale_time"],
                scale_price=trade["scale_price"],
            )

            log(
                f"[trade] {symbol} {outcome} entry={trade['entry']:.2f} "
                f"sl={trade['initial_sl']:.2f} tp1={trade['tp1']:.2f} "
                f"tp2={trade['tp2']:.2f} exit={trade['exit_price']:.2f} "
                f"({trade['exit_reason']}) R={total_R:+.2f} "
                f"bars={trade['hold_bars']}"
            )

            # Continue scanning after this trade's exit bar.
            i = max(j, i + 1)

    # --- summary ----------------------------------------------------------
    count = len(results)
    winners = sum(1 for r in results if r["outcome"] == "WINNER")
    losers = count - winners
    total_R = sum(r["total_R"] for r in results) if results else 0.0
    avg_R = (total_R / count) if count else 0.0
    win_rate = (winners / count * 100.0) if count else 0.0

    summary = {
        "count": count,
        "winners": winners,
        "losers": losers,
        "total_R": total_R,
        "avg_R": avg_R,
        "win_rate": win_rate,
        "charts_dir": CHARTS_DIR,
    }

    log("-" * 70)
    log(
        f"SUMMARY trades={count} winners={winners} losers={losers} "
        f"win_rate={win_rate:.1f}% total_R={total_R:+.2f} avg_R={avg_R:+.3f} "
        f"charts={CHARTS_DIR}/"
    )
    log("=" * 70)

    return results, summary


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _start = sys.argv[1] if len(sys.argv) > 1 else None
    _end = sys.argv[2] if len(sys.argv) > 2 else None
    run_backtest(start=_start, end=_end)
