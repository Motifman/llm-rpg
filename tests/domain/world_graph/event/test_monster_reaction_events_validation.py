"""モンスター状態遷移 event のバリデーションテスト (Phase 4-O A)。

検証対象:
- `MonsterStartedChasingInSpotEvent.__post_init__` で discriminated union
  (target_player_id / target_monster_id 片方のみ非 None) を強制する
- `MonsterAbandonedChaseInSpotEvent.reason` の Literal 型は静的に弾かれる
  (実行時テストでは典型値のみ)
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAbandonedChaseInSpotEvent,
    MonsterStartedChasingInSpotEvent,
    MonsterStartedFleeingInSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)
MONSTER_1 = MonsterId.create(101)


class TestStartedChasingValidation:
    """MonsterStartedChasingInSpotEvent の discriminated union バリデーション。"""

    def test_player_target_だけ非None_は_OK(self) -> None:
        ev = MonsterStartedChasingInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_1, spot_id=SPOT_A,
            target_player_id=EntityId.create(7),
        )
        assert ev.target_player_id is not None
        assert ev.target_monster_id is None

    def test_monster_target_だけ非None_は_OK(self) -> None:
        ev = MonsterStartedChasingInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_1, spot_id=SPOT_A,
            target_monster_id=MonsterId.create(202),
        )
        assert ev.target_monster_id is not None
        assert ev.target_player_id is None

    def test_両方None_は_ValueError(self) -> None:
        with pytest.raises(ValueError, match="片方だけ非 None"):
            MonsterStartedChasingInSpotEvent.create(
                aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
                monster_id=MONSTER_1, spot_id=SPOT_A,
            )

    def test_両方非None_は_ValueError(self) -> None:
        with pytest.raises(ValueError, match="片方だけ非 None"):
            MonsterStartedChasingInSpotEvent.create(
                aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
                monster_id=MONSTER_1, spot_id=SPOT_A,
                target_player_id=EntityId.create(7),
                target_monster_id=MonsterId.create(202),
            )


class TestAbandonedChaseReason:
    """`reason` は Literal 型 (実行時 enum 値ではないので各値の構築テストのみ)。"""

    @pytest.mark.parametrize(
        "reason",
        [
            "grace_expired",
            "max_ticks_exceeded",
            "target_lost",
            "search_expired",
            "no_path",
        ],
    )
    def test_全_AbandonChaseReason_値で_event_構築できる(
        self, reason: str,
    ) -> None:
        """5 種の reason が問題なく構築できる (Literal 型は実行時 check 無し
        だが、handler / formatter が同じ文字列を使うことを保証する)。"""
        ev = MonsterAbandonedChaseInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_1, spot_id=SPOT_A, reason=reason,
        )
        assert ev.reason == reason


class TestStartedFleeingShape:
    """MonsterStartedFleeingInSpotEvent は単純な shape のみ。"""

    def test_最小フィールドで_構築できる(self) -> None:
        ev = MonsterStartedFleeingInSpotEvent.create(
            aggregate_id=GRAPH_ID, aggregate_type="SpotGraphAggregate",
            monster_id=MONSTER_1, spot_id=SPOT_A,
        )
        assert ev.monster_id == MONSTER_1
        assert ev.spot_id == SPOT_A
