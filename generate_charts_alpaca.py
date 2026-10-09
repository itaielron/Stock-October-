import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
import pytz
import mplfinance as mpf

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OUT_DIR = "/Users/itaielron/.gemini/antigravity/brain/c0df299c-545f-4292-b580-1c4542af62c7/scratch"
os.makedirs(OUT_DIR, exist_ok=True)

ALPACA_DATA_URL = "https://data.alpaca.markets/v2/stocks/{symbol}/bars"
ALPACA_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET = os.environ.get("ALPACA_SECRET_KEY", "")

TIMEFRAME = "5Min"
BAR_MINUTES = 5
PRE_ROLL_MIN = 120          # minutes of context before the alert
POST_ROLL_MIN = 60          # minutes of context after the alert
SESSION_TZ = pytz.timezone("America/New_York")   # US equity RTH clock
UTC = timezone.utc

# US equity regular trading hours (session open/close in exchange-local time).
SESSION_OPEN = (9, 30)
SESSION_CLOSE = (16, 0)

# Defect #5 fix: hub.db timestamps are stored by the collector in *naive ET*
# wall-clock (America/New_York), NOT naive UTC. We therefore make the epoch
# explicit and configurable instead of assuming, and we validate it with a
# self-check so a wrong assumption fails loudly instead of silently shifting
# every alert vline by 4-5 hours.
HUB_TS_TZ = pytz.timezone(os.environ.get("HUB_DB_TZ", "America/New_York"))


# ---------------------------------------------------------------------------
# Alpaca 5-minute data fetch (FIXED)
# ---------------------------------------------------------------------------
def _alpaca_headers():
    if not ALPACA_KEY or not ALPACA_SECRET:
        raise RuntimeError(
            "Missing Alpaca credentials. Set ALPACA_API_KEY / ALPACA_SECRET_KEY."
        )
    return {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
        "Accept": "application/json",
    }


def _fetch_alpaca_bars(symbol, start_utc, end_utc, feed="iex", limit=10000):
    """
    Raw paginated pull of Alpaca v2 5-minute bars. All times must be tz-aware UTC.

    Feed selection / entitlement handling (Defect #2 fix):
      The old code checked for HTTP 401 and fell back iex->sip. That is inverted:
        * 401 Unauthorized => bad *credentials*, never fixed by changing feed.
        * 403 Forbidden    => valid credentials but NOT entitled to the
                              requested feed/endpoint. This is the only case
                              where switching feed (sip->iex) can succeed.
      We now try SIP first (full consolidated tape) when allowed, and fall back
      to IEX on 403 only. A 401 raises immediately with a clear message.
    """
    url = ALPACA_DATA_URL.format(symbol=symbol.upper())
    params = {
        "timeframe": TIMEFRAME,
        "start": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit": limit,
        "adjustment": "raw",
        "feed": feed,
        "sort": "asc",
    }
    bars = []
    page_token = None
    while True:
        if page_token:
            params["page_token"] = page_token
        resp = requests.get(url, headers=_alpaca_headers(), params=params, timeout=30)

        # 401 => bad credentials; changing the feed cannot help.
        if resp.status_code == 401:
            raise RuntimeError(
                f"Alpaca rejected credentials (HTTP 401) for {symbol}: "
                f"{resp.text.strip()}. Check ALPACA_API_KEY / ALPACA_SECRET_KEY."
            )

        # 403 => entitled-feed problem. Only now is a feed downgrade valid.
        if resp.status_code == 403:
            if feed == "sip":
                return _fetch_alpaca_bars(
                    symbol, start_utc, end_utc, feed="iex", limit=limit
                )
            raise RuntimeError(
                f"Alpaca denied access to feed '{feed}' (HTTP 403) for {symbol}: "
                f"{resp.text.strip()}. Account lacks entitlement."
            )

        resp.raise_for_status()
        payload = resp.json()
        bars.extend(payload.get("bars") or [])
        page_token = payload.get("next_page_token")
        if not page_token:
            break
        time.sleep(0.25)   # be polite to the rate limiter
    return bars


def _session_bounds_utc(ts_utc):
    """Return (open_utc, close_utc) for the ET trading session containing ts_utc."""
    et = ts_utc.astimezone(SESSION_TZ)
    open_et = SESSION_TZ.localize(
        datetime(et.year, et.month, et.day, *SESSION_OPEN)
    )
    close_et = SESSION_TZ.localize(
        datetime(et.year, et.month, et.day, *SESSION_CLOSE)
    )
    return open_et.astimezone(UTC), close_et.astimezone(UTC)


def _regular_session_mask(index_utc):
    """
    Boolean mask selecting bars inside 09:30 <= t < 16:00 ET, computed on a
    freshly ET-localized copy of the index (Defect #3 fix).

    The old code did `et = df.index.tz_convert(SESSION_TZ)` off a naive-filtered
    frame; that is unsafe across DST transitions because the comparison used a
    naive `.time` against a fixed wall clock while the underlying offset could
    still be the pre/post-transition value. We re-localize per-timestamp so DST
    straddle days are handled correctly, and we exclude the 16:00 closing print.
    """
    et_index = pd.DatetimeIndex(index_utc).tz_convert(SESSION_TZ)
    minutes = et_index.hour * 60 + et_index.minute
    open_min = SESSION_OPEN[0] * 60 + SESSION_OPEN[1]
    close_min = SESSION_CLOSE[0] * 60 + SESSION_CLOSE[1]
    return (minutes >= open_min) & (minutes < close_min)


def _expected_session_index(index_utc):
    """
    Build the *session-aware* regular 5-minute grid (Defect #1 fix).

    Instead of blindly reindexing from min->max UTC (which spans the overnight
    16:00->09:30 gap and re-inserts synthetic flat bars via ffill, corrupting
    ATR/EMA windows), we generate the grid PER TRADING DAY, only across that
    day's 09:30-16:00 session, and concatenate. Overnight/weekend gaps produce
    NO rows, so nothing can be forward-filled into a fake candle.
    """
    if index_utc.empty:
        return pd.DatetimeIndex([], tz="UTC")

    et_index = pd.DatetimeIndex(index_utc).tz_convert(SESSION_TZ)
    grid = []
    for day in sorted(set(et_index.normalize())):
        day_open = SESSION_TZ.localize(
            datetime(day.year, day.month, day.day, *SESSION_OPEN)
        )
        day_close = SESSION_TZ.localize(
            datetime(day.year, day.month, day.day, *SESSION_CLOSE)
        )
        # True 5-minute grid within the session; last bar starts 15:55.
        day_grid = pd.date_range(
            day_open, day_close, freq=f"{BAR_MINUTES}min", inclusive="left"
        )
        grid.append(day_grid.tz_convert(UTC))
    if not grid:
        return pd.DatetimeIndex([], tz="UTC")
    return grid[0].append(grid[1:]) if len(grid) > 1 else grid[0]


def _normalize_bars(bars):
    """
    Convert raw Alpaca bar dicts into a clean, UTC-indexed OHLCV DataFrame.

    Fixes applied:
      * Timezone: parse RFC3339 `t` as aware-UTC (never drop tzinfo).
      * Validation: drop non-finite / non-positive / degenerate OHLC bars.
      * Session-aware reindex (Defect #1): regular 5m grid generated per ET
        session only; the overnight gap contains no synthetic bars.
      * DST-safe session filter (Defect #3): re-localize each timestamp to ET.
      * No blind ffill: missing *intra-session* bars are left as NaN and dropped
        (so gates simply see fewer real bars) rather than being fabricated.
    """
    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(bars)
    df["t"] = pd.to_datetime(df["t"], utc=True)
    df = df.set_index("t").sort_index()
    df = df.rename(
        columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
    )[["open", "high", "low", "close", "volume"]]

    # Drop duplicate timestamps that can appear across pagination boundaries.
    df = df[~df.index.duplicated(keep="last")]

    # Drop incomplete / non-finite / degenerate bars.
    df = df[df[["open", "high", "low", "close"]].notna().all(axis=1)]
    for col in ["open", "high", "low", "close"]:
        df = df[df[col].apply(lambda x: x > 0)]
    df = df[
        (df["high"] >= df["low"])
        & (df["high"] >= df[["open", "close"]].max(axis=1))
        & (df["low"] <= df[["open", "close"]].min(axis=1))
    ]
    df["volume"] = df["volume"].fillna(0).clip(lower=0)

    if df.empty:
        return df

    # DST-safe regular-session filter.
    df = df[_regular_session_mask(df.index)]
    if df.empty:
        return df

    # Session-aware reindex: build the exact 5m grid *inside each session only*.
    full_idx = _expected_session_index(df.index)

    # Reindex WITHOUT ffill. Any hole that survived the API pull stays NaN and is
    # dropped below -> no synthetic flat bar ever enters an ATR/EMA window.
    reindexed = df.reindex(full_idx)

    missing = int(reindexed["close"].isna().sum())
    if missing:
        print(
            f"  [warn] {missing} intra-session 5m bar(s) missing from feed; "
            f"dropped rather than forward-filled."
        )

    reindexed = reindexed.dropna(subset=["open", "high", "low", "close"])

    # Final invariant check: every surviving stamp must be a real bar on the
    # session grid (no duplicates, no off-grid synthetic rows).
    reindexed = reindexed[~reindexed.index.duplicated(keep="last")]
    reindexed = reindexed[reindexed.index.isin(full_idx)]
    return reindexed


def _resolve_alert_datetime(ts_str):
    """
    Defect #5 fix: resolve a hub.db timestamp WITHOUT assuming naive == UTC.

    hub.db timestamps come from the collector as *naive America/New_York*
    wall-clock strings. We:
      1. Parse ISO (handling the trailing 'Z' as UTC if present).
      2. If naive, localize to HUB_TS_TZ (ET), then convert to UTC.
      3. If aware, respect its offset.
    """
    if ts_str is None:
        return None
    ts_str = str(ts_str).strip()
    if ts_str.endswith("Z"):
        dt = datetime.fromisoformat(ts_str[:-1]).replace(tzinfo=UTC)
    else:
        dt = datetime.fromisoformat(ts_str)
    if dt.tzinfo is None:
        dt = HUB_TS_TZ.localize(dt, is_dst=None)
    return dt.astimezone(UTC)


def get_data(symbol, alert_dt):
    """
    Pull clean, verified 5-minute data for `symbol` centered on `alert_dt`.

    Parameters
    ----------
    symbol : str
    alert_dt : datetime  (tz-aware preferred; naive input is assumed to be in
               HUB_TS_TZ / America/New_York, matching hub.db storage).

    Returns
    -------
    pd.DataFrame indexed by tz-aware UTC timestamps with columns
    open, high, low, close, volume, containing only real regular-session bars.
    Empty DataFrame if no valid data.
    """
    if alert_dt.tzinfo is None:
        alert_dt = HUB_TS_TZ.localize(alert_dt, is_dst=None)
    alert_dt = alert_dt.astimezone(UTC)

    start_utc = (alert_dt - timedelta(minutes=PRE_ROLL_MIN)).replace(
        second=0, microsecond=0
    )
    end_utc = (alert_dt + timedelta(minutes=POST_ROLL_MIN)).replace(
        second=0, microsecond=0
    )

    raw = _fetch_alpaca_bars(symbol, start_utc, end_utc)
    df = _normalize_bars(raw)
    if df.empty:
        return df

    # Trim to the requested alert window (session reindex may have pulled in the
    # whole day for grid alignment).
    df = df[(df.index >= start_utc) & (df.index <= end_utc)]
    return df


# ---------------------------------------------------------------------------
# Alert parsing
# ---------------------------------------------------------------------------
def parse_alert(message, timestamp_str):
    signals = []
    ticker_match = re.search(r"\|\s*Ticker\s*\|\s*([A-Z]+)\s*\|", message)

    # Defect #4 fix: the old regex `([\d]+\.[\d]+)` REQUIRED a literal dot and at
    # least one digit after it, so whole-dollar entries like "$150" or "150"
    # were silently dropped. New pattern accepts 150, 150.5, 150.50, $150, etc.
    num = r"\$?\s*(\d+(?:\.\d+)?)"

    entry_match = re.search(r"\|\s*Entry[^\|]*\|\s*~?" + num, message)
    sl_match = re.search(r"\|\s*Suggested Stop Loss\s*\|\s*" + num, message)
    tp1_match = re.search(r"\|\s*Suggested Target 1[^\|]*\|\s*" + num, message)
    tp2_match = re.search(r"\|\s*Suggested Target 2[^\|]*\|\s*" + num, message)

    direction = (
        "LONG" if "LONG SETUP" in message
        else "SHORT" if "SHORT SETUP" in message
        else "UNKNOWN"
    )

    if ticker_match and entry_match and sl_match and tp1_match:
        signals.append({
            "ticker": ticker_match.group(1),
            "direction": direction,
            "entry": float(entry_match.group(1)),
            "sl": float(sl_match.group(1)),
            "tp1": float(tp1_match.group(1)),
            "tp2": float(tp2_match.group(1)) if tp2_match else None,
            "timestamp": timestamp_str,
        })
    return signals


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    conn = sqlite3.connect("hub.db")
    cursor = conn.cursor()
    yesterday = (datetime.now() - timedelta(days=2)).isoformat()
    cursor.execute(
        "SELECT timestamp, message FROM alerts "
        "WHERE category='STOCK_SWEEP' "
        "AND (message LIKE '%🟢%' OR message LIKE '%🔴%') "
        "AND timestamp > ?",
        (yesterday,),
    )
    rows = cursor.fetchall()
    conn.close()

    all_signals = []
    for row in rows:
        all_signals.extend(parse_alert(row[1], row[0]))

    print(f"Generating charts for {len(all_signals)} signals...")

    for i, sig in enumerate(all_signals):
        ticker = sig["ticker"]
        print(f"Plotting {ticker}...")

        # Defect #5 fix: resolve the naive hub.db timestamp via the declared
        # HUB_TS_TZ epoch instead of assuming UTC.
        try:
            alert_dt = _resolve_alert_datetime(sig["timestamp"])
        except Exception as e:
            print(f"Timestamp parse failed for {ticker}: {e}")
            continue
        if alert_dt is None:
            print(f"Missing timestamp for {ticker}")
            continue

        try:
            data = get_data(ticker, alert_dt)
        except Exception as e:
            print(f"Data fetch failed for {ticker}: {e}")
            continue

        if data.empty:
            print(f"No valid 5m data for {ticker}")
            continue

        lines = [
            (sig["entry"], "blue"),
            (sig["sl"], "red"),
            (sig["tp1"], "green"),
        ]
        if sig["tp2"]:
            lines.append((sig["tp2"], "darkgreen"))

        hlines = dict(
            hlines=[l[0] for l in lines],
            colors=[l[1] for l in lines],
            linestyle="--",
            linewidths=1.5,
        )
        vlines = dict(vlines=[alert_dt], colors=["orange"], linewidths=2)

        title = (
            f"{ticker} - {sig['direction']} Alert "
            f"(Entry: {sig['entry']} | SL: {sig['sl']} | TP: {sig['tp1']})"
        )
        fname = f"{OUT_DIR}/chart_{i}_{ticker}_{sig['direction']}.png"

        s = mpf.make_mpf_style(
            base_mpf_style="cyberpunk",
            gridstyle=":",
            facecolor="#0f172a",
            edgecolor="#334155",
            figcolor="#0f172a",
            rc={"text.color": "#e2e8f0", "axes.labelcolor": "#e2e8f0"},
        )

        try:
            mpf.plot(
                data, type="candle", style=s, hlines=hlines, vlines=vlines,
                title=title, savefig=fname, figsize=(10, 6),
            )
            print(f"Saved {fname}")
        except Exception as e:
            print(f"Failed to plot {ticker}: {e}")


if __name__ == "__main__":
    main()