"""Mock external payment provider.

Randomly fails (simulating network flakiness / provider timeouts) so the
tenacity retry-with-exponential-backoff logic actually gets exercised. No
FastAPI imports — pure business logic, unit-testable in isolation.
"""

import asyncio
import random
import uuid
from decimal import Decimal
from typing import Any

from tenacity import RetryCallState, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.logging_config import logger

# Tuned for demo purposes: low enough that most requests still succeed after
# retries, high enough to actually see retries happen in the logs.
SIMULATED_FAILURE_RATE = 0.35


class PaymentError(Exception):
    """Raised when the (mock) payment provider fails to authorize a charge."""


def _log_retry(retry_state: RetryCallState) -> None:
    logger.warning(
        "payment attempt {} failed, retrying after backoff: {}",
        retry_state.attempt_number,
        retry_state.outcome.exception() if retry_state.outcome else None,
    )


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    retry=retry_if_exception_type(PaymentError),
    before_sleep=_log_retry,
)
async def charge(user_id: uuid.UUID, seat_id: uuid.UUID, amount: Decimal) -> dict[str, Any]:
    """Simulate an async call to a payment gateway. Raises PaymentError on
    (simulated) failure; tenacity retries with exponential backoff up to 3
    attempts before giving up and letting the error propagate."""
    await asyncio.sleep(0.05)  # simulate network latency

    if random.random() < SIMULATED_FAILURE_RATE:
        raise PaymentError("payment provider timed out")

    return {
        "transaction_id": str(uuid.uuid4()),
        "status": "succeeded",
        "amount": str(amount),
        "user_id": str(user_id),
        "seat_id": str(seat_id),
    }
