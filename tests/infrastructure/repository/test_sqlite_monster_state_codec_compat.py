"""sqlite_monster_state_codec の後方互換テスト (Phase 4a/4b 永続化)。

migration v24 未適用 (= Phase 4a/4b カラムが無い) DB から読み込んだ場合、
codec ヘルパは KeyError を握りつぶして None を返すべき。これにより
既存 DB を壊さずに新コードが動く。
"""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.infrastructure.repository.sqlite_monster_state_codec import (
    _decode_attacker_ref,
    _optional_spot_id,
    _optional_tick,
)


@pytest.fixture
def legacy_row() -> sqlite3.Row:
    """v24 未適用相当の sqlite3.Row。Phase 4a/4b カラムを持たない。"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE legacy_monsters (monster_id INTEGER, behavior_state TEXT)"
    )
    conn.execute(
        "INSERT INTO legacy_monsters (monster_id, behavior_state) VALUES (1, 'IDLE')"
    )
    cur = conn.execute("SELECT * FROM legacy_monsters WHERE monster_id = 1")
    return cur.fetchone()


class TestLegacySchemaCompat:
    """v24 未適用 row でも codec ヘルパが None を返す (KeyError を握りつぶす)。"""

    def test_optional_spot_id_returns_None_for_missing_column(
        self, legacy_row: sqlite3.Row,
    ) -> None:
        result = _optional_spot_id(
            legacy_row, "behavior_last_observed_target_spot_id"
        )
        assert result is None

    def test_optional_tick_returns_None_for_missing_column(
        self, legacy_row: sqlite3.Row,
    ) -> None:
        assert _optional_tick(legacy_row, "behavior_flee_until_tick") is None
        assert _optional_tick(legacy_row, "behavior_chase_started_at_tick") is None

    def test_decode_attacker_ref_returns_None_for_missing_column(
        self, legacy_row: sqlite3.Row,
    ) -> None:
        assert _decode_attacker_ref(legacy_row) is None


class TestCorruptionLogging:
    """DB 破損ケース (kind だけ入って ID が NULL 等) は error ログを出す。"""

    @pytest.fixture
    def corrupt_kind_only_row(self) -> sqlite3.Row:
        """kind=player だが player_id が NULL の不整合 row。"""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE corrupt (
                behavior_chase_attacker_ref_kind TEXT,
                behavior_chase_attacker_ref_player_id INTEGER,
                behavior_chase_attacker_ref_monster_id INTEGER
            )
            """
        )
        conn.execute(
            "INSERT INTO corrupt VALUES ('player', NULL, NULL)"
        )
        cur = conn.execute("SELECT * FROM corrupt")
        return cur.fetchone()

    def test_player_kind_with_null_id_returns_None_and_logs_error(
        self, corrupt_kind_only_row: sqlite3.Row, caplog,
    ) -> None:
        """kind=player + player_id=NULL は None を返し、error ログを出す。"""
        import logging
        with caplog.at_level(logging.ERROR):
            result = _decode_attacker_ref(corrupt_kind_only_row)
        assert result is None
        assert any(
            "AttackerRef DB corruption" in record.message
            for record in caplog.records
        )

    def test_unknown_kind_returns_None_and_logs_error(self, caplog) -> None:
        """`kind` が想定外の文字列なら None を返して error ログ。"""
        import logging

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE corrupt (
                behavior_chase_attacker_ref_kind TEXT,
                behavior_chase_attacker_ref_player_id INTEGER,
                behavior_chase_attacker_ref_monster_id INTEGER
            )
            """
        )
        conn.execute("INSERT INTO corrupt VALUES ('alien', NULL, NULL)")
        row = conn.execute("SELECT * FROM corrupt").fetchone()

        with caplog.at_level(logging.ERROR):
            result = _decode_attacker_ref(row)
        assert result is None
        assert any(
            "unknown kind" in record.message for record in caplog.records
        )
