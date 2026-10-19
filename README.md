# Content Outlier — Backend MVP

**Content Outlier** is a competitor-content intelligence SaaS backend that tracks competitor Instagram accounts, collects public Reels and performance metrics, stores historical metric snapshots, identifies statistically anomalous high-performing content relative to account baselines, downloads outlier media, and serves insights to the frontend.

---

## 1. System Architecture

```
Frontend (content-outlier.html)
        ↓ HTTP / REST
Backend API (FastAPI)
        ↓ ACID Transactions
PostgreSQL Database
        ↓ Non-blocking transactional queue (SELECT FOR UPDATE SKIP LOCKED)
VPS Background Worker Loop + APScheduler
        ↓ Python Module API (Session management, rate limit backoff)
Instaloader Client
        ↓
Instagram Public Graph
```

### Key Technical Pillars:
1. **Asynchronous Scraping**: Scraping is never executed within request-response cycles. Competitor creations immediately return HTTP 201 with a queued job descriptor.
2. **Normalized Historical Metrics**: Every scrape creates an immutable snapshot in `content_metrics` (`views, likes, comments, shares, saves, view_velocity, growth`).
3. **Isolated Outlier Intelligence**: Median baseline tracking, view multipliers, engagement lift, velocity bonuses, and transparent explainability reasons.
4. **Resilient Instagram Collection**: Explicit handling of 429 rate limits, exponential backoff with jitter, checkpoint identification, and strict preservation of `NULL` metrics.
5. **Abstract Storage Layer**: Media assets (videos/thumbnails) can be stored on local VPS storage, AWS S3, or Cloudflare R2 without changing business logic.
6. **Non-blocking Transcription Pipeline**: Modular pipeline designed for OpenAI Whisper with timestamped segments and structured hook breakdowns.

---

## 2. Directory Structure

```
ContentOutlier/
├── content-outlier.html        # Interactive frontend dashboard (connected to API)
├── seed_demo_data.py           # Demonstration database seeder
├── docker-compose.yml          # PostgreSQL + API + Worker orchestration
├── Dockerfile                  # Container definition
├── schema.sql                  # Raw PostgreSQL DDL schema
├── alembic.ini                 # Alembic configuration
├── alembic/                    # Database migrations
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py
├── app/
│   ├── config.py               # Pydantic Settings
│   ├── database.py             # Engine & SessionLocal
│   ├── models/                 # SQLAlchemy 2.0 ORM models
│   │   ├── competitor.py       # Competitor account model
│   │   ├── content.py          # Content items (Reels/videos)
│   │   ├── metric.py           # Historical snapshots (content_metrics)
│   │   ├── transcript.py       # Whisper transcripts & breakdowns
│   │   ├── job.py              # Scrape & processing job queue models
│   │   └── user.py             # User accounts
│   ├── schemas/                # Pydantic validation schemas
│   ├── storage/                # BaseStorage, LocalStorage, S3Storage
│   ├── scraper/                # InstaloaderClient & InstagramCollector
│   ├── services/
│   │   ├── outlier_engine.py   # Baseline, multiplier, & scoring intelligence
│   │   ├── competitor_service.py # Competitor lifecycle & sync dispatch
│   │   ├── content_service.py  # Content persistence & aggregation
│   │   └── transcription_service.py # Transcription pipeline
│   ├── worker/
│   │   ├── queue.py            # Transactional database job queue
│   │   ├── tasks.py            # Background job executions
│   │   ├── scheduler.py        # Periodic incremental scraper (APScheduler)
│   │   └── runner.py           # Worker daemon process
│   └── api/
│       ├── main.py             # FastAPI entrypoint, CORS, static media
│       ├── competitors.py      # /competitors endpoints
│       ├── outliers.py         # /outliers endpoints
│       ├── dashboard.py        # /dashboard endpoint
│       ├── content.py          # /content endpoints
│       └── jobs.py             # /jobs endpoints
└── tests/                      # 12 automated unit & integration tests
```

---

## 3. Outlier Scoring Engine

Rather than sorting raw views, the system calculates outlier performance relative to an account's own historical median baseline:

$$\text{View Multiplier} = \frac{\text{Current Reel Views}}{\max(\text{Competitor Median Reel Views}, 1)}$$

### Scoring Formulation:
- **Baseline Metric**: Median view count of competitor's tracked Reels (resistant to viral spikes).
- **Engagement Lift**: Ratio of post engagement rate to account baseline engagement rate.
- **View Velocity**: Hourly view growth rate: $\frac{\text{Views}}{\text{Hours Alive}}$.
- **Composite Score**: Weighted aggregate blending View Multiplier (60%), Engagement Lift (25%), and Velocity (15%).
- **Threshold**: When View Multiplier $\ge 3.0\times$, the item is flagged as an outlier (`is_outlier = True`).
- **Explainability**: Each item stores structured metadata explaining *why* it succeeded (e.g. `Generated 18.4× more views than @moveperformance's normal baseline (45,000 views) with 86% higher audience engagement`).

---

## 4. API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/dashboard` | High-level metrics: competitor count, tracked content, outliers found, hero card |
| `GET` | `/outliers` | Outlier feed filterable by competitor, date range (`7d`,`30d`,`90d`,`all`), `min_score`, and sort |
| `POST` | `/competitors` | Add competitor (cleans `@` prefix, queues initial sync job) |
| `GET` | `/competitors` | List competitors with follower counts and content count |
| `GET` | `/competitors/:id` | Detail of a single competitor |
| `PATCH`| `/competitors/:id` | Update competitor status (active, paused) |
| `DELETE`| `/competitors/:id`| Remove competitor from tracking |
| `POST` | `/competitors/:id/sync` | Trigger an immediate on-demand profile sync job |
| `GET` | `/content` | Paginated library of all tracked content items |
| `GET` | `/content/:id` | Single content detail with latest performance and transcript |
| `GET` | `/content/:id/metrics` | Historical snapshot array for growth charting and velocity analysis |
| `GET` | `/content/:id/transcript` | Timestamped transcript segments and structured hook breakdown |
| `GET` | `/jobs` | List recent background jobs and statuses (`queued`, `running`, `completed`, `failed`)|
| `GET` | `/jobs/:id` | Check specific job execution status |
| `GET` | `/health` | Application health and runtime configuration check |

---

## 5. Quickstart & Local Setup

### Prerequisites
- Python 3.11+
- Virtual environment

### Installation
```bash
# Clone & navigate to repository
cd ContentOutlier

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment variables
cp .env.example .env
```

### Seed Demo Data & Start Server
```bash
# Populate database with sample competitors, historical metrics, outliers & transcripts
python seed_demo_data.py

# Launch the FastAPI server
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser to:
- **Dashboard & App**: `http://localhost:8000/`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Start Background Worker
In a separate terminal:
```bash
python -m app.worker.runner
```

---

## 6. Running Tests

```bash
python -m pytest -v
```
All 12 test suites validate:
- Competitor management API and automatic job dispatch
- Outlier median baseline calculations and explainability summaries
- Historical snapshot tracking and velocity calculation
- Local & S3-compatible abstract storage
- Worker queue locking, exponential backoff, and retry handling
- Rate limit exception handling and preservation of `NULL` metrics

---

## 7. Production Deployment (Docker Compose)

To run the complete production stack (PostgreSQL 16 + FastAPI + VPS Worker):
```bash
docker compose up -d
```
All schema migrations are applied automatically on startup.
