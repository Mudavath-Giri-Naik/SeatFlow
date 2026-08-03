"""Structured logging via loguru.

Human-readable, colorized logs in development; single-line JSON in
production (easy to ship to any log aggregator). Import `logger` from here
everywhere instead of using `print`.
"""

import sys

from loguru import logger

from app.core.config import settings

_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)


def configure_logging() -> None:
    logger.remove()
    is_production = settings.ENVIRONMENT.lower() == "production"
    logger.add(
        sys.stdout,
        level="INFO" if is_production else "DEBUG",
        format=_LOG_FORMAT,
        colorize=not is_production,
        serialize=is_production,
        backtrace=not is_production,
    )


__all__ = ["configure_logging", "logger"]
