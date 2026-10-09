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
    Hierarchical confluence cluster — 15Min timeframe.

    Mandate §11: GEX/options data is NOT available from Alpaca IEX. We derive a
    *mock* GEX proxy strictly from price/volume so the engine NEVER halts.
    When the proxy is degenerate/absent we fall back to `gex_regime = "neutral"`,
    and neutral MUST permit BOTH sub-routines (trend AND mean-reversion).

    QA fixes carried forward (plumbing — non-negotiable):
      - GEX gate can NEVER deadlock: proxy degenerate -> "neutral" -> both
        sub-routines enabled. No `raise`, no hard block on missing data.
      - EMA warm-up: EMA_200 used only when actually seeded (non-NaN, >0);
        otherwise fall back to EMA_50 vs EMA_20, then EMA_50 slope. Never
        silently drop the bar for a missing long-term reference.
      - ATR band: RELATIVE bounds (ATR/Close between 0.3% and 3%) — no
        absolute dollar band that silently rejects low-vol weeks.
      - Macro/event pause defaults to Trading_Enabled = True (no calendar
        feed -> never block). Checked fail-soft.
      - Per-bar gate trace: `_GATE_TRACE` records gex_ok | ema_ok | atr_ok |
        macro_ok | risk_ok booleans plus per-gate pass counts.
      - Rejection-reason telemetry retained (`_REJECT_STATS`).

    15Min-specific structural tuning (win-rate oriented, not overfit):
      - Warmup guard = 40 bars (15Min bars are 3x denser than 5Min; 40 bars
        ≈ 10 hours of context — enough for EMA_50/20 + ATR_14 + swing seeding
        on a 1-week window without eating the whole sample).
      - Swing lookback = 16 bars (15Min swings span ~4 hours).
      - Pullback tolerance = 0.6 ATR around EMA_50 (15Min noise is larger
        than 5Min; too tight a tolerance starves the trend sub-routine).
      - Momentum body >= 0.30 ATR (15Min bars carry more signal; require a
        decisive body to filter chop).
      - R:R >= 2.0 on TP1, 3.5 on TP2 (15Min moves are larger than 5Min;
        demand more edge per trade to lift win rate).
      - Mean-reversion stretch cap = 1.2 ATR from swing extreme (15Min
        mean-reversion needs a genuine stretch, but 15Min swings are wider).
      - Trend continuation requires EMA_50 slope agreement over 4 bars
        (15Min slope over 3 bars is too noisy).
      - ADX-style regime fallback: when GEX proxy is neutral, use realized
        vol expansion (recent vs prior) to route trend vs mean-revert.
      - Volume confirmation: require current bar volume >= 1.1x rolling mean
        (15Min bars are less noisy; demand above-average participation).
      - Higher-timeframe agreement: require EMA_50 vs EMA_200 alignment
        when EMA_200 is available (15Min benefits from the slower anchor).
      - HTF trend anchor: when EMA_200 is unavailable, require EMA_50 vs
        EMA_20 alignment AND EMA_50 slope agreement (double confirmation).

    Confluence stack (all must agree):
        1) GEX regime  (proxy, neutral-permissive)
        2) EMA trend   (Close > EMA_50 > EMA_200, or EMA_50 > EMA_20 fallback)
        3) ATR sanity  (RELATIVE band: 0.3% <= ATR/Close <= 3%)
        4) Structural pullback + momentum confirmation + volume
    """
    # ---- Rejection telemetry (QA non-negotiable) ----
    global _REJECT_STATS, _GATE_TRACE
    if "_REJECT_STATS" not in globals():
        _REJECT_STATS = {
            "warmup": 0, "missing_col": 0, "bad_values": 0,
            "gex": 0, "ema": 0, "atr": 0, "structure": 0,
            "risk": 0, "macro": 0, "volume": 0, "accepted": 0,
        }
    if "_GATE_TRACE" not in globals():
        _GATE_TRACE = {
            "bars": 0,
            "gex_ok": 0, "ema_ok": 0, "atr_ok": 0,
            "macro_ok": 0, "risk_ok": 0,
            "all_ok": 0,
        }

    def _rej(reason: str):
        _REJECT_STATS[reason] = _REJECT_STATS.get(reason, 0) + 1
        return None

    # ---- Warmup guard: 40 bars for 15Min (≈10h context) ----
    if i < 40:
        return _rej("warmup")

    # ---- Required columns (fail-soft: skip bar, never raise) ----
    required = ("Close", "High", "Low", "Open", "Volume", "EMA_50", "ATR_14")
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
        ema50 = float(row["EMA_50"])
        atr14 = float(row["ATR_14"])
    except (TypeError, ValueError):
        return _rej("bad_values")

    if atr14 <= 0 or close <= 0 or ema50 <= 0:
        return _rej("bad_values")

    _GATE_TRACE["bars"] += 1

    # ---- EMA_200 with graceful fallback (QA fix #2) ----
    ema200 = None
    if "EMA_200" in df.columns:
        try:
            v = float(row["EMA_200"])
            if v == v and v > 0:  # not NaN, positive
                ema200 = v
        except (TypeError, ValueError):
            ema200 = None

    ema20 = None
    if "EMA_20" in df.columns:
        try:
            v = float(row["EMA_20"])
            if v == v and v > 0:
                ema20 = v
        except (TypeError, ValueError):
            ema20 = None

    # ============================================================
    # 0) MACRO / EVENT PAUSE (QA fix #4)
    #    Default Trading_Enabled = True. No calendar feed -> never block.
    # ============================================================
    macro_ok = True
    if "Trading_Enabled" in df.columns:
        try:
            te = row["Trading_Enabled"]
            if te is not None and te == te:  # not NaN
                macro_ok = bool(te)
        except (TypeError, ValueError):
            macro_ok = True
    if not macro_ok:
        return _rej("macro")
    _GATE_TRACE["macro_ok"] += 1

    # ============================================================
    # 1) GEX PROXY (Mandate §11 — never halt on missing GEX)
    #    Fallback: gex_regime = "neutral" when proxy is degenerate.
    #    Neutral routes via realized-vol expansion (ADX-style proxy).
    # ============================================================
    lookback = 20  # 15Min: 20 bars ≈ 5h of context for the proxy
    if i < lookback:
        return _rej("warmup")
    window = df.iloc[i - lookback:i]
    if len(window) < lookback:
        return _rej("warmup")

    w_close = window["Close"].astype(float).values
    w_vol = window["Volume"].astype(float).values
    w_high = window["High"].astype(float).values
    w_low = window["Low"].astype(float).values

    total_vol = float(w_vol.sum())
    gex_regime = "neutral"
    gex_proxy = 0.0
    vol_expansion = False  # ADX-style trend proxy for neutral regime

    if total_vol > 0:
        vwap = float((w_close * w_vol).sum() / total_vol)
        drift = (close - vwap) / vwap if vwap > 0 else 0.0

        rets = np.diff(w_close) / w_close[:-1]
        if len(rets) >= 14:
            recent_vol = float(np.std(rets[-6:])) + 1e-9
            prior_vol = float(np.std(rets[:-6])) + 1e-9
            vol_slope = (recent_vol - prior_vol) / prior_vol
            # ADX-style: expanding realized vol => trending regime.
            vol_expansion = vol_slope > 0.18
        else:
            vol_slope = 0.0

        rng = float(np.mean(w_high - w_low)) + 1e-9
        last_rng = float(high - low) + 1e-9
        range_ratio = last_rng / rng

        gex_proxy = (drift * 0.6) + (vol_slope * 0.3) - ((range_ratio - 1.0) * 0.1)

        # Neutral band widened: near-zero proxy => neutral (permissive).
        if gex_proxy < -0.0015:
            gex_regime = "negative"
        elif gex_proxy > 0.0015:
            gex_regime = "positive"
        else:
            gex_regime = "neutral"

    # GEX gate is ALWAYS satisfied (neutral is permissive). Trace it.
    _GATE_TRACE["gex_ok"] += 1

    # ============================================================
    # 2) EMA TREND FILTER (Mandate §1 — directional bias)
    #    Fallback: if EMA_200 unavailable, use EMA_50 > EMA_20.
    # ============================================================
    if ema200 is not None:
        long_trend = (close > ema50) and (ema50 > ema200)
        short_trend = (close < ema50) and (ema50 < ema200)
    elif ema20 is not None:
        long_trend = (close > ema50) and (ema50 > ema20)
        short_trend = (close < ema50) and (ema50 < ema20)
    else:
        # No long-term reference at all — use slope of EMA_50 vs 12 bars ago.
        if i >= 12:
            try:
                ema50_prev = float(df["EMA_50"].iloc[i - 12])
                long_trend = (close > ema50) and (ema50 > ema50_prev)
                short_trend = (close < ema50) and (ema50 < ema50_prev)
            except (TypeError, ValueError):
                return _rej("ema")
        else:
            return _rej("ema")

    if not (long_trend or short_trend):
        return _rej("ema")
    _GATE_TRACE["ema_ok"] += 1

    # ============================================================
    # 3) ATR SANITY BAND — RELATIVE (QA fix #3)
    #    ATR/Close must be within [0.3%, 3%]. No absolute dollar band.
    # ============================================================
    atr_pct = atr14 / close
    if atr_pct < 0.003 or atr_pct > 0.03:
        return _rej("atr")
    _GATE_TRACE["atr_ok"] += 1

    # ============================================================
    # 4) STRUCTURAL PULLBACK + MOMENTUM + VOLUME (15Min tuned)
    # ============================================================
    swing_low = float(df["Low"].iloc[max(0, i - 16):i].min())
    swing_high = float(df["High"].iloc[max(0, i - 16):i].max())

    body = close - open_
    # 15Min: require a decisive body (>= 0.30 ATR) to filter chop.
    min_body = atr14 * 0.30
    bullish_bar = body > min_body and close > float(prev["Close"])
    bearish_bar = body < -min_body and close < float(prev["Close"])

    # Volume confirmation: current bar volume >= 1.1x rolling mean (20 bars).
    vol_ok = True
    try:
        vol_mean = float(df["Volume"].iloc[max(0, i - 20):i].astype(float).mean())
        if vol_mean > 0:
            vol_ok = vol >= (vol_mean * 1.1)
    except (TypeError, ValueError):
        vol_ok = True

    # EMA_50 slope over 4 bars — 15Min trend continuation confirmation.
    ema50_slope_up = False
    ema50_slope_dn = False
    if i >= 4:
        try:
            ema50_prev4 = float(df["EMA_50"].iloc[i - 4])
            if ema50_prev4 == ema50_prev4 and ema50_prev4 > 0:
                ema50_slope_up = ema50 > ema50_prev4
                ema50_slope_dn = ema50 < ema50_prev4
        except (TypeError, ValueError):
            pass

    # ============================================================
    # REGIME ROUTER (Mandate §1)
    #   negative -> trend-following
    #   positive -> mean-reversion
    #   neutral  -> permissive: BOTH sub-routines enabled (QA fix #4)
    #               routed by realized-vol expansion (ADX-style proxy)
    # ============================================================

    def _trend_long():
        if not vol_ok:
            return _rej("volume")
        recent_low = float(df["Low"].iloc[i - 6:i].min())
        # 15Min: allow pullback within 0.6 ATR of EMA_50.
        pulled_back = recent_low <= ema50 + (atr14 * 0.6)
        if not pulled_back:
            return _rej("structure")
        # 15Min continuation: EMA_50 must be rising (or flat-but-not-falling).
        if not ema50_slope_up and ema50_slope_dn:
            return _rej("structure")
        entry = close
        sl = min(swing_low, recent_low) - (atr14 * 1.5)
        risk = entry - sl
        if risk <= 0 or risk > atr14 * 3.0:
            return _rej("risk")
        return {
            "entry": entry, "sl": sl,
            "tp1": entry + (risk * 2.0), "tp2": entry + (risk * 3.5),
            "swing_low": swing_low, "swing_high": swing_high,
            "risk": risk, "regime": "trend_long", "gex_proxy": gex_proxy,
        }

    def _trend_short():
        if not vol_ok:
            return _rej("volume")
        recent_high = float(df["High"].iloc[i - 6:i].max())
        pulled_back = recent_high >= ema50 - (atr14 * 0.6)
        if not pulled_back:
            return _rej("structure")
        if not ema50_slope_dn and ema50_slope_up:
            return _rej("structure")
        entry = close
        sl = max(swing_high, recent_high) + (atr14 * 1.5)
        risk = sl - entry
        if risk <= 0 or risk > atr14 * 3.0:
            return _rej("risk")
        return {
            "entry": entry, "sl": sl,
            "tp1": entry - (risk * 2.0), "tp2": entry - (risk * 3.5),
            "swing_low": swing_low, "swing_high": swing_high,
            "risk": risk, "regime": "trend_short", "gex_proxy": gex_proxy,
        }

    def _mr_long():
        if not vol_ok:
            return _rej("volume")
        # 15Min mean-reversion: require close below EMA_50 (stretched down).
        if close >= ema50:
            return _rej("structure")
        if not bullish_bar:
            return _rej("structure")
        dist_to_low = (close - swing_low) / atr14
        if dist_to_low > 1.2:
            return _rej("structure")
        entry = close
        sl = swing_low - (atr14 * 1.5)
        risk = entry - sl
        if risk <= 0 or risk > atr14 * 3.0:
            return _rej("risk")
        return {
            "entry": entry, "sl": sl,
            "tp1": entry + (risk * 2.0), "tp2": entry + (risk * 3.5),
            "swing_low": swing_low, "swing_high": swing_high,
            "risk": risk, "regime": "mr_long", "gex_proxy": gex_proxy,
        }

    def _mr_short():
        if not vol_ok:
            return _rej("volume")
        if close <= ema50:
            return _rej("structure")
        if not bearish_bar:
            return _rej("structure")
        dist_to_high = (swing_high - close) / atr14
        if dist_to_high > 1.2:
            return _rej("structure")
        entry = close
        sl = swing_high + (atr14 * 1.5)
        risk = sl - entry
        if risk <= 0 or risk > atr14 * 3.0:
            return _rej("risk")
        return {
            "entry": entry, "sl": sl,
            "tp1": entry - (risk * 2.0), "tp2": entry - (risk * 3.5),
            "swing_low": swing_low, "swing_high": swing_high,
            "risk": risk, "regime": "mr_short", "gex_proxy": gex_proxy,
        }

    def _accept(sig):
        _REJECT_STATS["accepted"] += 1
        _GATE_TRACE["risk_ok"] += 1
        _GATE_TRACE["all_ok"] += 1
        return sig

    # ---- Regime routing ----
    if gex_regime == "negative":
        # Trend-following regime
        if long_trend and bullish_bar:
            sig = _trend_long()
            if sig:
                return _accept(sig)
        if short_trend and bearish_bar:
            sig = _trend_short()
            if sig:
                return _accept(sig)
        return _rej("gex")

    if gex_regime == "positive":
        # Mean-reversion regime
        sig = _mr_long()
        if sig:
            return _accept(sig)
        sig = _mr_short()
        if sig:
            return _accept(sig)
        return _rej("gex")

    # ---- NEUTRAL: permissive — BOTH sub-routines enabled (QA fix #4) ----
    # Route by realized-vol expansion (ADX-style proxy): expanding vol =>
    # trend-following; contracting vol => mean-reversion. This gives the
    # neutral regime a structural bias instead of blind "try everything".
    if vol_expansion:
        if long_trend and bullish_bar:
            sig = _trend_long()
            if sig:
                return _accept(sig)
        if short_trend and bearish_bar:
            sig = _trend_short()
            if sig:
                return _accept(sig)
        # Fall through to mean-reversion if trend structure not present.
        sig = _mr_long()
        if sig:
            return _accept(sig)
        sig = _mr_short()
        if sig:
            return _accept(sig)
    else:
        # Contracting vol => mean-reversion first, then trend fallback.
        sig = _mr_long()
        if sig:
            return _accept(sig)
        sig = _mr_short()
        if sig:
            return _accept(sig)
        if long_trend and bullish_bar:
            sig = _trend_long()
            if sig:
                return _accept(sig)
        if short_trend and bearish_bar:
            sig = _trend_short()
            if sig:
                return _accept(sig)

    # Neutral regime exhausted both sub-routines — classify by dominant gate.
    if not (long_trend or short_trend):
        return _rej("ema")
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
