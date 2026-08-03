"""initial schema: users, venues, shows, seats, bookings

Revision ID: 0001
Revises:
Create Date: 2026-08-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "venues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("city", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "shows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "venue_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("venues.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_shows_venue_id", "shows", ["venue_id"])

    seat_status_enum = postgresql.ENUM("available", "held", "booked", name="seat_status")
    seat_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "seats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "show_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_label", sa.String(length=10), nullable=False),
        sa.Column("seat_number", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column(
            "status",
            postgresql.ENUM("available", "held", "booked", name="seat_status", create_type=False),
            nullable=False,
            server_default="available",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("show_id", "row_label", "seat_number", name="uq_seat_position_per_show"),
    )
    op.create_index("ix_seats_show_id", "seats", ["show_id"])

    booking_status_enum = postgresql.ENUM("held", "confirmed", "cancelled", name="booking_status")
    booking_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "bookings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "seat_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("seats.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "status",
            postgresql.ENUM("held", "confirmed", "cancelled", name="booking_status", create_type=False),
            nullable=False,
            server_default="held",
        ),
        sa.Column("held_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bookings_seat_id", "bookings", ["seat_id"])
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_bookings_user_id", table_name="bookings")
    op.drop_index("ix_bookings_seat_id", table_name="bookings")
    op.drop_table("bookings")
    postgresql.ENUM(name="booking_status").drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_seats_show_id", table_name="seats")
    op.drop_table("seats")
    postgresql.ENUM(name="seat_status").drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_shows_venue_id", table_name="shows")
    op.drop_table("shows")

    op.drop_table("venues")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
