"""game_db_path ヘルパの境界値"""

from pathlib import Path

from ai_rpg_world.infrastructure.repository.game_db_path import (
    get_game_db_path_from_env,
)


class TestGetGameDbPathFromEnv:
    def test_missing_and_empty_returns_none(self) -> None:
        assert get_game_db_path_from_env(environ={}) is None
        assert get_game_db_path_from_env(environ={"GAME_DB_PATH": ""}) is None
        assert get_game_db_path_from_env(environ={"GAME_DB_PATH": "  "}) is None

    def test_resolves_relative_path(self, tmp_path: Path) -> None:
        db = tmp_path / "nested" / "a.db"
        raw = str(db)
        got = get_game_db_path_from_env(environ={"GAME_DB_PATH": raw})
        assert got == str(db.resolve())
