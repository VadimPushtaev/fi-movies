"""Store TMDB IDs for direct Letterboxd film links."""

import sqlalchemy as sa
from alembic import op

revision = "0002_movie_tmdb_id"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("movies", sa.Column("tmdb_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("movies", "tmdb_id")
