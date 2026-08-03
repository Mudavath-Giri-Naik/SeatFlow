from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/seatflow"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Auth
    JWT_SECRET_KEY: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Payments (Phase 2)
    PAYMENT_GATEWAY_API_KEY: str = "mock-key"

    # CORS (Phase 2)
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    # Observability (Phase 4)
    SENTRY_DSN: str | None = None
    ENVIRONMENT: str = "development"

    # Booking
    SEAT_HOLD_TTL_SECONDS: int = 120

    APP_NAME: str = "SeatFlow"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
