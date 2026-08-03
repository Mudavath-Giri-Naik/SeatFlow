"""Sentry error tracking. No-ops gracefully if SENTRY_DSN isn't set, so
local dev never needs a Sentry account."""

import sentry_sdk

from app.core.config import settings
from app.core.logging_config import logger


def init_sentry() -> None:
    if not settings.SENTRY_DSN:
        logger.debug("SENTRY_DSN not set - Sentry error tracking disabled")
        return

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        traces_sample_rate=0.2,
    )
    logger.info("Sentry initialized (environment={})", settings.ENVIRONMENT)
