"""スポットグラフモードの発話配信・フォーマット"""

from unittest.mock import MagicMock

import pytest

from tests.application.observation.test_observation_recipient_resolver_extended_events import (
    _make_status,
)

from ai_rpg_world.application.observation.services.observation_formatter import (
    ObservationFormatter,
)
from ai_rpg_world.application.observation.services.observation_recipient_resolver import (
    create_observation_recipient_resolver,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)


def _node(i: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


def _build_two_spot_graph(*, perm: float = 0.5, conn_name: str = "c") -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(_node(1))
    g.add_spot(_node(2))
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(1),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name=conn_name,
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

    def test_muffled_prose_includes_source_connection_direction(self) -> None:
        """Issue #269: MUFFLED の listener prose に音の到来方向 (接続名) が含まれる。"""
        graph = _build_two_spot_graph(perm=0.5, conn_name="閲覧室の扉")
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
        assert "閲覧室の扉" in out.prose
        assert out.structured.get("source_connection_name") == "閲覧室の扉"
        # S1 が listener 側から見た方向元スポット (name_resolver で解決される)
        assert out.structured.get("source_adjacent_spot_name") == "S1"

    def test_clear_prose_has_no_direction_clause(self) -> None:
        """同 spot (CLEAR) の listener には方向情報は付与しない (冗長なため)。"""
        graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
        graph.add_spot(_node(1))
        graph.place_entity(EntityId.create(1), SpotId.create(1))
        graph.place_entity(EntityId.create(2), SpotId.create(1))
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
        assert "の向こうから" not in out.prose
        assert "source_connection_name" not in out.structured


def _spoke(channel: SpeechChannel = SpeechChannel.SAY) -> PlayerSpokeEvent:
    return PlayerSpokeEvent.create(
        aggregate_id=PlayerId(1),
        aggregate_type="PlayerStatusAggregate",
        content="水門を開けるな",
        channel=channel,
        spot_id=SpotId(1),
        speaker_coordinate=Coordinate(0, 0, 0),
        target_player_id=None,
    )


def _same_spot_formatter() -> ObservationFormatter:
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph.add_spot(_node(1))
    graph.place_entity(EntityId.create(1), SpotId.create(1))
    graph.place_entity(EntityId.create(2), SpotId.create(1))
    return ObservationFormatter(spot_graph_repository=InMemorySpotGraphRepository(graph))


class TestSpeechForListenerWhoDoesNotKnowSpeaker:
    """話し声の観測が、話し手を知らない受け手向けに、名前を伏せた本文と structured を持つことを保証する。"""

    def test_muffled_voice_has_an_anonymous_view_with_direction(self) -> None:
        """隣の場所からのぼんやりした声は、話し手の名前と組で「〈接続〉の向こうから、誰かの遠くの声が聞こえる」版を持ち、伏せた structured に話し手の名前と番号が無い。"""
        formatter = ObservationFormatter(
            spot_graph_repository=InMemorySpotGraphRepository(
                _build_two_spot_graph(perm=0.5, conn_name="西の坂道")
            )
        )

        out = formatter.format(_spoke(), PlayerId(2))

        assert out is not None and out.if_subject_unknown is not None
        assert out.subject_name == out.structured["speaker"]
        assert out.subject_name in out.prose
        assert out.if_subject_unknown.prose.startswith("〈西の坂道〉の向こうから、誰かの遠くの声が聞こえる: 「")
        assert "speaker" not in out.if_subject_unknown.structured
        assert "speaker_player_id" not in out.if_subject_unknown.structured
        assert out.if_subject_unknown.structured["sound_clarity"] == "MUFFLED"

    def test_faint_voice_has_an_anonymous_view(self) -> None:
        """かすかな声の伏せた版は「誰かの声がかすかに聞こえるが、内容ははっきりしない。」になる。"""
        formatter = ObservationFormatter(
            spot_graph_repository=InMemorySpotGraphRepository(
                _build_two_spot_graph(perm=0.2, conn_name="西の坂道")
            )
        )

        out = formatter.format(_spoke(), PlayerId(2))

        assert out is not None and out.if_subject_unknown is not None
        assert out.if_subject_unknown.prose == (
            "〈西の坂道〉の向こうから、誰かの声がかすかに聞こえるが、内容ははっきりしない。"
        )

    @pytest.mark.parametrize(
        ("channel", "verb"),
        [(SpeechChannel.SAY, "言った"), (SpeechChannel.SHOUT, "叫んだ")],
    )
    def test_clear_voice_in_the_same_place_has_an_anonymous_view(self, channel, verb) -> None:
        """同じ場所の声も、伏せた版は「誰かが言った」「誰かが叫んだ」になる。暗がりなど、同じ場所でも会っていない相手がいるため。"""
        out = _same_spot_formatter().format(_spoke(channel), PlayerId(2))

        assert out is not None and out.if_subject_unknown is not None
        assert out.if_subject_unknown.prose == f"誰かが{verb}: 「水門を開けるな」"

    def test_speaker_saying_own_name_still_yields_an_observation(self) -> None:
        """話し手が自分の名前を口にしても観測は作られ、伏せた版の本文には言った言葉がそのまま残る。声がそう言ったのは聞こえているため。"""
        formatter = _same_spot_formatter()
        speaker = formatter.format(_spoke(), PlayerId(2)).subject_name
        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            content=f"{speaker}だ、聞こえるか",
            channel=SpeechChannel.SAY,
            spot_id=SpotId(1),
            speaker_coordinate=Coordinate(0, 0, 0),
            target_player_id=None,
        )

        out = formatter.format(event, PlayerId(2))

        assert out is not None and out.if_subject_unknown is not None
        assert out.if_subject_unknown.prose == f"誰かが言った: 「{speaker}だ、聞こえるか」"
