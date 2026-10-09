Project: TLV Deal Hunter (tlv-deal-hunter) Owner: you Contract version: 1.2 Purpose of this file: single source of truth for any agent (human, DeepSeek, Antigravity, Cursor, Claude Code) building this project. If code and this file disagree, this file wins until it's updated deliberately.

1. Product in one sentence
A daily-run system that watches TLV -> Europe + US East Coast flight prices from multiple sources, stores its own price history, flags anomalous deals, and alerts to a private Telegram channel.

Explicitly out of scope: booking, payment, seat selection, visa logic, multi-city, award tickets.

2. Target scope
Origin: TLV (Tel Aviv Ben Gurion)

Destinations - Europe (20): LHR, CDG, AMS, FRA, MUC, MAD, BCN, FCO, MXP, ATH, IST, VIE, ZRH, BER, LIS, PRG, WAW, BUD, OTP, KEF

Destinations - US East Coast (7): JFK, EWR, BOS, IAD, PHL, MIA, ATL

Trip shape (v1): one-way only. Round-trip is v1.1.

Cabin: economy only (v1). Business is v1.1.

Currency stored: USD. Display currency configurable later.

3. Architecture (fixed - do not redesign without updating this file)
┌──────────────────────────────────────────────────────────────┐
│ Scheduler (GitHub Actions or local cron, daily 03:00 UTC)   │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────┐   ┌──────────────────────────────┐
│ collectors/             │──▶│  SOURCES (see §4)            │
│ - ff_collector.py       │   │  - fast-flights (truth)      │
│ - fli_collector.py      │   │  - fli scraper (Google)      │
│ - telegram_listener.py  │   │  - Telegram channels (signal) │
│ - site_scraper.py       │   │  - Fly4Free IL, Secret Flying │
└──────────┬──────────────┘   └──────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│ SQLite (hub_v2.db)                                           │
│ - price_history  (facts)                                     │
│ - signals        (raw text from Telegram/sites)              │
│ - deals          (flagged anomalies)                         │
└──────────┬───────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────┐
│ analyzer/detector.py    │  z-score + pct threshold + signal
│                         │  crossover → deals
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ notifier/telegram_bot.py│  → your private channel
└─────────────────────────┘
Rule: collectors write to DB. Analyzer reads DB, writes deals. Notifier reads deals. No collector calls another collector. No notifier touches collectors. One-way data flow.

4. Sources of truth vs sources of signal
Layer   Source  Role    Free-tier budget
Truth   fast-flights    Primary query for real bookable prices      $0
Truth (backup)  fli (Google Scraper)    Second opinion on price $0, unstructured
Signal  Telegram channels (Passport Card, Secret Flights IL, others)    Earliest notice of a deal       $0 (bot API)
Signal  fly4free.co.il  Curated IL deals, articles      $0
Signal  secretflying.com (IL section)   Global deals filtered to IL     $0
Rule: a deal is only alerted if confirmed by at least one truth source. A signal-only hit is stored but flagged unconfirmed.

5. Database schema (canonical - SQLite v1.1)
-- Facts: one row per price observation
CREATE TABLE price_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    origin       TEXT          NOT NULL,
    destination  TEXT          NOT NULL,
    depart_date  TEXT          NOT NULL,
    return_date  TEXT,
    fare_total   REAL          NOT NULL,
    base_fare    REAL,
    taxes        REAL,
    currency     TEXT          NOT NULL DEFAULT 'USD',
    carrier      TEXT,
    stops        INTEGER,
    bag_included BOOLEAN,
    bag_price    REAL,
    source       TEXT          NOT NULL,   -- 'amadeus' | 'fli'
    captured_at  TEXT          NOT NULL
);
CREATE INDEX ix_ph_route ON price_history (origin, destination, depart_date, captured_at DESC);

-- Raw signals from Telegram / sites
CREATE TABLE signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    channel     TEXT          NOT NULL,    -- '@passportcard' | 'fly4free' | ...
    msg_id      TEXT,                     -- platform-native id, for dedupe
    text        TEXT          NOT NULL,
    url         TEXT,
    posted_at   TEXT,
    captured_at TEXT          NOT NULL,
    matched_routes TEXT,                  -- JSON string: '["TLV-LHR","TLV-CDG"]'
    UNIQUE (channel, msg_id)
);

-- Flagged anomalies
CREATE TABLE deals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    route       TEXT          NOT NULL,    -- 'TLV-LHR'
    depart_date TEXT          NOT NULL,
    fare_total  REAL          NOT NULL,
    median_30d  REAL,
    z_score     REAL,
    pct_drop    REAL,
    confirmed   BOOLEAN       NOT NULL DEFAULT 0,
    sources     TEXT,                      -- JSON string: '["amadeus","fli"]'
    signal_ids  TEXT,                      -- JSON string of IDs
    flagged_at  TEXT          NOT NULL,
    UNIQUE (route, depart_date, fare_total)
);
Migration rule: never DROP or rename columns in place. Add new, backfill, deprecate, delete in a later release.

6. Module contracts
Each module exposes a narrow, stable interface. Agents may rewrite internals; do not change these signatures without bumping the spec version.

collectors/ff_collector.py
def run(destinations: list[str]) -> int:
    """Fetch prices for the given destinations, insert into price_history.
    Returns number of rows inserted. Honors quota budget in §7."""
collectors/fli_collector.py
def run(destinations: list[str], days_ahead: int = 45) -> int:
    """Fetch prices via fli, insert into price_history with source='fli'.
    Returns rows inserted."""
collectors/telegram_listener.py
async def run_forever(channels: list[str]) -> None:
    """Telethon-based. Subscribes to channels, inserts new messages into
    signals. Never blocks other collectors - runs as separate process."""
collectors/site_scraper.py
def run() -> int:
    """Scrape Fly4Free IL and Secret Flying IL. Insert new articles into
    signals. Idempotent on (channel, msg_id)."""
analyzer/detector.py
def flag_deals() -> list[dict]:
    """Read price_history + signals, compute anomalies per §8,
    upsert into deals, return newly flagged deals (for notifier).
    Must be idempotent on (route, depart_date, fare_total)."""
notifier/telegram_bot.py
def send(deal: dict) -> bool:
    """Send a single deal to configured output channel.
    Returns True on success. Must not raise on failure - log and return False."""
Rule: modules do not import each other's internals. Only the public functions above.

7. Quota & rate-limit budget (Amadeus is the scarce resource)
Hard ceiling: 1,800 Amadeus calls/month (leave 200 for manual testing).
Daily allowance: 60 calls.
Strategy - rotation, not exhaustive:
Every day, pick 10 destinations from the 27-destination pool, rotating deterministically by day-of-year so every destination is visited ~every 3 days.
For each chosen destination: 1 cheapest_dates call for next month (returns full price matrix), then 3 offers_one_date calls on the 3 cheapest days.
= 4 calls × 10 destinations = 40 calls/day -> ~1,200/mo. Headroom for retries.
Retries: max 2, exponential backoff, count against daily budget.
On hitting daily budget: stop cleanly, log, exit 0. Do not silently drop.
fli calls: unlimited technically (no quota), but throttle to 1 req / 2 s to stay polite. Cap at 300 routes/day.
Telegram: only listens, never sends to anyone but your own channel.
8. Deal detection logic (canonical)
For each (origin, destination, depart_date) with >= 5 observations in the last 30 days:

median_30d = median(fare_total) over window
sd_30d     = population stdev over window
latest     = most recent fare_total
z          = (latest - median_30d) / sd_30d
pct        = (latest - median_30d) / median_30d * 100
Flag as a deal if either:

z <= -1.5 (statistical outlier), or
pct <= -20 (meaningful absolute drop)
Additionally, a signals row that mentions a matching route in the last 24h:

sets confirmed = FALSE if only signal,
sets confirmed = TRUE if a truth source (amadeus or fli) is within ±10% of the signal-described price.
Do not alert on confirmed = FALSE unless explicitly opted in via config.

9. Configuration surface
All tunables live in config/config.yaml:

origin: TLV
destinations:
  europe: [LHR, CDG, AMS, FRA, MUC, MAD, BCN, FCO, MXP, ATH, IST, VIE, ZRH, BER, LIS, PRG, WAW, BUD, OTP, KEF]
  us_east: [JFK, EWR, BOS, IAD, PHL, MIA, ATL]

amadeus:
  monthly_call_budget: 1800
  daily_call_budget: 60
  destinations_per_day: 10
  days_per_destination: 3

fli:
  days_ahead: 45
  max_routes_per_day: 300
  throttle_seconds: 2

detection:
  window_days: 30
  min_samples: 5
  z_threshold: -1.5
  pct_threshold: -20

notify:
  telegram_channel: "@your_private_channel"
  alert_unconfirmed: false
  max_alerts_per_day: 20
Rule: no magic numbers in code. Everything above is the source of defaults.

10. Environment variables (secrets - never in config.yaml)
AMADEUS_CLIENT_ID
AMADEUS_CLIENT_SECRET
DATABASE_URL
TELEGRAM_API_ID
TELEGRAM_API_HASH
TELEGRAM_BOT_TOKEN
TELEGRAM_CHANNELS       # comma-separated, e.g. "@passportcard,@secretflights_il"
11. Build order - vertical slices
Each slice must run end-to-end before the next begins. Do not build horizontally.

Slice 1 - "One flight, one row" ✅ gate
db.py creates schema.
collectors/fli_collector.py fetches TLV->LHR for one date, inserts one row.
Verify with SELECT * FROM price_history LIMIT 1;.
Acceptance: a row exists with source='fli' and a sane price.
Slice 2 - "Amadeus truth" ✅ gate
collectors/ff_collector.py fetches the same route+date, inserts with source='amadeus'.
Acceptance: two sources agree within 30%.
Slice 3 - "Rotation, not flood" ✅ gate
Amadeus collector implements the §7 rotation strategy over all 27 destinations.
Acceptance: running twice on consecutive days visits different destinations; daily call count <= 60.
Slice 4 - "Detector fires" ✅ gate
analyzer/detector.py implemented per §8.
Seed with 10 fake rows to force a flag.
Acceptance: a synthetic 30% drop produces a deals row.
Slice 5 - "Alerts" ✅ gate
notifier/telegram_bot.py sends a flagged deal to your private channel.
Acceptance: message arrives within 5s of send().
Slice 6 - "Signals" ✅ gate
collectors/telegram_listener.py reads one Israeli channel, inserts messages.
Acceptance: running for 1 hour yields >= 1 row in signals with a route mention.
Slice 7 - "Signal + truth merge" ✅ gate
Detector cross-references signals and sets confirmed.
Acceptance: a fake signal + fake truth observation produces confirmed=TRUE.
Slice 8 - "Second truth source" ✅ gate
fast-flights added as cross-check when fli and amadeus disagree by >30%.
Slice 9 - "Dashboard" (optional)
FastAPI /deals and /chart/{route} views.
Only Slice 1-3 are required for v1 to be considered "usable". Everything after is value-add.

12. Non-goals (explicitly)
No automated booking.
No payment handling.
No scraping of airline sites directly (Israir/El Al) in v1 - that's v1.1.
No Facebook scraping (ToS-hostile, brittle).
No machine-learning price prediction. z-score only.
No multi-user. Single operator (you).
13. Anti-patterns - reject these in review
❌ Collectors writing to deals directly.
❌ Notifier computing thresholds.
❌ Any module calling requests.get on a source not listed in §4.
❌ Storing secrets in config.yaml.
❌ New tables without a migration note in §5.
❌ New external dependency without a section in §4 with a free-tier budget.
❌ Bypassing the rotation strategy in §7 - even "just for testing" (test against fake data, not live quota).
❌ Adding "smart" heuristics before §11 slices prove the plain version works.
14. Definition of done (project level)
cron.sh runs daily for 7 consecutive days without manual intervention.
price_history contains >= 3,000 rows spanning >= 20 destinations.
At least one real deals row has fired confirmed=TRUE from two sources.
Your private Telegram channel received an alert you acted on (or would have).
SPEC.md reflects reality - update it if reality changed.
15. Handoff note for any downstream agent
You are building against a fixed contract. If something in this file is wrong or impossible against a real API, stop and report - do not silently deviate. Silent deviation is the number-one failure mode of multi-agent builds.

Priorities, in order:

Working vertical slices (Slice 1 -> Slice 3) beat a broken full system.
Quota discipline (§7) beats completeness.
Signal + truth confirmation (§4, §8) beats raw sensitivity.
Readable, boring code beats clever code.
End of SPEC v1.0.
