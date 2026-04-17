"""
Net Worth Game API
FastAPI server for the WikiHover "Rank the Rich" game.
Uses PostgreSQL for persistent celebrity data.

Env vars:
  DATABASE_URL  postgresql://user:pass@host:5432/dbname
"""

import asyncio
import os
import random
import time
import uuid
import threading
from contextlib import asynccontextmanager

import httpx
import psycopg2
import psycopg2.pool
import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# DB connection pool
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://networth:networth@localhost:5432/networth"
)

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(2, 20, DATABASE_URL)
    return _pool


def db_query(sql: str, params=(), fetchall=True):
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if fetchall else cur.fetchone()
    finally:
        pool.putconn(conn)


def db_execute(sql: str, params=()):
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    finally:
        pool.putconn(conn)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    get_pool()   # warm up connection pool
    yield
    if _pool:
        _pool.closeall()


app = FastAPI(title="Net Worth Game API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Category config
# ---------------------------------------------------------------------------

CATEGORY_META = {
    "actors":               {"label": "Actors",         "emoji": "🎬", "min_nw": 20_000_000},
    "singers":              {"label": "Singers",         "emoji": "🎤", "min_nw": 10_000_000},
    "rappers":              {"label": "Rappers",         "emoji": "🎵", "min_nw": 10_000_000},
    "rock-stars":           {"label": "Rock Stars",      "emoji": "🎸", "min_nw": 10_000_000},
    "djs":                  {"label": "DJs",             "emoji": "🎧", "min_nw": 5_000_000},
    "comedians":            {"label": "Comedians",       "emoji": "😂", "min_nw": 5_000_000},
    "richest-comedians":    {"label": "Comedians",       "emoji": "😂", "min_nw": 5_000_000},
    "models":               {"label": "Models",          "emoji": "💃", "min_nw": 5_000_000},
    "directors":            {"label": "Directors",       "emoji": "🎥", "min_nw": 10_000_000},
    "nba":                  {"label": "NBA Players",     "emoji": "🏀", "min_nw": 5_000_000},
    "nfl":                  {"label": "NFL Players",     "emoji": "🏈", "min_nw": 5_000_000},
    "soccer":               {"label": "Soccer Players",  "emoji": "⚽", "min_nw": 5_000_000},
    "boxers":               {"label": "Boxers",          "emoji": "🥊", "min_nw": 5_000_000},
    "tennis":               {"label": "Tennis Players",  "emoji": "🎾", "min_nw": 5_000_000},
    "richest-billionaires": {"label": "Billionaires",    "emoji": "💰", "min_nw": 1_000_000_000},
    "ceos":                 {"label": "CEOs",            "emoji": "👔", "min_nw": 100_000_000},
    "authors":              {"label": "Authors",         "emoji": "📚", "min_nw": 5_000_000},
    "producers":            {"label": "Producers",       "emoji": "🎬", "min_nw": 10_000_000},
}

# ---------------------------------------------------------------------------
# In-memory challenge store
# ---------------------------------------------------------------------------

_challenges: dict[str, dict] = {}
_challenges_lock = threading.Lock()
CHALLENGE_TTL = 600


def _evict_challenges():
    now = time.time()
    with _challenges_lock:
        stale = [k for k, v in _challenges.items() if now - v["created_at"] > CHALLENGE_TTL]
        for k in stale:
            del _challenges[k]


# ---------------------------------------------------------------------------
# Wikipedia photo fetch
# ---------------------------------------------------------------------------

async def _fetch_wiki_photo(name: str) -> str | None:
    try:
        slug = name.replace(" ", "_")
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}"
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(url, headers={"User-Agent": "NetWorthGame/1.0"})
            if r.status_code == 200:
                data = r.json()
                thumb = data.get("thumbnail") or data.get("originalimage")
                if thumb:
                    return thumb.get("source")
    except Exception:
        pass
    return None


async def _get_photo(celeb_id: int, name: str) -> str | None:
    row = db_query("SELECT photo_url FROM celebrities WHERE id=%s", (celeb_id,), fetchall=False)
    if row and row[0]:
        return row[0]
    photo = await _fetch_wiki_photo(name)
    if photo:
        db_execute("UPDATE celebrities SET photo_url=%s WHERE id=%s", (photo, celeb_id))
    return photo


def _initials(name: str) -> str:
    parts = (name or "").strip().split()
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


# ---------------------------------------------------------------------------
# Game endpoints
# ---------------------------------------------------------------------------

@app.get("/api/game/challenge")
async def game_challenge(entity: str = Query("", description="Hovered celebrity name")):
    _evict_challenges()

    # Find category from entity
    category = None
    if entity:
        row = db_query(
            "SELECT category FROM celebrities WHERE name ILIKE %s LIMIT 1",
            (f"%{entity}%",), fetchall=False
        )
        if row:
            category = row[0]

    # Fallback to most-populated known category
    if not category or category not in CATEGORY_META:
        known = list(CATEGORY_META.keys())
        row = db_query(
            f"SELECT category, COUNT(*) as cnt FROM celebrities "
            f"WHERE category = ANY(%s) "
            f"GROUP BY category ORDER BY cnt DESC LIMIT 1",
            (known,), fetchall=False
        )
        category = row[0] if row else "actors"

    meta = CATEGORY_META.get(category, {"label": category.title(), "emoji": "⭐", "min_nw": 1_000_000})

    # Pick 5 from top 200 famous celebs in category
    rows = db_query(
        """SELECT id, name, net_worth, net_worth_display
           FROM celebrities
           WHERE category=%s AND net_worth >= %s AND net_worth IS NOT NULL
           ORDER BY net_worth DESC LIMIT 200""",
        (category, meta["min_nw"])
    )

    if len(rows) < 5:
        rows = db_query(
            """SELECT id, name, net_worth, net_worth_display
               FROM celebrities
               WHERE category=%s AND net_worth IS NOT NULL
               ORDER BY net_worth DESC LIMIT 100""",
            (category,)
        )

    if len(rows) < 5:
        return JSONResponse({"error": f"Not enough data for '{category}'"}, status_code=404)

    picked = random.sample(rows, 5)

    # Fetch photos async
    photos = await asyncio.gather(*[_get_photo(r[0], r[1]) for r in picked])

    # Correct ranking
    sorted_by_nw = sorted(enumerate(picked), key=lambda x: x[1][2], reverse=True)
    correct_ranking = {picked[i][0]: rank + 1 for rank, (i, _) in enumerate(sorted_by_nw)}

    # Shuffle for display
    order = list(range(5))
    random.shuffle(order)

    celebrities = []
    for idx in order:
        r = picked[idx]
        celebrities.append({
            "id": r[0],
            "name": r[1],
            "photo_url": photos[idx],
            "initials": _initials(r[1]),
        })

    challenge_id = str(uuid.uuid4())
    with _challenges_lock:
        _challenges[challenge_id] = {
            "celebrities": {r[0]: {"name": r[1], "net_worth": r[2], "net_worth_display": r[3]} for r in picked},
            "correct_ranking": correct_ranking,
            "created_at": time.time(),
        }

    return {
        "challenge_id": challenge_id,
        "category": category,
        "category_label": meta["label"],
        "category_emoji": meta["emoji"],
        "celebrities": celebrities,
    }


@app.post("/api/game/submit")
async def game_submit(body: dict):
    challenge_id = body.get("challenge_id", "")
    user_ranking: list[int] = body.get("ranking", [])

    with _challenges_lock:
        challenge = _challenges.get(challenge_id)

    if not challenge:
        return JSONResponse({"error": "Challenge expired or not found"}, status_code=404)

    correct = challenge["correct_ranking"]
    celebs = challenge["celebrities"]

    score = 0
    results = []
    for user_pos, celeb_id in enumerate(user_ranking, 1):
        cor = correct.get(celeb_id, 0)
        is_correct = (user_pos == cor)
        if is_correct:
            score += 1
        c = celebs.get(celeb_id, {})
        results.append({
            "id": celeb_id,
            "name": c.get("name", ""),
            "net_worth_display": c.get("net_worth_display", ""),
            "net_worth": c.get("net_worth", 0),
            "correct_rank": cor,
            "your_rank": user_pos,
            "correct": is_correct,
        })

    results.sort(key=lambda x: x["correct_rank"])
    return {"score": score, "max_score": 5, "perfect": score == 5, "results": results}


# ---------------------------------------------------------------------------
# Search + Stats (useful for admin)
# ---------------------------------------------------------------------------

@app.get("/api/search")
async def search(
    q: str = Query(""),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    sort: str = Query("net_worth"),
    order: str = Query("desc"),
):
    safe_sort = sort if sort in ("net_worth", "name", "scraped_at") else "net_worth"
    safe_order = "ASC" if order == "asc" else "DESC"
    like = f"%{q}%"

    rows = db_query(
        f"""SELECT name, net_worth, net_worth_display, category, url
            FROM celebrities WHERE name ILIKE %s
            ORDER BY {safe_sort} {safe_order} NULLS LAST
            LIMIT %s OFFSET %s""",
        (like, limit, offset)
    )
    total = db_query("SELECT COUNT(*) FROM celebrities WHERE name ILIKE %s", (like,), fetchall=False)[0]

    return {
        "total": total,
        "results": [
            {"name": r[0], "net_worth": r[1], "net_worth_display": r[2], "category": r[3], "url": r[4]}
            for r in rows
        ],
    }


@app.get("/api/stats")
async def stats():
    total = db_query("SELECT COUNT(*) FROM celebrities", fetchall=False)[0]
    cats = db_query(
        "SELECT category, COUNT(*) as cnt FROM celebrities GROUP BY category ORDER BY cnt DESC LIMIT 15"
    )
    top = db_query(
        "SELECT name, net_worth_display, net_worth FROM celebrities ORDER BY net_worth DESC NULLS LAST LIMIT 5"
    )
    return {
        "total": total,
        "categories": [{"category": r[0], "cnt": r[1]} for r in cats],
        "top_richest": [{"name": r[0], "net_worth_display": r[1], "net_worth": r[2]} for r in top],
    }


@app.get("/health")
async def health():
    try:
        db_query("SELECT 1", fetchall=False)
        return {"status": "ok"}
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8001, reload=True)