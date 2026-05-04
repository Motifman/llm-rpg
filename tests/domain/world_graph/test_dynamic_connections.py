"""動的な接続の生成・破壊のテスト。

SpotGraphAggregate.remove_connection() と
WorldGraphEffectService の CREATE_CONNECTION / DESTROY_CONNECTION を検証する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    ConnectionCreatedEvent,
    ConnectionDestroyedEvent,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    UnknownConnectionException,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import WorldGraphEffectService
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


def _make_graph_with_connection(bidirectional: bool = False) -> SpotGraphAggregate:
    """2スポット + 1接続のグラフを構築する。"""
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph.add_spot(SpotNode(
        spot_id=SpotId.create(1), name="Room A", description="",
        category=SpotCategoryEnum.OTHER, parent_id=None,
    ))
    graph.add_spot(SpotNode(
        spot_id=SpotId.create(2), name="Room B", description="",
        category=SpotCategoryEnum.OTHER, parent_id=None,
    ))
    conn = SpotConnection(
        connection_id=ConnectionId.create(10),
        from_spot_id=SpotId.create(1),
        to_spot_id=SpotId.create(2),
        name="通路",
        description="A→Bへの通路",
        travel_ticks=1,
        is_bidirectional=bidirectional,
    )
    rev_id = ConnectionId.create(11) if bidirectional else None
    graph.add_connection(conn, reverse_connection_id=rev_id)
    graph.clear_events()
    return graph


class TestRemoveConnectionUnidirectional:
    """単方向接続の削除テスト"""

    def test_remove_deletes_from_graph(self) -> None:
        """削除後に接続がグラフから消えること"""
        graph = _make_graph_with_connection(bidirectional=False)
        graph.remove_connection(ConnectionId.create(10))
        with pytest.raises(UnknownConnectionException):
            graph.get_connection(ConnectionId.create(10))

    def test_remove_emits_event(self) -> None:
        """削除時にConnectionDestroyedEventが発行されること"""
        graph = _make_graph_with_connection(bidirectional=False)
        graph.remove_connection(ConnectionId.create(10))
        events = [e for e in graph.get_events() if isinstance(e, ConnectionDestroyedEvent)]
        assert len(events) == 1
        assert events[0].connection_id == ConnectionId.create(10)

    def test_remove_makes_movement_impossible(self) -> None:
        """削除後にmove_entityが失敗すること"""
        graph = _make_graph_with_connection(bidirectional=False)
        eid = EntityId.create(1)
        graph.place_entity(eid, SpotId.create(1))
        graph.remove_connection(ConnectionId.create(10))
        with pytest.raises(UnknownConnectionException):
            graph.move_entity(eid, ConnectionId.create(10), frozenset(), frozenset())

    def test_outgoing_list_updated(self) -> None:
        """削除後にoutgoing接続リストから消えること"""
        graph = _make_graph_with_connection(bidirectional=False)
        graph.remove_connection(ConnectionId.create(10))
        connections = graph.iter_outgoing_connections_from(SpotId.create(1))
        assert len(connections) == 0


class TestRemoveConnectionBidirectional:
    """双方向接続の削除テスト"""

    def test_remove_deletes_both_directions(self) -> None:
        """双方向接続の削除で逆方向も消えること"""
        graph = _make_graph_with_connection(bidirectional=True)
        graph.remove_connection(ConnectionId.create(10))
        with pytest.raises(UnknownConnectionException):
            graph.get_connection(ConnectionId.create(10))
        with pytest.raises(UnknownConnectionException):
            graph.get_connection(ConnectionId.create(11))

    def test_remove_reverse_also_deletes_forward(self) -> None:
        """逆方向IDで削除しても正方向も消えること"""
        graph = _make_graph_with_connection(bidirectional=True)
        graph.remove_connection(ConnectionId.create(11))
        with pytest.raises(UnknownConnectionException):
            graph.get_connection(ConnectionId.create(10))
        with pytest.raises(UnknownConnectionException):
            graph.get_connection(ConnectionId.create(11))


class TestEffectServiceCreateConnection:
    """WorldGraphEffectService の CREATE_CONNECTION テスト"""

    def test_create_connection_spec_generated(self) -> None:
        """CREATE_CONNECTION でSpecが生成されること"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CREATE_CONNECTION,
            parameters={
                "from_spot_id": 1,
                "to_spot_id": 2,
                "connection_name": "壊した壁",
                "description": "壁を壊して通路ができた",
                "travel_ticks": 2,
                "is_bidirectional": True,
            },
        )
        result = svc.apply_effects(
            interior=SpotInterior((), (), (), ()),
            acting_object=None,
            effects=[effect],
            world_flags=frozenset(),
        )
        assert len(result.create_connection_specs) == 1
        spec = result.create_connection_specs[0]
        assert spec.from_spot_id == 1
        assert spec.to_spot_id == 2
        assert spec.connection_name == "壊した壁"
        assert spec.is_bidirectional is True
        assert spec.travel_ticks == 2

    def test_create_connection_requires_name(self) -> None:
        """connection_nameが空の場合はSpecが生成されないこと"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CREATE_CONNECTION,
            parameters={"from_spot_id": 1, "to_spot_id": 2, "connection_name": ""},
        )
        result = svc.apply_effects(
            interior=SpotInterior((), (), (), ()),
            acting_object=None,
            effects=[effect],
            world_flags=frozenset(),
        )
        assert len(result.create_connection_specs) == 0


class TestEffectServiceDestroyConnection:
    """WorldGraphEffectService の DESTROY_CONNECTION テスト"""

    def test_destroy_connection_spec_generated(self) -> None:
        """DESTROY_CONNECTION でSpecが生成されること"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.DESTROY_CONNECTION,
            parameters={"connection_id": 42},
        )
        result = svc.apply_effects(
            interior=SpotInterior((), (), (), ()),
            acting_object=None,
            effects=[effect],
            world_flags=frozenset(),
        )
        assert len(result.destroy_connection_specs) == 1
        assert result.destroy_connection_specs[0].connection_id == 42

    def test_destroy_connection_zero_id_ignored(self) -> None:
        """connection_id=0の場合はSpecが生成されないこと"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.DESTROY_CONNECTION,
            parameters={"connection_id": 0},
        )
        result = svc.apply_effects(
            interior=SpotInterior((), (), (), ()),
            acting_object=None,
            effects=[effect],
            world_flags=frozenset(),
        )
        assert len(result.destroy_connection_specs) == 0
