from __future__ import annotations

from ai_rpg_world.application.world_graph.spot_graph_actor_stage_service import (
    SpotGraphActorStageService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_actor_rule import (
    SpotGraphActorRule,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)


def _build_graph() -> SpotGraphAggregate:
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    a = SpotId.create(1)
    b = SpotId.create(2)
    graph.add_spot(
        SpotNode(
            spot_id=a,
            name="A",
            description="A",
            category=SpotCategoryEnum.OTHER,
            parent_id=None,
        )
    )
    graph.add_spot(
        SpotNode(
            spot_id=b,
            name="B",
            description="B",
            category=SpotCategoryEnum.OTHER,
            parent_id=None,
        )
    )
    graph.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(1),
            from_spot_id=a,
            to_spot_id=b,
            name="A->B",
            description="",
            travel_ticks=1,
            is_bidirectional=True,
            passage_conditions=(),
            sound_permeability=1.0,
            is_passable=True,
        ),
        reverse_connection_id=ConnectionId.create(2),
    )
    graph.place_entity(EntityId.create(99), a)
    graph.clear_events()
    return graph


def test_actor_stage_moves_entity_on_tick() -> None:
    repo = InMemorySpotGraphRepository(_build_graph())
    rule = SpotGraphActorRule(entity_id=99, patrol_route_spot_ids=(1, 2), move_every_ticks=2)
    stage = SpotGraphActorStageService(spot_graph_repository=repo, actor_rules=(rule,))

    stage.run(WorldTick(1), frozenset())
    assert repo.find_graph().get_entity_spot(EntityId.create(99)) == SpotId.create(1)

    stage.run(WorldTick(2), frozenset())
    assert repo.find_graph().get_entity_spot(EntityId.create(99)) == SpotId.create(2)
