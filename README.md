# SeatFlow

Real-time seat booking system: FastAPI (async) + PostgreSQL + Redis, with
Redis locks + `SELECT ... FOR UPDATE` guaranteeing no seat is ever
double-booked, even under concurrent load.

## Tech stack

| Layer | Technology |
|---|---|
| API framework | FastAPI (async), Uvicorn |
| Database | PostgreSQL + SQLAlchemy (async) + Alembic |
| Cache / locks | Redis |
| Auth | PyJWT, passlib + bcrypt |
| Validation | Pydantic |
| Reliability | tenacity (retries), custom idempotency keys |
| Security | slowapi (rate limiting), CORS |
| Testing | pytest, pytest-asyncio, Locust |
| Logging/monitoring | loguru, sentry-sdk |
| Containerization | Docker, docker-compose |
| CI/CD | GitHub Actions |
| Frontend | Next.js (minimal, backend-focused project) |
| Hosting | Render/Railway (backend), Vercel (frontend) |

## Project layout

```
app/
  main.py           FastAPI app + router wiring
  core/              config, db engine, redis client, security helpers
  models/            SQLAlchemy async models
  schemas/           Pydantic Create/Read schemas
  services/          business logic, no FastAPI imports
  api/               routers (thin — validation + calling services)
alembic/             migrations
tests/               pytest suite
scripts/seed.py       demo data seeder
frontend/             minimal Next.js seat map UI (Phase 2+)
```

## Getting started (local development)

### 1. Prerequisites

- Python 3.12+
- Docker (for Postgres + Redis) — or your own local instances
- Node 20+ (only needed once the frontend exists, Phase 2+)

### 2. Configure environment

```bash
cp .env.example .env
# edit .env: set JWT_SECRET_KEY to a long random string at minimum
```

### 3. Start Postgres + Redis

```bash
docker-compose up -d
```

This starts only `postgres` and `redis` in Phase 1/2 — the API runs locally
via uvicorn so you get fast reload during development. (Phase 3 adds the
backend itself to docker-compose for a one-command full-stack run.)

### 4. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Run migrations

```bash
alembic upgrade head
```

### 6. Start the API

```bash
uvicorn app.main:app --reload
```

The API is now at `http://localhost:8000`, interactive docs at
`http://localhost:8000/docs`.

### 7. Create some data

Either use the seed script:

```bash
python -m scripts.seed
```

...or do it by hand through `/docs`:

1. `POST /auth/signup` — create a user
2. `POST /auth/login` — get an access token, click "Authorize" in `/docs` with `Bearer <access_token>`
3. `POST /venues`, `POST /shows`, `POST /seats` — build up a seat map

## Concurrency model (the core of this project)

- **Hold** (`hold_seat`): acquires a Redis lock (`SET NX PX`) per seat with a
  short TTL (default 120s, `SEAT_HOLD_TTL_SECONDS`). If another user already
  holds the lock, this fails immediately and cheaply — no DB round trip for
  the losing request beyond the initial seat lookup.
- **Confirm** (`confirm_booking`): opens a Postgres transaction and issues
  `SELECT ... FOR UPDATE` on the seat row. This is the actual source of
  truth — even if two requests both believe they hold the Redis lock (e.g.
  a bug, or a lock that just expired), only one can win the row lock and
  flip the seat to `booked`; the other observes the already-booked status
  and aborts.
- **Release** (`release_seat`): used on explicit cancellation or hold
  timeout. Releases the Redis lock (via an atomic compare-and-delete Lua
  script so you can only release a lock you own) and resets the seat back
  to `available`.
- **Reconciliation**: `reconcile_seat_status` self-heals reads — if a seat
  is marked `held` in Postgres but its Redis lock has since expired (TTL
  ran out without an explicit release), it's flipped back to `available` on
  the next read instead of staying stuck.

## API surface (Phase 2)

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/shows/{id}/seats` | no | Full seat map, self-heals expired holds on read |
| POST | `/seats/{id}/hold` | yes | Rate-limited 10/min/user |
| POST | `/bookings/confirm` | yes | Requires `Idempotency-Key` header; rate-limited 10/min/user |
| POST | `/bookings/{id}/cancel` | yes | Works for both held and confirmed bookings |
| WS | `/ws/shows/{id}` | no | Broadcasts `{event, seat_id, status}` on hold/confirm/release |

### Idempotency

`POST /bookings/confirm` requires an `Idempotency-Key` header (any client-generated
UUID works). The key is scoped per-user in Redis:

- First request with a key: claims it, processes the booking, caches the response.
- Same key seen again after success: the cached response is replayed verbatim —
  the booking/payment logic does not re-run.
- Same key seen again *while the first request is still in flight*: returns
  `409` immediately instead of double-processing.
- On a business failure (payment declined, seat lost the race), the claim is
  released so the same key can be retried.

### Payments & retries

`app/services/payment_service.py` simulates a flaky external payment
provider (~35% simulated failure rate). Calls are wrapped in `tenacity`
with exponential backoff (up to 3 attempts) before the failure is allowed
to propagate as `402 Payment Required`. Watch the logs during a confirm
call to see retries happen.

### Real-time updates

The WebSocket endpoint doesn't hold an in-process connection registry —
it subscribes to a Redis Pub/Sub channel per show (`show:{id}:events`).
Every hold/confirm/cancel publishes to that channel. This is what makes
broadcasts work correctly once the backend runs as multiple worker
processes (Phase 3's `gunicorn -k uvicorn.workers.UvicornWorker -w N`): a
hold handled by worker A still reaches a client connected to worker B.

### Rate limiting & CORS

`/seats/{id}/hold` and `/bookings/confirm` are capped at 10 requests/minute,
keyed by authenticated user id (falls back to IP for unauthenticated
requests). CORS only allows the single origin configured in
`FRONTEND_ORIGIN` — no wildcard.

## Frontend (Phase 2)

A minimal Next.js app in `/frontend` — its only job is to prove the backend
works: sign up/log in, load a show's seat map, hold/confirm seats, and watch
updates arrive live over the WebSocket in a second tab.

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`, sign up, paste in a show UUID (from
`python -m scripts.seed`'s output), and click Load Seats. Open the same page
in a second tab and hold the same seat from both — only one should succeed,
and both tabs' grids update instantly via the WebSocket.

## Testing (Phase 3)

```bash
# unit tests only (no infra needed)
pytest tests/unit

# full suite — integration tests need postgres+redis reachable
docker-compose up -d postgres redis
pytest
```

- `tests/unit/` — `booking_service` with Redis/DB fully mocked (`unittest.mock.AsyncMock`).
- `tests/integration/test_booking_flow.py` — real hold → confirm flow against
  live Postgres + Redis.
- `tests/integration/test_concurrency.py` — the core correctness test: fires
  two (and separately twenty) simultaneous `hold_seat` calls at the same seat
  with `asyncio.gather` and asserts exactly one wins.

Integration tests auto-skip with a clear message if Postgres/Redis aren't
reachable, so `pytest` still passes in an environment with no Docker. They
run against whatever `DATABASE_URL`/`REDIS_URL` point at and will create/drop
tables and flush that Redis DB — point them at a disposable instance (the
docker-compose ones are fine).

### Load test (Locust)

```bash
docker-compose up -d
locust -f locustfile.py --headless -u 1000 -r 100 --host http://localhost:8000
```

This seeds one show with a small pool of 15 seats and throws many simulated
users at hold/confirm on that pool concurrently. At the end it queries
Postgres directly for any seat with more than one `confirmed` booking and
prints a pass/fail banner — that count must be zero.

## Full stack via Docker (Phase 3)

```bash
docker-compose up --build
```

This now brings up Postgres, Redis, **and** the backend itself in one
command. The backend image is a multi-stage build (deps compiled in a
`builder` stage, slim runtime in the final stage, run as a non-root user)
served by `gunicorn` with `uvicorn` workers. The container's entrypoint runs
`alembic upgrade head` before starting the server, so migrations are always
applied automatically.

`GET /health` checks both DB and Redis connectivity and returns `200` (or
`503` if either is down) — used for the container `HEALTHCHECK` and is a
good target for your platform's health-check config in Phase 4.

## CI/CD (Phase 4)

`.github/workflows/ci.yml` runs on every push and PR:

1. **lint** — `ruff check` over `app/`, `scripts/`, `tests/`, `locustfile.py`.
2. **test** — spins up real Postgres + Redis as GitHub Actions service
   containers, runs `alembic upgrade head`, then the full `pytest` suite
   (unit + integration — nothing skips in CI since the services are real).
3. **build-image** — builds the production Docker image (with GitHub Actions
   layer caching). On `push` to `main` only, it also logs in to
   `ghcr.io` using the automatically-provided `GITHUB_TOKEN` (no extra secret
   needed) and pushes `ghcr.io/<owner>/<repo>:latest` and `:<commit-sha>`.

## Logging & error tracking (Phase 4)

- All application code logs through `loguru` (`app/core/logging_config.py`)
  instead of `print` — colorized human-readable output in development,
  single-line JSON in production (`ENVIRONMENT=production`) for easy
  ingestion by any log aggregator.
- `sentry-sdk` is initialized in `app/core/sentry.py`, reading `SENTRY_DSN`.
  If it's unset (the default), Sentry is skipped entirely and a debug log
  line notes it — local dev never needs a Sentry account.

## Deployment

### Backend — Render or Railway

Both platforms work the same way here: connect the repo, point it at the
`Dockerfile`, add managed Postgres + Redis, set env vars.

**Render:**

1. Push this repo to GitHub.
2. In the Render dashboard: **New → Web Service**, connect the repo.
3. Render should auto-detect the `Dockerfile` (leave build/start commands
   blank — they come from `ENTRYPOINT`/`CMD`).
4. **New → PostgreSQL** and **New → Redis** (Render's managed Redis, or use
   the Key Value add-on) — create both, then copy their **Internal
   Connection Strings**.
5. On the web service, add environment variables:
   - `DATABASE_URL` = the Postgres internal URL, with `postgresql+asyncpg://`
     as the scheme (Render gives you `postgresql://` — just change the prefix)
   - `REDIS_URL` = the Redis internal URL
   - `JWT_SECRET_KEY` = a long random string (`openssl rand -hex 32`)
   - `JWT_ALGORITHM=HS256`, `ACCESS_TOKEN_EXPIRE_MINUTES=15`, `REFRESH_TOKEN_EXPIRE_DAYS=7`
   - `PAYMENT_GATEWAY_API_KEY` = any placeholder
   - `FRONTEND_ORIGIN` = your deployed Vercel URL (set this after step below)
   - `SENTRY_DSN` = optional
   - `ENVIRONMENT=production`
6. Deploy. Render builds the Dockerfile and runs the container — migrations
   run automatically via `entrypoint.sh`.

**Railway:** same shape — **New Project → Deploy from GitHub repo**, add the
Postgres and Redis plugins from Railway's marketplace, copy their reference
variables (`${{Postgres.DATABASE_URL}}` etc., adjusting the scheme to
`postgresql+asyncpg://`) into the backend service's variables, same list as
above, deploy.

### Frontend — Vercel

1. In the Vercel dashboard: **Add New → Project**, import this repo.
2. Set **Root Directory** to `frontend`.
3. Framework preset should auto-detect as Next.js.
4. Add environment variables:
   - `NEXT_PUBLIC_API_URL` = your deployed backend URL (e.g. `https://seatflow-backend.onrender.com`)
   - `NEXT_PUBLIC_WS_URL` = same host, `wss://` scheme (e.g. `wss://seatflow-backend.onrender.com`)
5. Deploy. Then go back to your backend's `FRONTEND_ORIGIN` env var and set
   it to the Vercel URL you were just given, and redeploy the backend so CORS
   allows it.

## Environment variables

See `.env.example` for the full list with comments.

- Phase 1 requires `DATABASE_URL`, `REDIS_URL`, and `JWT_SECRET_KEY` at minimum.
- Phase 2 adds `PAYMENT_GATEWAY_API_KEY` (any placeholder value — it's a mock)
  and `FRONTEND_ORIGIN` (e.g. `http://localhost:3000`, used for CORS).
- Phase 4 adds `SENTRY_DSN` (optional — leave blank to disable Sentry).

Credentials that do **not** go in `.env`:

- **GitHub Actions secrets**: none required for the ghcr.io push —
  `GITHUB_TOKEN` is provided automatically by GitHub. You'd only add repo
  secrets here if you switched to pushing to Docker Hub instead.
- **Render/Railway dashboard env vars**: same variable names as `.env`, but
  production values, entered directly in their dashboard — never committed.
- **Vercel dashboard env vars**: `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_WS_URL`.
