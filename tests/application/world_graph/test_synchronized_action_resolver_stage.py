"""SynchronizedActionResolverStageService の挙動テスト。

協力ギミック #13 の核となる resolver: 猶予窓内に必要な prepare が揃えば
on_complete を発火、超えれば on_timeout を発火し prepare をクリアする。
"""

from __future__ import annotations

from ai_rpg_world.application.world_graph.synchronized_action_registry import (
    SynchronizedActionRegistry,
)
from ai_rpg_world.application.world_graph.synchronized_action_resolver_stage_service import (
    SynchronizedActionResolverStageService,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.passage_kind import DoorStateEnum
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.synchronized_action_group import (
    SynchronizedActionGroup,
)
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


def _build_graph() -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(_node(1))
    g.add_spot(_node(2))
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(10),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="vault_door",
            description="",
            travel_ticks=1,
            is_bidirectional=False,
            passage=Passage.door(DoorStateEnum.LOCKED),
        ),
    )
    g.clear_events()
    return g


def _change_passage_to_open() -> InteractionEffect:
    return InteractionEffect(
        effect_type=InteractionEffectTypeEnum.CHANGE_PASSAGE_STATE,
        parameters={"connection_id": 10, "new_state": "OPEN"},
    )


def _set_flag(name: str) -> InteractionEffect:
    return InteractionEffect(
        effect_type=InteractionEffectTypeEnum.SET_FLAG,
        parameters={"flag_name": name},
    )


def _build_stage(group: SynchronizedActionGroup):
    """resolver stage と registry, repos を組み立てる。"""
    graph = _build_graph()
    spot_graph_repo = InMemorySpotGraphRepository(graph)
    interior_repo = InMemorySpotInteriorRepository()
    flag_state = MutableWorldFlagState()
    registry = SynchronizedActionRegistry(flag_state)
    stage = SynchronizedActionResolverStageService(
        groups=(group,),
        registry=registry,
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=interior_repo,
        world_flag_state=flag_state,
    )
    return stage, registry, spot_graph_repo, flag_state


class TestResolverCompletion:
    """全 prepare が揃ったときの on_complete 挙動。"""

    def test_completes_when_all_prepares_within_window(self) -> None:
        """window 内に全 prepare が揃えば on_complete が走る。"""
        group = SynchronizedActionGroup(
            group_id="g",
            required_action_ids=("a", "b"),
            window_ticks=2,
            on_complete=(_change_passage_to_open(), _set_flag("vault_unlocked")),
        )
        stage, registry, repo, flags = _build_stage(group)
        registry.prepare(action_id="a", player_id=1, current_tick=5)
        registry.prepare(action_id="b", player_id=2, current_tick=5)

        stage.run(WorldTick(5))
        # passage が OPEN になり flag が立つ
        assert repo.find_graph().get_connection(ConnectionId.create(10)).passage.state == "OPEN"
        assert "vault_unlocked" in flags.as_frozen_set()
        # prepare flag は全消去
        assert registry.entries_for("a") == []
        assert registry.entries_for("b") == []

    def test_completes_with_prepares_at_different_ticks_within_window(self) -> None:
        """1 tick 差でも window=2 内に揃えば完成する。"""
        group = SynchronizedActionGroup(
            group_id="g",
            required_action_ids=("a", "b"),
            window_ticks=2,
            on_complete=(_set_flag("done"),),
        )
        stage, registry, _, flags = _build_stage(group)
        registry.prepare(action_id="a", player_id=1, current_tick=5)
        registry.prepare(action_id="b", player_id=2, current_tick=6)

        stage.run(WorldTick(6))
        assert "done" in flags.as_frozen_set()


class TestResolverTimeout:
    """窓を超えたときの on_timeout 挙動。"""

    def test_timeout_clears_partial_prepares(self) -> None:
        """window 超えで prepare が揃わない場合、on_timeout を発火し flag をクリア。"""
        group = SynchronizedActionGroup(
            group_id="g",
            required_action_ids=("a", "b"),
            window_ticks=2,
            on_complete=(_set_flag("vault_unlocked"),),
            on_timeout=(_set_flag("reset_done"),),
        )
        stage, registry, _, flags = _build_stage(group)
        # tick=5 に a だけ prepare、b は来ない
        registry.prepare(action_id="a", player_id=1, current_tick=5)

        # tick=7 (5+2 = window expired) で resolve
        stage.run(WorldTick(7))
        # on_complete は走らず on_timeout が走る
        assert "vault_unlocked" not in flags.as_frozen_set()
        assert "reset_done" in flags.as_frozen_set()
        # prepare は消える
        assert registry.entries_for("a") == []

    def test_no_action_when_no_prepares(self) -> None:
        """誰も prepare していない group は何もしない（idle）。"""
        group = SynchronizedActionGroup(
            group_id="g",
            required_action_ids=("a", "b"),
            window_ticks=2,
            on_complete=(_set_flag("done"),),
            on_timeout=(_set_flag("timed_out"),),
        )
        stage, _, _, flags = _build_stage(group)
        stage.run(WorldTick(100))
        assert "done" not in flags.as_frozen_set()
        assert "timed_out" not in flags.as_frozen_set()


class TestResolverPending:
    """猶予窓内でまだ揃っていないときは何もしない。"""

    def test_pending_within_window_keeps_prepares(self) -> None:
        """window 内に prepare が部分的にあっても、まだ window 内なら待つ。"""
        group = SynchronizedActionGroup(
            group_id="g",
            required_action_ids=("a", "b"),
            window_ticks=3,
            on_complete=(_set_flag("done"),),
        )
        stage, registry, _, flags = _build_stage(group)
        registry.prepare(action_id="a", player_id=1, current_tick=5)

        # tick 6 (5+3 まで猶予あり)
        stage.run(WorldTick(6))
        assert "done" not in flags.as_frozen_set()
        # prepare は残っている
        assert len(registry.entries_for("a")) == 1


class TestResolverBoundary:
    """境界値: window_ticks=1（同 tick のみ）と窓ぴったり tick 差。"""

    def test_window_one_requires_same_tick(self) -> None:
        """window_ticks=1 で 1 tick 差ならタイムアウト扱い。"""
        group = SynchronizedActionGroup(
            group_id="g",
            required_action_ids=("a", "b"),
            window_ticks=1,
            on_complete=(_set_flag("done"),),
            on_timeout=(_set_flag("timed_out"),),
        )
        stage, registry, _, flags = _build_stage(group)
        registry.prepare(action_id="a", player_id=1, current_tick=5)
        registry.prepare(action_id="b", player_id=2, current_tick=6)

        stage.run(WorldTick(6))
        # oldest=5, current=6 → 1 < 1 = False → timeout
        assert "done" not in flags.as_frozen_set()
        assert "timed_out" in flags.as_frozen_set()

    def test_window_one_same_tick_completes(self) -> None:
        """window_ticks=1 で同 tick 完成は OK。"""
        group = SynchronizedActionGroup(
            group_id="g",
            required_action_ids=("a", "b"),
            window_ticks=1,
            on_complete=(_set_flag("done"),),
        )
        stage, registry, _, flags = _build_stage(group)
        registry.prepare(action_id="a", player_id=1, current_tick=5)
        registry.prepare(action_id="b", player_id=2, current_tick=5)

        stage.run(WorldTick(5))
        assert "done" in flags.as_frozen_set()

    def test_unsupported_effect_logs_warning(self, caplog) -> None:
        """on_complete に CHANGE_OBJECT_STATE のような非対応 effect があれば warning ログ。"""
        from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
            InteractionEffectTypeEnum,
        )
        from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
            InteractionEffect,
        )
        unsupported = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_OBJECT_STATE,
            parameters={"state_updates": {}},
        )
        group = SynchronizedActionGroup(
            group_id="g",
            required_action_ids=("a", "b"),
            window_ticks=2,
            on_complete=(unsupported, _set_flag("done")),
        )
        stage, registry, _, flags = _build_stage(group)
        registry.prepare(action_id="a", player_id=1, current_tick=3)
        registry.prepare(action_id="b", player_id=2, current_tick=3)

        with caplog.at_level("WARNING"):
            stage.run(WorldTick(3))
        # SET_FLAG は走り、CHANGE_OBJECT_STATE は warning が出る
        assert "done" in flags.as_frozen_set()
        assert any("CHANGE_OBJECT_STATE" in r.message for r in caplog.records)
