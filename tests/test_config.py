from pathlib import Path

from fi_movies.config import Settings


def test_tmdb_env_token_wins_over_file(tmp_path: Path) -> None:
    token_file = tmp_path / "TOKEN"
    token_file.write_text("file-token\n", encoding="utf-8")

    settings = Settings(tmdb_read_access_token="env-token", tmdb_read_access_token_file=str(token_file))

    assert settings.resolved_tmdb_read_access_token == "env-token"


def test_tmdb_token_can_be_read_from_file(tmp_path: Path) -> None:
    token_file = tmp_path / "TOKEN"
    token_file.write_text("file-token\n", encoding="utf-8")

    settings = Settings(tmdb_read_access_token_file=str(token_file))

    assert settings.resolved_tmdb_read_access_token == "file-token"
