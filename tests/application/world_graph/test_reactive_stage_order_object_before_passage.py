"""Issue #188 Step 3: reactive_object_state を reactive_passage より先に評価する。

旧順序 (passage → object) では、同 tick 内で object state の変化が passage
評価に反映されず **1 tick の grace period** を生んでいた。これは第 7 回
LLM 実験で R2 WIN を生んだ「timing exploit」の正体。

新順序 (object → passage) では、object 状態変化が即 passage に伝播するため、
同じシナリオで「operator が黙って制御室を離脱」した場合、扉が **即座に**
LOCKED となる。

検証する不変条件:
- ``ReactiveObjectStateBindingStage`` で object state を更新した結果が、
  **同じ tick の** ``ReactivePassageBindingStage`` から見える
- relay_puzzle で「operator 離脱 → object stage で power_on=false →
  passage stage で扉 LOCKED」が 1 tick 内に完結する (旧 2 tick lag が解消)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_graph.reactive_object_state_binding_stage_service import (
    ReactiveObjectStateBindingStageService,
)
from ai_rpg_world.application.world_graph.reactive_passage_binding_stage_service import (
    ReactivePassageBindingStageService,
)
from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.passage_kind import DoorStateEnum
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.reactive_object_state_binding import (
    ReactiveObjectStateBinding,
)
from ai_rpg_world.domain.world_graph.value_object.reactive_passage_binding import (
    ReactivePassageBinding,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)


def _node(i: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


def _build_world():
    """relay_puzzle 相当の最小世界: control_room (1) - corridor (2) で
    対象 connection は ID=10 (corridor → vault っぽい配置)、object_panel は ID=7。"""
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    for i in (1, 2, 3):
        g.add_spot(_node(i))
    # corridor_to_vault 相当の connection (初期 LOCKED)
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(10),
            from_spot_id=SpotId.create(2),
            to_spot_id=SpotId.create(3),
            name="vault_door",
            description="",
            travel_ticks=1,
            is_bidirectional=False,
            passage=Passage.door(DoorStateEnum.LOCKED),
        )
    )
    control_panel = SpotObject(
        object_id=SpotObjectId.create(7),
        name="control_panel",
        description="d",
        object_type=SpotObjectTypeEnum.SWITCH,
        state={"power_on": True},  # 初期 power_on
        interactions=(),
    )
    interior = SpotInterior((), (control_panel,), (), ())
    spot_graph_repo = InMemorySpotGraphRepository(g)
    interior_repo = InMemorySpotInteriorRepository()
    interior_repo.save(SpotId.create(1), interior)
    flags = MutableWorldFlagState()

    class _NoopStatusRepo:
        def find_all(self):
            return []

    class _NoopInventoryRepo:
        def find_by_id(self, *_a, **_kw):
            return None

    class _NoopItemRepo:
        pass

    evaluator = ScenarioConditionEvaluator(
        world_flag_state=flags,
        spot_interior_repository=interior_repo,
        player_status_repository=_NoopStatusRepo(),
        player_inventory_repository=_NoopInventoryRepo(),
        item_repository=_NoopItemRepo(),
    )
    return spot_graph_repo, interior_repo, flags, evaluator


def _build_stages(spot_graph_repo, interior_repo, evaluator):
    object_binding = ReactiveObjectStateBinding(
        target_object_id=SpotObjectId.create(7),
        # 制御室 (spot 1) に誰も居ない → power_on=false
        predicate=ScenarioEventCondition(
            condition_type="NOT",
            children=(
                ScenarioEventCondition(
                    condition_type="PLAYER_AT_SPOT", spot_id=1,
                ),
            ),
        ),
        on_true_state_updates=(("power_on", False),),
        on_false_state_updates=(("power_on", True),),
    )
    passage_binding = ReactivePassageBinding(
        target_connection_id=ConnectionId.create(10),
        # power_on=true なら開く
        predicate=ScenarioEventCondition(
            condition_type="OBJECT_STATE",
            object_id=7,
            required_state={"power_on": True},
        ),
        on_true_state="OPEN",
        on_false_state="LOCKED",
    )
    object_stage = ReactiveObjectStateBindingStageService(
        bindings=(object_binding,),
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=interior_repo,
        condition_evaluator=evaluator,
    )
    passage_stage = ReactivePassageBindingStageService(
        bindings=(passage_binding,),
        spot_graph_repository=spot_graph_repo,
        condition_evaluator=evaluator,
    )
    return object_stage, passage_stage


class TestReactiveStageOrderObjectBeforePassage:
    """新順序: object 評価が passage より先に走り、同 tick で連動する。"""

    def test_object_first_then_passage_reflects_in_one_tick(self) -> None:
        """object stage の power_on=false が、同 tick の passage 評価で
        即時 LOCKED に反映される。Step 3 の中核挙動。"""
        repo, interior_repo, _, evaluator = _build_world()
        object_stage, passage_stage = _build_stages(repo, interior_repo, evaluator)

        # 初期: 制御室に entity を居住させる
        g = repo.find_graph()
        g.place_entity(EntityId.create(101), SpotId.create(1))

        # 最初の tick: 制御室に人が居る → power_on=true 維持、扉 OPEN
        object_stage.run(WorldTick(1))
        passage_stage.run(WorldTick(1))
        assert g.get_connection(ConnectionId.create(10)).passage.state == "OPEN"

        # entity が制御室を離脱: unplace + place で別 spot へ強制移動。
        # (テスト目的の最短手段。実運用は travel_stage 経由の段階的移動)
        g.unplace_entity(EntityId.create(101))
        g.place_entity(EntityId.create(101), SpotId.create(2))

        # 次の tick: 制御室に誰も居ない
        # 新順序 (object → passage):
        #   1. object_stage: power_on=false に更新
        #   2. passage_stage: power_on=false で評価 → LOCKED
        # → 1 tick 内で扉が閉まる
        object_stage.run(WorldTick(2))
        passage_stage.run(WorldTick(2))
        assert g.get_connection(ConnectionId.create(10)).passage.state == "LOCKED", (
            "新順序 (object 先, passage 後) で同 tick 内に扉が LOCKED に "
            "なっていない。timing exploit の修正が効いていない可能性。"
        )

    def test_passage_uses_fresh_object_state_in_same_tick(self) -> None:
        """逆: 既に LOCKED の状態で entity が制御室に戻る → 同 tick で OPEN になる。"""
        repo, interior_repo, _, evaluator = _build_world()
        object_stage, passage_stage = _build_stages(repo, interior_repo, evaluator)

        g = repo.find_graph()
        # 初期: 誰も居ない → power_on=false / 扉 LOCKED
        object_stage.run(WorldTick(1))
        passage_stage.run(WorldTick(1))
        assert g.get_connection(ConnectionId.create(10)).passage.state == "LOCKED"

        # entity が制御室に入る
        g.place_entity(EntityId.create(101), SpotId.create(1))
        # 新順序: 1 tick で扉 OPEN
        object_stage.run(WorldTick(2))
        passage_stage.run(WorldTick(2))
        assert g.get_connection(ConnectionId.create(10)).passage.state == "OPEN"
