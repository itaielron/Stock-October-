import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "hub_v2.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # price_history
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS price_history (
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
        source       TEXT          NOT NULL,
        captured_at  TEXT          NOT NULL
    );
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS ix_ph_route ON price_history (origin, destination, depart_date, captured_at DESC);')

    # signals
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS signals (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        channel     TEXT          NOT NULL,
        msg_id      TEXT,
        text        TEXT          NOT NULL,
        url         TEXT,
        posted_at   TEXT,
        captured_at TEXT          NOT NULL,
        matched_routes TEXT,
        UNIQUE (channel, msg_id)
    );
    ''')

    # deals
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS deals (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        route       TEXT          NOT NULL,
        depart_date TEXT          NOT NULL,
        fare_total  REAL          NOT NULL,
        median_30d  REAL,
        z_score     REAL,
        pct_drop    REAL,
        confirmed   BOOLEAN       NOT NULL DEFAULT 0,
        sources     TEXT,
        signal_ids  TEXT,
        flagged_at  TEXT          NOT NULL,
        UNIQUE (route, depart_date, fare_total)
    );
    ''')
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database schema initialized successfully.")
