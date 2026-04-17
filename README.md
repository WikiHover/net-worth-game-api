# Net Worth Game API

Backend API for the WikiHover **"Rank the Rich"** game — a net worth ranking game embedded in the WikiHover player tooltip.

When a user hovers over a celebrity name on any webpage, the Rank tab shows 5 famous celebrities from the same category (actors, singers, NBA players, etc.). The user drags them richest → poorest and gets scored.

---

## Architecture

```
Chrome Extension (WikiHover Player)
        │
        ▼
AWS App Runner  (this service)
        │
        ▼
AWS RDS PostgreSQL  (24,000+ celebrities with net worth data)
```

Data is scraped from public net worth sources and includes **24,242 celebrities** across 18+ categories.

---

## How it works

The game uses a **single API call**. The server returns all 5 celebrities with their net worth values included (shuffled). The JS client scores the user's ranking entirely locally — no second round-trip needed.

```
User hovers name → JS fetches /api/game/challenge
                 → Server returns 5 celebs (shuffled) with net_worth included
                 → User drags to rank
                 → JS scores locally → instant result, no submit call
```

---

## API Endpoints

### `GET /api/game/challenge?entity={name}`

The only game endpoint. Returns 5 famous celebrities from the same category as the hovered entity, shuffled for display. Includes full net worth data so the client can score locally.

Wikipedia photos are fetched on first request and cached in the DB.

**Example:** `GET /api/game/challenge?entity=Taylor+Swift`

```json
{
  "category": "singers",
  "category_label": "Singers",
  "category_emoji": "🎤",
  "celebrities": [
    { "id": 123, "name": "Rihanna",       "net_worth": 1400000000, "net_worth_display": "$1.4 Billion", "photo_url": "https://upload.wikimedia...", "initials": "R"  },
    { "id": 456, "name": "Jay-Z",          "net_worth": 2500000000, "net_worth_display": "$2.5 Billion", "photo_url": "https://upload.wikimedia...", "initials": "JZ" },
    { "id": 789, "name": "Taylor Swift",   "net_worth": 1100000000, "net_worth_display": "$1.1 Billion", "photo_url": "https://upload.wikimedia...", "initials": "TS" },
    { "id": 321, "name": "Paul McCartney", "net_worth": 1300000000, "net_worth_display": "$1.3 Billion", "photo_url": "https://upload.wikimedia...", "initials": "PM" },
    { "id": 654, "name": "Elton John",     "net_worth":  550000000, "net_worth_display": "$550 Million",  "photo_url": "https://upload.wikimedia...", "initials": "EJ" }
  ]
}
```

The JS feed (`networth_rank.js`) sorts celebrities by `net_worth` desc to determine the correct ranking, then compares against the user's drag order to compute score (0–5) and grade (S/A/B/C) — entirely client-side.

---

### `GET /api/search?q={name}&sort=net_worth&order=desc`

Search celebrities by name with pagination.

| Param | Default | Description |
|---|---|---|
| `q` | `""` | Name search (case-insensitive) |
| `sort` | `net_worth` | `net_worth` / `name` |
| `order` | `desc` | `asc` / `desc` |
| `limit` | `50` | Max 200 |
| `offset` | `0` | Pagination offset |

---

### `GET /api/stats`

Returns total count, top categories, and top 5 richest celebrities in the DB.

---

### `GET /health`

Health check — returns `{"status": "ok"}` when DB is reachable. Used by App Runner.

---

## Supported Categories

| Category | Label | Min Net Worth (famousness filter) |
|---|---|---|
| `actors` | Actors | $20M |
| `singers` | Singers | $10M |
| `rappers` | Rappers | $10M |
| `rock-stars` | Rock Stars | $10M |
| `nba` | NBA Players | $5M |
| `nfl` | NFL Players | $5M |
| `soccer` | Soccer Players | $5M |
| `richest-billionaires` | Billionaires | $1B |
| `ceos` | CEOs | $100M |
| `models` | Models | $5M |
| `comedians` | Comedians | $5M |
| `directors` | Directors | $10M |
| `boxers` | Boxers | $5M |
| `tennis` | Tennis Players | $5M |
| `authors` | Authors | $5M |

---

## Local Development

### Prerequisites
- Docker + Docker Compose
- Python 3.12+

### Run locally

```bash
# 1. Start PostgreSQL
docker compose up -d db

# 2. Migrate your scraped data into PostgreSQL
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python migrate_sqlite.py --sqlite /path/to/celebrities.db

# 3. Start the API
.venv/bin/uvicorn app:app --reload --port 8001

# 4. Test
curl "http://localhost:8001/api/game/challenge?entity=Taylor+Swift"
curl "http://localhost:8001/api/stats"
```

Or run everything with Docker Compose (after migration):

```bash
docker compose up
```

---

## Deploy to AWS

### Prerequisites
- AWS CLI v2 configured
- Docker running
- Terraform >= 1.5

### One-command deploy

```bash
cd terraform
DB_PASSWORD=yourpassword ./deploy.sh
```

This will:
1. Create ECR repository
2. Build and push Docker image
3. Create RDS PostgreSQL (t3.micro)
4. Deploy App Runner service
5. Auto-migrate your local SQLite data to RDS
6. Print the public App Runner URL

### Environment variables for `deploy.sh`

| Variable | Required | Default | Description |
|---|---|---|---|
| `DB_PASSWORD` | ✅ | — | PostgreSQL password |
| `AWS_REGION` | | `us-east-1` | AWS region |
| `SERVICE_NAME` | | `net-worth-game` | App Runner + ECR name |
| `SQLITE_PATH` | | `~/net_worth_scraper/celebrities.db` | Local SQLite to migrate |
| `IMAGE_TAG` | | `latest` | Docker image tag |

### Estimated AWS cost

| Resource | Cost |
|---|---|
| App Runner (1 vCPU / 2GB) | ~$10–15/month |
| RDS PostgreSQL t3.micro | ~$15/month (free tier first 12mo) |
| ECR storage | ~$1/month |
| **Total** | **~$25–30/month** |

---

## Connect to WikiHover Player

After deploying, add the App Runner URL to your WikiHover config:

```javascript
window.WikiHoverConfig = {
  token: "...",
  orgId: "...",
  feeds: { ... },
  networthApi: "https://xxxx.us-east-1.awsapprunner.com"  // ← add this
};
```

The `networth_rank.js` feed module reads `window.WikiHoverConfig.networthApi` and falls back to `http://localhost:8001` for local development.

---

## Project Structure

```
net-worth-game-api/
├── app.py              # FastAPI application (PostgreSQL)
├── migrate_sqlite.py   # One-time SQLite → PostgreSQL migration
├── requirements.txt
├── Dockerfile
├── docker-compose.yml  # Local dev: API + PostgreSQL
└── terraform/
    ├── main.tf         # ECR + RDS + App Runner
    ├── variables.tf
    ├── outputs.tf
    └── deploy.sh       # Full deploy + data migration
```
