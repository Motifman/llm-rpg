"""SpotGraphAggregate.teleport_entity が接続を使わない移動を成立させることを保証する。

`TELEPORT_ENTITY` 効果 (隠し通路・ベント・魔法陣) は接続を辿らずに別スポットへ
飛ぶ。`move_entity` は ConnectionId を要求し通行判定も行うため使えない。
本メソッドは presence の付け替えと Left → Entered の発火だけを行い、通行条件を
評価しない点が move_entity と異なる。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    EntityEnteredSpotEvent,
    EntityLeftSpotEvent,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    EntityNotAtSpotException,
    EntityNotInGraphException,
    SpotNotInGraphException,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


def _node(i: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


def _graph_with_connection() -> SpotGraphAggregate:
    """S1 → S2 の接続を 1 本持つグラフ (接続移動との衝突検証用)。"""
    return SpotGraphAggregate(
        graph_id=SpotGraphId.create(1),
        spots={
            SpotId.create(1): _node(1),
            SpotId.create(2): _node(2),
            SpotId.create(3): _node(3),
        },
        connections_by_id={
            ConnectionId.create(1): SpotConnection(
                connection_id=ConnectionId.create(1),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="door",
                description="d",
                travel_ticks=1,
                is_bidirectional=False,
            ),
        },
    )


def _graph_without_connections() -> SpotGraphAggregate:
    """接続を 1 本も持たない 2 スポットのグラフ (テレポート専用の検証用)。"""
    return SpotGraphAggregate(
        graph_id=SpotGraphId.create(1),
        spots={SpotId.create(1): _node(1), SpotId.create(2): _node(2)},
        connections_by_id={},
    )


class TestTeleportEntity:
    """teleport_entity が接続なしで entity を移し、目撃可能なイベントを残す。"""

    def test_entity_moves_to_target_spot_without_any_connection(self) -> None:
        """接続が 1 本も無くても、指定したスポットへ entity が移動する。"""
        graph = _graph_without_connections()
        entity = EntityId.create(1)
        graph.place_entity(entity, SpotId.create(1))
        graph.clear_events()

        graph.teleport_entity(entity, SpotId.create(2))

        assert graph.get_entity_spot(entity) == SpotId.create(2)

    def test_presence_is_moved_from_source_to_destination(self) -> None:
        """テレポート後、出発スポットの presence から消え、到着スポットに現れる。"""
        graph = _graph_without_connections()
        entity = EntityId.create(1)
        graph.place_entity(entity, SpotId.create(1))
        graph.clear_events()

        graph.teleport_entity(entity, SpotId.create(2))

        assert not graph.presence_at(SpotId.create(1)).is_present(entity)
        assert graph.presence_at(SpotId.create(2)).is_present(entity)

    def test_emits_left_then_entered_events(self) -> None:
        """出発と到着がそれぞれ観測できるよう、Left → Entered の順にイベントを発火する。"""
        graph = _graph_without_connections()
        entity = EntityId.create(1)
        graph.place_entity(entity, SpotId.create(1))
        graph.clear_events()

        graph.teleport_entity(entity, SpotId.create(2))

        events = list(graph.get_events())
        left = [e for e in events if isinstance(e, EntityLeftSpotEvent)]
        entered = [e for e in events if isinstance(e, EntityEnteredSpotEvent)]
        assert len(left) == 1
        assert len(entered) == 1
        assert events.index(left[0]) < events.index(entered[0])
        assert left[0].spot_id == SpotId.create(1)
        assert left[0].to_spot_id == SpotId.create(2)
        assert entered[0].spot_id == SpotId.create(2)
        assert entered[0].from_spot_id == SpotId.create(1)

    def test_unplaced_entity_raises(self) -> None:
        """グラフに配置されていない entity をテレポートさせると EntityNotInGraphException。"""
        graph = _graph_without_connections()

        with pytest.raises(EntityNotInGraphException):
            graph.teleport_entity(EntityId.create(99), SpotId.create(2))

    def test_unknown_destination_raises(self) -> None:
        """グラフに存在しないスポットを指定すると SpotNotInGraphException を投げ、entity は動かない。"""
        graph = _graph_without_connections()
        entity = EntityId.create(1)
        graph.place_entity(entity, SpotId.create(1))

        with pytest.raises(SpotNotInGraphException):
            graph.teleport_entity(entity, SpotId.create(999))
        assert graph.get_entity_spot(entity) == SpotId.create(1)

    def test_teleport_to_current_spot_is_noop_without_events(self) -> None:
        """現在地と同じスポットへのテレポートは何も起こさず、イベントも発火しない。

        「出発していないのに出発イベントが流れる」と、同席者に幽霊のような
        出入りが観測されてしまうため。
        """
        graph = _graph_without_connections()
        entity = EntityId.create(1)
        graph.place_entity(entity, SpotId.create(1))
        graph.clear_events()

        graph.teleport_entity(entity, SpotId.create(1))

        assert graph.get_entity_spot(entity) == SpotId.create(1)
        assert list(graph.get_events()) == []


class TestTeleportVersusConnectionMovement:
    """テレポートで位置が変わった entity に対する接続移動が破綻することを明示する。

    `PlayerSpotNavigationState` (複数 tick 移動) は本集約とは別に「どの接続を
    辿っている途中か」を保持する。移動中の entity をテレポートさせると、次の
    接続移動が「接続の始点に居ない」として失敗する。現在この経路は踏めない
    (interact は行為者自身しか飛ばせず、移動中のプレイヤーはターンが回らない)
    が、他者を飛ばす効果や trap 由来のテレポートを足すときに、この症状を
    知らないまま踏むのを防ぐために固定する。
    """

    def test_connection_move_fails_after_the_entity_was_teleported_away(self) -> None:
        """接続の始点からテレポートで離れた後に同じ接続で移動すると EntityNotAtSpotException。"""
        graph = _graph_with_connection()
        entity = EntityId.create(1)
        graph.place_entity(entity, SpotId.create(1))

        graph.teleport_entity(entity, SpotId.create(3))

        with pytest.raises(EntityNotAtSpotException):
            graph.move_entity(
                entity, ConnectionId.create(1), frozenset(), frozenset()
            )
