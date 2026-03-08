"""SqliteReflectionStatePort のテスト（永続化）"""

import pytest
from datetime import datetime

from ai_rpg_world.infrastructure.llm.sqlite_reflection_state_port import (
    SqliteReflectionStatePort,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestSqliteReflectionStatePort:
    """SqliteReflectionStatePort の永続化テスト"""

    def test_mark_and_get_last_reflection_game_day_persists(self, tmp_path):
        """mark_reflection_success した game_day がストア再作成後も get_last_reflection_game_day で取得できる"""
        db_path = tmp_path / "reflection.db"
        port = SqliteReflectionStatePort(db_path)
        player_id = PlayerId(1)
        port.mark_reflection_success(player_id, game_day=5, cursor=datetime.now())

        port2 = SqliteReflectionStatePort(db_path)
        got = port2.get_last_reflection_game_day(player_id)
        assert got == 5

    def test_cursor_persists(self, tmp_path):
        """cursor が永続化され、get_reflection_cursor で取得できる"""
        db_path = tmp_path / "reflection.db"
        port = SqliteReflectionStatePort(db_path)
        player_id = PlayerId(1)
        fixed_cursor = datetime(2025, 3, 8, 12, 0, 0)
        port.mark_reflection_success(player_id, game_day=1, cursor=fixed_cursor)

        port2 = SqliteReflectionStatePort(db_path)
        got = port2.get_reflection_cursor(player_id)
        assert got is not None
        assert got.year == 2025
        assert got.month == 3
        assert got.day == 8
