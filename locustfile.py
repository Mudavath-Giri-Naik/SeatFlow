"""Load test: many simulated users hammer hold/confirm on a small, shared
pool of seats. The point isn't throughput — it's proving that under real
concurrent load, the Redis lock + SELECT ... FOR UPDATE combo in
booking_service never lets two users end up with a confirmed booking on the
same seat.

Run:
    locust -f locustfile.py --headless -u 1000 -r 100 --host http://localhost:8000

At the end, look for the "double-booking check" banner in stdout. It queries
Postgres directly (DATABASE_URL) for any seat with more than one CONFIRMED
booking — that count must be zero.
"""

import asyncio
import os
import random
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import requests
from locust import HttpUser, between, events, task

SEAT_POOL_SIZE = 15

_state: dict = {"show_id": None, "seat_ids": []}


def _bootstrap(host: str) -> None:
    """Create one venue/show/seat-pool that every simulated user contends over."""
    email = f"locust-admin-{uuid.uuid4().hex[:8]}@example.com"
    password = "loadtest12345"

    requests.post(f"{host}/auth/signup", json={"email": email, "password": password}, timeout=10)
    login = requests.post(f"{host}/auth/login", json={"email": email, "password": password}, timeout=10)
    login.raise_for_status()
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    venue = requests.post(
        f"{host}/venues", json={"name": "Locust Venue"}, headers=headers, timeout=10
    ).json()

    starts_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    show = requests.post(
        f"{host}/shows",
        json={"venue_id": venue["id"], "title": "Locust Show", "starts_at": starts_at},
        headers=headers,
        timeout=10,
    ).json()

    seat_ids = []
    for i in range(SEAT_POOL_SIZE):
        seat = requests.post(
            f"{host}/seats",
            json={"show_id": show["id"], "row_label": "A", "seat_number": i + 1, "price": "20.00"},
            headers=headers,
            timeout=10,
        ).json()
        seat_ids.append(seat["id"])

    _state["show_id"] = show["id"]
    _state["seat_ids"] = seat_ids


@events.test_start.add_listener
def on_test_start(environment, **kwargs) -> None:
    _bootstrap(environment.host)
    print(f"[locust] seeded show {_state['show_id']} with {len(_state['seat_ids'])} contended seats")


async def _count_double_bookings() -> list[str]:
    database_url = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/seatflow"
    )
    dsn = database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            """
            SELECT seat_id::text AS seat_id, COUNT(*) AS confirmed_count
            FROM bookings
            WHERE status = 'confirmed'
            GROUP BY seat_id
            HAVING COUNT(*) > 1
            """
        )
    finally:
        await conn.close()
    return [row["seat_id"] for row in rows]


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs) -> None:
    if not _state["show_id"]:
        return
    try:
        double_booked = asyncio.run(_count_double_bookings())
    except Exception as exc:  # noqa: BLE001
        print(f"[locust] could not run double-booking check against Postgres: {exc}")
        return

    print("=" * 70)
    if double_booked:
        print(f"[locust] DOUBLE BOOKING DETECTED on {len(double_booked)} seat(s): {double_booked}")
        environment.process_exit_code = 1
    else:
        print("[locust] double-booking check passed: 0 seats have more than one confirmed booking")
    print("=" * 70)


class SeatBookingUser(HttpUser):
    wait_time = between(0.1, 1.0)

    def on_start(self) -> None:
        self.email = f"locust-{uuid.uuid4().hex}@example.com"
        self.password = "loadtest12345"
        self.client.post("/auth/signup", json={"email": self.email, "password": self.password})
        res = self.client.post("/auth/login", json={"email": self.email, "password": self.password})
        self.token = res.json().get("access_token", "")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task
    def hold_and_confirm_random_seat(self) -> None:
        if not _state["seat_ids"]:
            return
        seat_id = random.choice(_state["seat_ids"])

        hold_res = self.client.post(f"/seats/{seat_id}/hold", headers=self.headers, name="/seats/[id]/hold")
        if hold_res.status_code != 200:
            # Expected under contention: someone else already holds/booked this seat.
            return

        self.client.post(
            "/bookings/confirm",
            json={"seat_id": seat_id},
            headers={**self.headers, "Idempotency-Key": str(uuid.uuid4())},
            name="/bookings/confirm",
        )
        # 200 = booked. 402 = simulated payment failure (retryable). 409 = lost
        # the race between hold succeeding and confirm running. All expected.
