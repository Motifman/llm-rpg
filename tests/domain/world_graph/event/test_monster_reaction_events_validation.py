"""追跡開始イベントはプレイヤーとモンスターの対象を片方だけ受け付ける。

有効な2状態を構築でき、対象なし・両方指定の2状態を生成時に拒否する。
理由の保持は公開formatter、逃走の識別子は実ハンドラ発火の試験で保証する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterStartedChasingInSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId

GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)
MONSTER_1 = MonsterId.create(101)


class TestStartedChasingValidation:
    """MonsterStartedChasingInSpotEvent の discriminated union バリデーション。"""

    def test_player_target_non_none_ok(self) -> None:
        """player target だけ非None は OK。"""
        ev = MonsterStartedChasingInSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_1,
            spot_id=SPOT_A,
            target_player_id=EntityId.create(7),
        )
        assert ev.target_player_id is not None
        assert ev.target_monster_id is None

    def test_monster_target_non_none_ok(self) -> None:
        """monster target だけ非None は OK。"""
        ev = MonsterStartedChasingInSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_1,
            spot_id=SPOT_A,
            target_monster_id=MonsterId.create(202),
        )
        assert ev.target_monster_id is not None
        assert ev.target_player_id is None

    def test_no_target_raises_value_error(self) -> None:
        """両方None は ValueError。"""
        with pytest.raises(ValueError, match="片方だけ非 None"):
            MonsterStartedChasingInSpotEvent.create(
                aggregate_id=GRAPH_ID,
                aggregate_type="SpotGraphAggregate",
                monster_id=MONSTER_1,
                spot_id=SPOT_A,
            )

    def test_both_targets_raise_value_error(self) -> None:
        """両方非None は ValueError。"""
        with pytest.raises(ValueError, match="片方だけ非 None"):
            MonsterStartedChasingInSpotEvent.create(
                aggregate_id=GRAPH_ID,
                aggregate_type="SpotGraphAggregate",
                monster_id=MONSTER_1,
                spot_id=SPOT_A,
                target_player_id=EntityId.create(7),
                target_monster_id=MonsterId.create(202),
            )
