# Deployment guide

Backend → **Render**, frontend → **Vercel**. This is the exact path used to deploy the live demo, including the gotchas that actually came up.

## Part A — Backend on Render

### 1. Create the Postgres database
Render dashboard → **New +** → **PostgreSQL** → Free plan → create it, then copy the **Internal Database URL**.

### 2. Create Redis
**New +** → **Redis** (may be labeled **Key Value**) → Free plan → copy the **Internal Redis URL**.

> If Render doesn't offer a free Redis tier for your account, use [Upstash](https://upstash.com/) instead (free serverless Redis) — it's a drop-in `REDIS_URL` replacement.

### 3. Create the web service
**New +** → **Web Service** → connect the `SeatFlow` repo.

- **Root Directory: leave blank.** The `Dockerfile` lives at the repo root — do **not** point Render at the `frontend` folder, that's Vercel's job.
- Render should auto-detect **Docker** as the runtime from the `Dockerfile`.

### 4. Environment variables

| Key | Value |
|---|---|
| `DATABASE_URL` | Internal Postgres URL, **with the scheme changed** from `postgresql://` to `postgresql+asyncpg://` |
| `REDIS_URL` | Internal Redis URL |
| `JWT_SECRET_KEY` | Long random string (`openssl rand -hex 32`) |
| `JWT_ALGORITHM` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` |
| `PAYMENT_GATEWAY_API_KEY` | any placeholder |
| `FRONTEND_ORIGIN` | placeholder for now (e.g. `http://localhost:3000`) — fixed in Part C |
| `ENVIRONMENT` | `production` |
| `SENTRY_DSN` | optional, leave blank |

> **Gotcha:** Render's copy-paste "Internal Database URL" gives you plain `postgresql://`. If you paste it in unmodified, the app falls back to the `psycopg2` driver, which isn't installed (this project uses `asyncpg`), and migrations fail with `ModuleNotFoundError: No module named 'psycopg2'`. Always double check the scheme is `postgresql+asyncpg://`.

### 5. Deploy
Create the service. The `entrypoint.sh` script runs `alembic upgrade head` automatically before starting the server — watch the **Logs** tab for `Uvicorn running on...`.

### 6. Verify
```
https://<your-service>.onrender.com/health
```
should return `{"status":"ok","checks":{"database":"ok","redis":"ok"}}`.

## Part B — Frontend on Vercel

1. Vercel dashboard → **Add New...** → **Project** → import the same repo.
2. **This is the important folder setting**: click **Edit** next to "Root Directory" and set it to **`frontend`**. (Opposite of Render — Vercel needs the Next.js app specifically, not the repo root.)
3. Environment variables:

   | Key | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | your Render URL, e.g. `https://seatflow-xxxx.onrender.com` |
   | `NEXT_PUBLIC_WS_URL` | same host, `wss://` scheme, e.g. `wss://seatflow-xxxx.onrender.com` |

4. Deploy. Vercel gives you a stable domain (e.g. `your-app.vercel.app`) plus a per-deployment preview URL that changes every build — use the **stable** one for the next step.

## Part C — Connect them

Go back to Render → your web service → **Environment** → set `FRONTEND_ORIGIN` to your **stable** Vercel domain (no trailing slash) → save. This triggers a redeploy and unblocks CORS.

## Part D — Seed production data

Render's free tier has no shell access, so seed from your own machine against the **External** Database URL (different from Internal — Internal only resolves inside Render's private network):

```bash
# copy the External Database URL from the Render Postgres dashboard first
export DATABASE_URL="postgresql+asyncpg://user:pass@host/dbname?ssl=require"
python -m scripts.seed
```

> **Gotcha:** Render's *external* Postgres connections require SSL (internal ones don't — that's why the app itself connects fine without any `ssl=` param). Forgetting `?ssl=require` on the external URL fails with `asyncpg.exceptions.InvalidAuthorizationSpecificationError: SSL/TLS required`.

Copy the `Show:` UUID the seed script prints (not that you'll need to paste it anywhere — the frontend browses shows automatically) and open your Vercel URL to confirm everything's live end to end.
