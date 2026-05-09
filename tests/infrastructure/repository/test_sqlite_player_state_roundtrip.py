"""Phase 4-D-2 PR 1: PlayerStatusAggregate.state の sqlite 永続化検証。

migration v23 で追加した state_json 列が、save → reload で state を
正しく復元することを保証する。空 dict は NULL に保存される storage 節約
の挙動も検証 (item instance state v22 と同形)。
"""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_status_write_repository import (
    SqlitePlayerStatusWriteRepository,
)


def _build_status(state: dict | None = None) -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(1),
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=80, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
        state=state,
    )


@pytest.fixture
def sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_game_write_schema(conn)
    conn.commit()
    return conn


class TestPlayerStateRoundtrip:
    """state を持った PlayerStatusAggregate が save → reload で復元される。"""

    def test_save_and_reload_preserves_state(self, sqlite_conn) -> None:
        """非空 state を保存→再読込で state_json 経由で復元できる。"""
        repo = SqlitePlayerStatusWriteRepository.for_standalone_connection(sqlite_conn)
        status = _build_status(state={
            "alignment": "good",
            "disguise": "noble",
            "reputation": 5,
            "fire_resist": True,
        })

        repo.save(status)

        loaded = repo.find_by_id(PlayerId(1))
        assert loaded is not None
        assert loaded.state == {
            "alignment": "good",
            "disguise": "noble",
            "reputation": 5,
            "fire_resist": True,
        }

    def test_save_and_reload_empty_state_returns_empty_dict(self, sqlite_conn) -> None:
        """state が空のときは NULL に保存され、復元時は空 dict として返る。"""
        repo = SqlitePlayerStatusWriteRepository.for_standalone_connection(sqlite_conn)
        status = _build_status()  # state なし

        repo.save(status)

        loaded = repo.find_by_id(PlayerId(1))
        assert loaded is not None
        assert loaded.state == {}

    def test_state_overwrite_is_persisted(self, sqlite_conn) -> None:
        """save 後に state を変えて再 save すると上書きされる。"""
        repo = SqlitePlayerStatusWriteRepository.for_standalone_connection(sqlite_conn)
        status = _build_status(state={"alignment": "good"})
        repo.save(status)

        # 再読込して state を変更し再 save
        reloaded = repo.find_by_id(PlayerId(1))
        assert reloaded is not None
        reloaded.replace_state({"alignment": "evil", "curse": "weakness"})
        repo.save(reloaded)

        # 3 度目に読み直すと最新が見える
        final = repo.find_by_id(PlayerId(1))
        assert final is not None
        assert final.state == {"alignment": "evil", "curse": "weakness"}

    def test_empty_state_after_clearing(self, sqlite_conn) -> None:
        """非空 state を空に戻して save すると、NULL に書き戻される (空 dict 復元)。"""
        repo = SqlitePlayerStatusWriteRepository.for_standalone_connection(sqlite_conn)
        status = _build_status(state={"buff": "haste"})
        repo.save(status)

        reloaded = repo.find_by_id(PlayerId(1))
        reloaded.replace_state({})
        repo.save(reloaded)

        final = repo.find_by_id(PlayerId(1))
        assert final.state == {}
