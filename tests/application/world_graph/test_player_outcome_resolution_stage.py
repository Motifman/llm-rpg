"""PlayerOutcomeResolutionStageService の挙動検証 (Phase E-3b)。

RESCUED (signal_fire + at summit) / STRANDED (tick 上限超え) の遷移、
tick 飛び (skip) の catch-up、既 DEAD の保護を確認する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.world_graph.player_outcome_resolution_stage_service import (
    PlayerOutcomeResolutionStageService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode


SUMMIT = SpotId.create(100)
BEACH = SpotId.create(200)
SIGNAL_FLAG = "signal_fire_lit"


def _make_graph_with_summit() -> SpotGraphAggregate:
    """summit + beach の最小グラフ。"""
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(SpotNode(
        spot_id=SUMMIT, name="山頂", description="山頂",
        category=SpotCategoryEnum.FIELD, parent_id=None,
    ))
    g.add_spot(SpotNode(
        spot_id=BEACH, name="浜辺", description="浜辺",
        category=SpotCategoryEnum.FIELD, parent_id=None,
    ))
    return g


def _make_stage(
    registry: PlayerOutcomeRegistry,
    graph: SpotGraphAggregate,
    flags: frozenset[str],
    player_ids: list[PlayerId],
    rescue_at_ticks=(10, 20),
    stranded_at_tick=30,
) -> PlayerOutcomeResolutionStageService:
    return PlayerOutcomeResolutionStageService(
        outcome_registry=registry,
        rescue_at_ticks=rescue_at_ticks,
        stranded_at_tick=stranded_at_tick,
        summit_spot_id=SUMMIT,
        signal_fire_flag=SIGNAL_FLAG,
        graph_provider=lambda: graph,
        flags_provider=lambda: flags,
        player_ids=player_ids,
    )


def _place_at(graph: SpotGraphAggregate, player_id: PlayerId, spot_id: SpotId) -> None:
    eid = EntityId.create(int(player_id))
    graph.place_entity(eid, spot_id)


class TestRescuePath:
    """signal_fire_lit + summit に居るプレイヤーが RESCUED に確定する。"""

    def test_signal_lit_AND_at_summit_なら_RESCUED(self) -> None:
        graph = _make_graph_with_summit()
        _place_at(graph, PlayerId(1), SUMMIT)
        registry = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        stage = _make_stage(registry, graph, frozenset({SIGNAL_FLAG}), [PlayerId(1)])

        stage.run(WorldTick(10))

        assert registry.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.RESCUED

    def test_signal_未点火なら_RESCUED_されない(self) -> None:
        graph = _make_graph_with_summit()
        _place_at(graph, PlayerId(1), SUMMIT)
        registry = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        stage = _make_stage(registry, graph, frozenset(), [PlayerId(1)])

        stage.run(WorldTick(10))

        assert registry.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.UNRESOLVED

    def test_summit_に居ないプレイヤーは_RESCUED_されない(self) -> None:
        graph = _make_graph_with_summit()
        _place_at(graph, PlayerId(1), BEACH)
        registry = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        stage = _make_stage(registry, graph, frozenset({SIGNAL_FLAG}), [PlayerId(1)])

        stage.run(WorldTick(10))

        assert registry.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.UNRESOLVED

    def test_既_DEAD_のプレイヤーは_RESCUED_に上書きされない(self) -> None:
        graph = _make_graph_with_summit()
        _place_at(graph, PlayerId(1), SUMMIT)
        registry = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        registry.set_outcome(PlayerId(1), PlayerOutcomeEnum.DEAD)
        stage = _make_stage(registry, graph, frozenset({SIGNAL_FLAG}), [PlayerId(1)])

        stage.run(WorldTick(10))

        assert registry.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.DEAD


class TestStrandedPath:
    """tick 上限到達時に残 UNRESOLVED が STRANDED に。"""

    def test_stranded_tick_到達で_UNRESOLVED_は_STRANDED(self) -> None:
        graph = _make_graph_with_summit()
        registry = PlayerOutcomeRegistry.new_for_players([PlayerId(1), PlayerId(2)])
        stage = _make_stage(registry, graph, frozenset(), [PlayerId(1), PlayerId(2)])

        stage.run(WorldTick(30))

        assert registry.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.STRANDED
        assert registry.get_outcome(PlayerId(2)) is PlayerOutcomeEnum.STRANDED

    def test_既_RESCUED_は_STRANDED_に上書きされない(self) -> None:
        graph = _make_graph_with_summit()
        registry = PlayerOutcomeRegistry.new_for_players([PlayerId(1), PlayerId(2)])
        registry.set_outcome(PlayerId(1), PlayerOutcomeEnum.RESCUED)
        stage = _make_stage(registry, graph, frozenset(), [PlayerId(1), PlayerId(2)])

        stage.run(WorldTick(30))

        assert registry.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.RESCUED
        assert registry.get_outcome(PlayerId(2)) is PlayerOutcomeEnum.STRANDED


class TestIdempotency:
    """rescue tick / stranded tick の二重発火が起きない。"""

    def test_同じ_rescue_tick_を_2_回_run_しても_変化しない(self) -> None:
        graph = _make_graph_with_summit()
        _place_at(graph, PlayerId(1), SUMMIT)
        registry = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        calls: list[tuple] = []
        registry.register_callback(lambda pid, old, new: calls.append((int(pid), new.value)))
        stage = _make_stage(registry, graph, frozenset({SIGNAL_FLAG}), [PlayerId(1)])

        stage.run(WorldTick(10))
        stage.run(WorldTick(10))
        stage.run(WorldTick(15))

        assert calls == [(1, "RESCUED")]

    def test_tick_飛び_でも_過去の_rescue_tick_が_catch_up_される(self) -> None:
        """tick=5 から tick=25 に飛んでも tick=10 / 20 の rescue 判定が走る。"""
        graph = _make_graph_with_summit()
        _place_at(graph, PlayerId(1), SUMMIT)
        registry = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        stage = _make_stage(
            registry, graph, frozenset({SIGNAL_FLAG}), [PlayerId(1)],
            rescue_at_ticks=(10, 20),
        )

        stage.run(WorldTick(25))

        # tick=10 の rescue が catch-up され、結果として RESCUED 確定
        assert registry.get_outcome(PlayerId(1)) is PlayerOutcomeEnum.RESCUED
