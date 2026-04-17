"""
One-time migration: SQLite celebrities.db → PostgreSQL

Usage:
    python migrate_sqlite.py --sqlite /path/to/celebrities.db
    DATABASE_URL=postgresql://... python migrate_sqlite.py --sqlite /path/to/celebrities.db
"""

import argparse
import os
import sqlite3
import sys

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://networth:networth@localhost:5432/networth"
)

DDL = """
CREATE TABLE IF NOT EXISTS celebrities (
    id                SERIAL PRIMARY KEY,
    name              TEXT NOT NULL,
    net_worth         BIGINT,
    net_worth_display TEXT,
    url               TEXT UNIQUE NOT NULL,
    category          TEXT,
    photo_url         TEXT,
    scraped_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_name      ON celebrities (name);
CREATE INDEX IF NOT EXISTS idx_net_worth ON celebrities (net_worth);
CREATE INDEX IF NOT EXISTS idx_category  ON celebrities (category);
"""


def migrate(sqlite_path: str):
    print(f"Source SQLite : {sqlite_path}")
    print(f"Target Postgres: {DATABASE_URL.split('@')[-1]}")

    # Read from SQLite
    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    rows = src.execute(
        "SELECT name, net_worth, net_worth_display, url, category, photo_url FROM celebrities"
    ).fetchall()
    src.close()
    print(f"Read {len(rows):,} rows from SQLite")

    # Connect to PostgreSQL
    dst = psycopg2.connect(DATABASE_URL)
    cur = dst.cursor()

    # Create schema
    cur.execute(DDL)
    dst.commit()
    print("Schema ready")

    # Bulk insert (upsert on url)
    batch = [
        (r["name"], r["net_worth"], r["net_worth_display"], r["url"], r["category"], r["photo_url"])
        for r in rows
    ]

    psycopg2.extras.execute_values(
        cur,
        """INSERT INTO celebrities (name, net_worth, net_worth_display, url, category, photo_url)
           VALUES %s
           ON CONFLICT (url) DO UPDATE SET
               net_worth         = EXCLUDED.net_worth,
               net_worth_display = EXCLUDED.net_worth_display,
               photo_url         = EXCLUDED.photo_url""",
        batch,
        page_size=500
    )
    dst.commit()

    cur.execute("SELECT COUNT(*) FROM celebrities")
    total = cur.fetchone()[0]
    print(f"Done! {total:,} celebrities in PostgreSQL.")
    cur.close()
    dst.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", default="/Users/roy.fi/net_worth_scraper/celebrities.db")
    args = parser.parse_args()
    migrate(args.sqlite)
