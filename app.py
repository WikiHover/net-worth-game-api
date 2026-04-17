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
    "actors":               {"label": "Actors",          "emoji": "🎬", "min_nw": 100_000_000},
    "singers":              {"label": "Singers",         "emoji": "🎤", "min_nw": 100_000_000},
    "rappers":              {"label": "Rappers",         "emoji": "🎵", "min_nw": 50_000_000},
    "richest-rappers":      {"label": "Rappers",         "emoji": "🎵", "min_nw": 50_000_000},
    "rock-stars":           {"label": "Rock Stars",      "emoji": "🎸", "min_nw": 50_000_000},
    "djs":                  {"label": "DJs",             "emoji": "🎧", "min_nw": 30_000_000},
    "richest-djs":          {"label": "DJs",             "emoji": "🎧", "min_nw": 30_000_000},
    "comedians":            {"label": "Comedians",       "emoji": "😂", "min_nw": 30_000_000},
    "richest-comedians":    {"label": "Comedians",       "emoji": "😂", "min_nw": 30_000_000},
    "models":               {"label": "Models",          "emoji": "💃", "min_nw": 20_000_000},
    "directors":            {"label": "Directors",       "emoji": "🎥", "min_nw": 50_000_000},
    "producers":            {"label": "Producers",       "emoji": "🎬", "min_nw": 50_000_000},
    "authors":              {"label": "Authors",         "emoji": "📚", "min_nw": 30_000_000},
    "nba":                  {"label": "NBA Players",     "emoji": "🏀", "min_nw": 40_000_000},
    "nfl":                  {"label": "NFL Players",     "emoji": "🏈", "min_nw": 40_000_000},
    "soccer":               {"label": "Soccer Players",  "emoji": "⚽", "min_nw": 40_000_000},
    "richest-soccer":       {"label": "Soccer Players",  "emoji": "⚽", "min_nw": 40_000_000},
    "boxers":               {"label": "Boxers",          "emoji": "🥊", "min_nw": 30_000_000},
    "richest-boxers":       {"label": "Boxers",          "emoji": "🥊", "min_nw": 30_000_000},
    "tennis":               {"label": "Tennis Players",  "emoji": "🎾", "min_nw": 30_000_000},
    "richest-tennis":       {"label": "Tennis Players",  "emoji": "🎾", "min_nw": 30_000_000},
    "richest-billionaires": {"label": "Billionaires",    "emoji": "💰", "min_nw": 1_000_000_000},
    "ceos":                 {"label": "CEOs",            "emoji": "👔", "min_nw": 500_000_000},
    "business-executives":  {"label": "Business",        "emoji": "💼", "min_nw": 100_000_000},
    "richest-businessmen":  {"label": "Business",        "emoji": "💼", "min_nw": 100_000_000},
    "wall-street":          {"label": "Wall Street",     "emoji": "📈", "min_nw": 100_000_000},
    "richest-celebrities":  {"label": "Celebrities",     "emoji": "⭐", "min_nw": 100_000_000},
    "richest-baseball":     {"label": "Baseball Players","emoji": "⚾", "min_nw": 30_000_000},
    "richest-golfers":      {"label": "Golfers",         "emoji": "⛳", "min_nw": 30_000_000},
    "hockey":               {"label": "Hockey Players",  "emoji": "🏒", "min_nw": 20_000_000},
    "race-car-drivers":     {"label": "Race Car Drivers","emoji": "🏎️", "min_nw": 30_000_000},
    "olympians":            {"label": "Olympians",       "emoji": "🏅", "min_nw": 20_000_000},
    "wrestlers":            {"label": "Wrestlers",       "emoji": "💪", "min_nw": 20_000_000},
    "mma-net-worth":        {"label": "MMA Fighters",   "emoji": "🥋", "min_nw": 20_000_000},
    "richest-coaches":      {"label": "Coaches",         "emoji": "📋", "min_nw": 20_000_000},
    "richest-designers":    {"label": "Designers",       "emoji": "✏️", "min_nw": 50_000_000},
    "republicans":          {"label": "Politicians",     "emoji": "🏛️", "min_nw": 50_000_000},
    "democrats":            {"label": "Politicians",     "emoji": "🏛️", "min_nw": 50_000_000},
    "presidents":           {"label": "Presidents",      "emoji": "🏛️", "min_nw": 10_000_000},
    "richest-athletes":     {"label": "Athletes",        "emoji": "🏆", "min_nw": 50_000_000},
    "richest-celebrity-chefs": {"label": "Celebrity Chefs", "emoji": "👨‍🍳", "min_nw": 20_000_000},
    "lawyers":              {"label": "Lawyers",         "emoji": "⚖️", "min_nw": 30_000_000},
    "royals":               {"label": "Royals",          "emoji": "👑", "min_nw": 50_000_000},
}

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
    """
    Returns 5 celebrities: the hovered entity + 2 close in net worth + 2 from top 20.
    Also returns 3 recommendations for "play next".
    """
    # Find entity and category
    category = None
    entity_row = None
    entity_nw = 0
    if entity:
        # Prefer exact match, then partial
        erow = db_query(
            "SELECT id, name, net_worth, net_worth_display, category FROM celebrities WHERE LOWER(name) = LOWER(%s) LIMIT 1",
            (entity,), fetchall=False
        )
        if not erow:
            erow = db_query(
                "SELECT id, name, net_worth, net_worth_display, category FROM celebrities WHERE name ILIKE %s ORDER BY LENGTH(name) ASC LIMIT 1",
                (f"%{entity}%",), fetchall=False
            )
        if erow:
            category = erow[4]
            entity_row = erow[:4]
            entity_nw = erow[2] or 0

    # Fallback to most-populated known category
    if not category or category not in CATEGORY_META:
        known = list(CATEGORY_META.keys())
        row = db_query(
            "SELECT category FROM celebrities WHERE category = ANY(%s) "
            "GROUP BY category ORDER BY COUNT(*) DESC LIMIT 1",
            (known,), fetchall=False
        )
        category = row[0] if row else "actors"

    meta = CATEGORY_META.get(category, {"label": category.title(), "emoji": "⭐", "min_nw": 1_000_000})

    # ── Get top 20 (famous pool) ──
    top_rows = db_query(
        """SELECT id, name, net_worth, net_worth_display
           FROM celebrities
           WHERE category=%s AND net_worth >= %s AND net_worth IS NOT NULL
           ORDER BY net_worth DESC LIMIT 20""",
        (category, meta["min_nw"])
    )

    # ── Get ~10 neighbors close in net worth to the entity ──
    neighbors = []
    if entity_row and entity_nw:
        neighbors = db_query(
            """SELECT id, name, net_worth, net_worth_display
               FROM celebrities
               WHERE category=%s AND net_worth IS NOT NULL AND id != %s
               ORDER BY ABS(net_worth - %s) ASC LIMIT 10""",
            (category, entity_row[0], entity_nw)
        )

    # Fallback if not enough data
    if len(top_rows) < 5 and not neighbors:
        top_rows = db_query(
            """SELECT id, name, net_worth, net_worth_display
               FROM celebrities WHERE category=%s AND net_worth IS NOT NULL
               ORDER BY net_worth DESC LIMIT 50""",
            (category,)
        )

    if len(top_rows) < 3 and len(neighbors) < 2:
        return JSONResponse({"error": f"Not enough data for '{category}'"}, status_code=404)

    # ── Build the 5 picks ──
    picked_ids = set()
    picked = []

    # 1) The hovered entity
    if entity_row:
        picked.append(entity_row)
        picked_ids.add(entity_row[0])

    # 2) Pick 2 from neighbors (close net worth → harder to guess)
    neighbor_pool = [r for r in neighbors if r[0] not in picked_ids]
    random.shuffle(neighbor_pool)
    for r in neighbor_pool[:2]:
        picked.append(r)
        picked_ids.add(r[0])

    # 3) Fill remaining from top 20 (famous, easy to recognize)
    top_pool = [r for r in top_rows if r[0] not in picked_ids]
    random.shuffle(top_pool)
    remaining = 5 - len(picked)
    for r in top_pool[:remaining]:
        picked.append(r)
        picked_ids.add(r[0])

    # If still not 5, fill from whatever is available
    if len(picked) < 5:
        all_pool = [r for r in (top_rows + neighbors) if r[0] not in picked_ids]
        random.shuffle(all_pool)
        for r in all_pool[:5 - len(picked)]:
            picked.append(r)
            picked_ids.add(r[0])

    if len(picked) < 5:
        return JSONResponse({"error": f"Not enough data for '{category}'"}, status_code=404)

    # Fetch Wikipedia photos
    photos = await asyncio.gather(*[_get_photo(r[0], r[1]) for r in picked])

    # Shuffle for display
    order = list(range(5))
    random.shuffle(order)

    celebrities = [
        {
            "id":               picked[i][0],
            "name":             picked[i][1],
            "net_worth":        picked[i][2],
            "net_worth_display": picked[i][3],
            "photo_url":        photos[i],
            "initials":         _initials(picked[i][1]),
        }
        for i in order
    ]

    # ── Recommendations: 3 people to play next ──
    recommendations = []

    # 1) Same category — someone not in this game
    same_cat = db_query(
        """SELECT id, name, net_worth_display, photo_url, category
           FROM celebrities
           WHERE category=%s AND net_worth IS NOT NULL AND id != ALL(%s)
           ORDER BY net_worth DESC LIMIT 20""",
        (category, list(picked_ids))
    )
    if same_cat:
        r = random.choice(same_cat)
        recommendations.append({
            "name": r[1], "net_worth_display": r[2], "photo_url": r[3],
            "category": r[4], "reason": f"More {meta['label']}"
        })

    # 2) Different category — pick a popular one
    other_cats = [c for c in CATEGORY_META if c != category]
    if other_cats:
        other_cat = random.choice(other_cats)
        other_meta = CATEGORY_META[other_cat]
        diff_cat = db_query(
            """SELECT id, name, net_worth_display, photo_url, category
               FROM celebrities
               WHERE category=%s AND net_worth >= %s AND net_worth IS NOT NULL
               ORDER BY net_worth DESC LIMIT 10""",
            (other_cat, other_meta["min_nw"])
        )
        if diff_cat:
            r = random.choice(diff_cat)
            recommendations.append({
                "name": r[1], "net_worth_display": r[2], "photo_url": r[3],
                "category": r[4], "reason": f"{other_meta['emoji']} {other_meta['label']}"
            })

    # 3) Another different category
    if len(other_cats) >= 2:
        used_cats = {category} | {rec.get("category") for rec in recommendations}
        remaining_cats = [c for c in other_cats if c not in used_cats]
        if remaining_cats:
            third_cat = random.choice(remaining_cats)
            third_meta = CATEGORY_META[third_cat]
            third_rows = db_query(
                """SELECT id, name, net_worth_display, photo_url, category
                   FROM celebrities
                   WHERE category=%s AND net_worth >= %s AND net_worth IS NOT NULL
                   ORDER BY net_worth DESC LIMIT 10""",
                (third_cat, third_meta["min_nw"])
            )
            if third_rows:
                r = random.choice(third_rows)
                recommendations.append({
                    "name": r[1], "net_worth_display": r[2], "photo_url": r[3],
                    "category": r[4], "reason": f"{third_meta['emoji']} {third_meta['label']}"
                })

    return {
        "category":        category,
        "category_label":  meta["label"],
        "category_emoji":  meta["emoji"],
        "celebrities":     celebrities,
        "recommendations": recommendations,
    }


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