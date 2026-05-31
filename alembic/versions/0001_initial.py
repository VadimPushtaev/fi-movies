"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-31 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_cities_slug"),
    )
    op.create_table(
        "movies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_movie_id", sa.String(length=120), nullable=False),
        sa.Column("source_internal_id", sa.String(length=120), nullable=True),
        sa.Column("slug", sa.String(length=240), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("original_title", sa.String(length=500), nullable=True),
        sa.Column("swedish_title", sa.String(length=500), nullable=True),
        sa.Column("poster_url", sa.Text(), nullable=True),
        sa.Column("trailer_url", sa.Text(), nullable=True),
        sa.Column("age_limit", sa.String(length=40), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("genres", sa.Text(), nullable=True),
        sa.Column("distributor", sa.String(length=250), nullable=True),
        sa.Column("premiere_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("director", sa.Text(), nullable=True),
        sa.Column("script", sa.Text(), nullable=True),
        sa.Column("actors", sa.Text(), nullable=True),
        sa.Column("raw_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source", "source_movie_id", name="uq_movies_source_movie"),
    )
    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("movies_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("theaters_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("showtimes_seen", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "theaters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_theater_id", sa.String(length=120), nullable=False),
        sa.Column("city_id", sa.Integer(), sa.ForeignKey("cities.id"), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("webpage_url", sa.Text(), nullable=True),
        sa.Column("phone_number", sa.String(length=120), nullable=True),
        sa.Column("email", sa.String(length=250), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("api_id", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source", "source_theater_id", name="uq_theaters_source_theater"),
    )
    op.create_table(
        "showtimes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_key", sa.String(length=128), nullable=False),
        sa.Column("source_show_id", sa.String(length=180), nullable=True),
        sa.Column("source_raw_id", sa.String(length=180), nullable=True),
        sa.Column("movie_id", sa.Integer(), sa.ForeignKey("movies.id"), nullable=False),
        sa.Column("theater_id", sa.Integer(), sa.ForeignKey("theaters.id"), nullable=False),
        sa.Column("auditorium", sa.String(length=250), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("order_page_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_key", name="uq_showtimes_source_key"),
    )
    op.create_index("ix_showtimes_starts_at", "showtimes", ["starts_at"])
    op.create_index("ix_showtimes_theater_time", "showtimes", ["theater_id", "starts_at"])


def downgrade() -> None:
    op.drop_index("ix_showtimes_theater_time", table_name="showtimes")
    op.drop_index("ix_showtimes_starts_at", table_name="showtimes")
    op.drop_table("showtimes")
    op.drop_table("theaters")
    op.drop_table("scrape_runs")
    op.drop_table("movies")
    op.drop_table("cities")

