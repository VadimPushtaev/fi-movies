"""Store the HIFF timetable.

Revision ID: 0003_hiff_timetable
Revises: 0002_movie_tmdb_id
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_hiff_timetable"
down_revision: str | None = "0002_movie_tmdb_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hiff_movies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("original_title", sa.String(length=500), nullable=True),
        sa.Column("poster_url", sa.Text(), nullable=True),
        sa.Column("letterboxd_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_url", name="uq_hiff_movies_source_url"),
    )
    op.create_table(
        "hiff_screenings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_key", sa.String(length=180), nullable=False),
        sa.Column("movie_id", sa.Integer(), sa.ForeignKey("hiff_movies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("venue", sa.String(length=300), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("screening_number", sa.Integer(), nullable=True),
        sa.Column("screening_total", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_key", name="uq_hiff_screenings_source_key"),
    )
    op.create_index("ix_hiff_screenings_starts_at", "hiff_screenings", ["starts_at"])


def downgrade() -> None:
    op.drop_index("ix_hiff_screenings_starts_at", table_name="hiff_screenings")
    op.drop_table("hiff_screenings")
    op.drop_table("hiff_movies")
