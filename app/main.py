from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import auth, bookings, catalog, health, seats, websocket
from app.core.config import settings
from app.core.logging_config import configure_logging, logger
from app.core.rate_limit import limiter
from app.core.redis import close_redis
from app.core.sentry import init_sentry

configure_logging()
init_sentry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("{} starting up (environment={})", settings.APP_NAME, settings.ENVIRONMENT)
    yield
    await close_redis()
    logger.info("{} shut down", settings.APP_NAME)


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(seats.router)
app.include_router(bookings.router)
app.include_router(websocket.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": settings.APP_NAME, "status": "ok"}
