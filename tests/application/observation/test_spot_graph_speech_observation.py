"""スポットグラフモードの発話配信・フォーマット"""

from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.observation_formatter import (
    ObservationFormatter,
)
from ai_rpg_world.application.observation.services.observation_recipient_resolver import (
    create_observation_recipient_resolver,
)
from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from tests.application.observation.test_observation_recipient_resolver_extended_events import (
    _make_status,
)


def _node(i: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


def _build_two_spot_graph(*, perm: float = 0.5) -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(_node(1))
    g.add_spot(_node(2))
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(1),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="c",
            description="",
            travel_ticks=1,
            is_bidirectional=False,
            passage=Passage.open(sound_permeability=perm),
        )
    )
    g.place_entity(EntityId.create(1), SpotId.create(1))
    g.place_entity(EntityId.create(2), SpotId.create(2))
    return g


class TestSpotGraphSpeechRecipientResolver:
    def test_say_uses_graph_when_speaker_in_graph(self) -> None:
        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store=data_store)
        status_repo.save(_make_status(1, 1, Coordinate(0, 0, 0)))
        status_repo.save(_make_status(2, 1, Coordinate(1, 0, 0)))
        graph = _build_two_spot_graph(perm=1.0)
        spot_repo = InMemorySpotGraphRepository(graph)
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=MagicMock(),
            spot_graph_repository=spot_repo,
        )
        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            content="こんにちは",
            channel=SpeechChannel.SAY,
            spot_id=SpotId(1),
            speaker_coordinate=Coordinate(0, 0, 0),
            target_player_id=None,
        )
        assert {p.value for p in resolver.resolve(event)} == {1, 2}

    def test_speaker_not_in_graph_falls_back_to_tile_speech(self) -> None:
        g = _build_two_spot_graph()
        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store=data_store)
        status_repo.save(_make_status(3, 1, Coordinate(0, 0, 0)))
        status_repo.save(_make_status(4, 1, Coordinate(2, 0, 0)))
        spot_repo = InMemorySpotGraphRepository(g)
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=MagicMock(),
            spot_graph_repository=spot_repo,
        )
        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(3),
            aggregate_type="PlayerStatusAggregate",
            content="こんにちは",
            channel=SpeechChannel.SAY,
            spot_id=SpotId(1),
            speaker_coordinate=Coordinate(0, 0, 0),
            target_player_id=None,
        )
        assert {p.value for p in resolver.resolve(event)} == {3, 4}


class TestSpotGraphSpeechFormatter:
    def test_muffled_prose_when_spot_graph_configured(self) -> None:
        graph = _build_two_spot_graph(perm=0.5)
        spot_repo = InMemorySpotGraphRepository(graph)
        formatter = ObservationFormatter(spot_graph_repository=spot_repo)
        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            content="やあ",
            channel=SpeechChannel.SAY,
            spot_id=SpotId(1),
            speaker_coordinate=Coordinate(0, 0, 0),
            target_player_id=None,
        )
        out = formatter.format(event, PlayerId(2))
        assert out is not None
        assert "遠くの声" in out.prose
        assert out.structured.get("sound_clarity") == "MUFFLED"
