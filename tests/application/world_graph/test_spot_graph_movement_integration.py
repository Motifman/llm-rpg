from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

import pytest

from ai_rpg_world.application.world_graph.spot_graph_movement_application_service import (
    SpotGraphMovementApplicationService,
)
from ai_rpg_world.application.world_graph.spot_graph_travel_stage_service import (
    SpotGraphTravelStageService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from tests.domain.player.aggregate.test_player_status_aggregate import create_test_status_aggregate


def _node(i: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


def _line_graph_three_spots(travel_ticks: int = 1) -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(_node(1))
    g.add_spot(_node(2))
    g.add_spot(_node(3))
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(1),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="a",
            description="",
            travel_ticks=travel_ticks,
            is_bidirectional=False,
        )
    )
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(2),
            from_spot_id=SpotId.create(2),
            to_spot_id=SpotId.create(3),
            name="b",
            description="",
            travel_ticks=travel_ticks,
            is_bidirectional=False,
        )
    )
    g.place_entity(EntityId.create(1), SpotId.create(1))
    g.clear_events()
    return g


@dataclass
class _FixedContext:
    items: FrozenSet[ItemSpecId]
    flags: FrozenSet[str]

    def owned_item_spec_ids_for(self, player_id: PlayerId) -> FrozenSet[ItemSpecId]:
        del player_id
        return self.items

    def world_flags(self) -> FrozenSet[str]:
        return self.flags


def test_start_and_tick_reaches_destination() -> None:
    graph = _line_graph_three_spots(travel_ticks=1)
    graph_repo = InMemorySpotGraphRepository(graph)
    player_repo = InMemoryPlayerStatusRepository()
    player = create_test_status_aggregate(player_id=1)
    player_repo.save(player)

    svc = SpotGraphMovementApplicationService(graph_repo, player_repo)
    ctx = _FixedContext(items=frozenset(), flags=frozenset())
    stage = SpotGraphTravelStageService(player_repo, svc, ctx)

    svc.start_travel_to_spot(PlayerId(1), SpotId.create(3), frozenset(), frozenset())

    loaded = player_repo.find_by_id(PlayerId(1))
    assert loaded is not None
    nav = loaded.spot_navigation_state
    assert nav is not None
    assert nav.is_traveling

    stage.run(WorldTick(1))
    stage.run(WorldTick(2))

    g2 = graph_repo.find_graph()
    assert g2.get_entity_spot(EntityId.create(1)) == SpotId.create(3)
    p2 = player_repo.find_by_id(PlayerId(1))
    assert p2 is not None
    assert p2.spot_navigation_state is not None
    assert not p2.spot_navigation_state.is_traveling
    assert p2.spot_navigation_state.current_spot_id == SpotId.create(3)


def test_ensure_spot_nav_syncs_from_graph() -> None:
    graph = _line_graph_three_spots()
    graph_repo = InMemorySpotGraphRepository(graph)
    player_repo = InMemoryPlayerStatusRepository()
    player_repo.save(create_test_status_aggregate(player_id=1))

    svc = SpotGraphMovementApplicationService(graph_repo, player_repo)
    svc.start_travel_to_spot(PlayerId(1), SpotId.create(2), frozenset(), frozenset())

    p = player_repo.find_by_id(PlayerId(1))
    assert p is not None
    assert p.spot_navigation_state is not None
    assert p.spot_navigation_state.is_traveling


def test_move_to_sub_location() -> None:
    graph = _line_graph_three_spots()
    graph_repo = InMemorySpotGraphRepository(graph)
    player_repo = InMemoryPlayerStatusRepository()
    player_repo.save(create_test_status_aggregate(player_id=1))

    svc = SpotGraphMovementApplicationService(graph_repo, player_repo)
    svc.move_to_sub_location(PlayerId(1), SubLocationId.create(7))

    p = player_repo.find_by_id(PlayerId(1))
    assert p is not None
    assert p.spot_navigation_state is not None
    assert p.spot_navigation_state.current_sub_location_id == SubLocationId.create(7)


def test_same_destination_no_op() -> None:
    graph = _line_graph_three_spots()
    graph_repo = InMemorySpotGraphRepository(graph)
    player_repo = InMemoryPlayerStatusRepository()
    player_repo.save(create_test_status_aggregate(player_id=1))

    svc = SpotGraphMovementApplicationService(graph_repo, player_repo)
    svc.start_travel_to_spot(PlayerId(1), SpotId.create(1), frozenset(), frozenset())

    p = player_repo.find_by_id(PlayerId(1))
    assert p is not None
    assert p.spot_navigation_state is not None
    assert not p.spot_navigation_state.is_traveling
