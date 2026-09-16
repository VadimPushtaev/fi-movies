"""Store Letterboxd genres for HIFF films.

Revision ID: 0004_hiff_letterboxd_genres
Revises: 0003_hiff_timetable
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_hiff_letterboxd_genres"
down_revision: str | None = "0003_hiff_timetable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("hiff_movies", sa.Column("genres", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("hiff_movies", "genres")
