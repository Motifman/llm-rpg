"""Issue #227: speech_say (NORMAL/SAY) が max_hops=1 を超えて届くかの再現テスト。

第13回実験 (#223) で、master_study (5 hops away) のカイトが
reading_room のリンに speech_say を送り、リンが直後に応答 speech を
返したのが観測された。BFS / strategy は本来 1 hop までしか配信しない
はずだが、実機で 5 hop 先まで届いている。

本テストは:
1. SoundPropagationService の BFS を 0〜5 hop で検証 (純粋ロジック層)
2. create_observation_recipient_resolver().resolve() を 0〜5 hop で検証
   (wiring 経由で本物の strategy が選ばれる)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.observation.services.observation_recipient_resolver import (
    create_observation_recipient_resolver,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.sound_volume import SoundVolumeEnum
from ai_rpg_world.domain.world_graph.service.sound_propagation_service import (
    SoundPropagationService,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import (
    InMemoryDataStore,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)

from tests.application.observation.test_observation_recipient_resolver_extended_events import (
    _make_status,
)


def _build_linear_graph(distance: int) -> tuple[SpotGraphAggregate, list[SpotId]]:
    """speaker spot=1, listener spot=(distance+1) の直列グラフ。

    1 -> 2 -> 3 -> ... -> N を双方向で繋ぐ。両端のスポット数 = distance+1。
    """
    n = max(distance + 1, 2)
    g = SpotGraphAggregate(graph_id=SpotGraphId.create(1))
    sids: list[SpotId] = []
    for i in range(n):
        sid = SpotId.create(i + 1)
        sids.append(sid)
        g.add_spot(
            SpotNode(
                spot_id=sid,
                name=f"S{i}",
                description="",
                category=SpotCategoryEnum.OTHER,
                parent_id=None,
            )
        )
    cid = 0
    for i in range(n - 1):
        cid += 1
        fwd = ConnectionId.create(cid)
        cid += 1
        rev = ConnectionId.create(cid)
        g.add_connection(
            SpotConnection(
                connection_id=fwd,
                from_spot_id=sids[i],
                to_spot_id=sids[i + 1],
                name=f"e{i}",
                description="",
                travel_ticks=1,
                is_bidirectional=True,
                passage=Passage.open(),
            ),
            reverse_connection_id=rev,
        )
    g.place_entity(EntityId.create(1), sids[0])
    g.place_entity(EntityId.create(2), sids[distance])
    return g, sids


class TestSoundPropagationBFS:
    """SoundPropagationService が hop 数を正しく cap するか。"""

    @pytest.mark.parametrize(
        "distance,expected_ids",
        [
            (0, [1, 2]),
            (1, [1, 2]),
            (2, [1]),
            (3, [1]),
            (4, [1]),
            (5, [1]),
        ],
    )
    def test_say_は_1_hop_までしか届かない(
        self, distance: int, expected_ids: list[int]
    ) -> None:
        """NORMAL (SAY) は max_hops=1 で listener が 2 hop 以上なら届かない。"""
        graph, _ = _build_linear_graph(distance)
        svc = SoundPropagationService()
        recipients = svc.resolve_recipients(
            EntityId.create(1), SoundVolumeEnum.NORMAL, graph
        )
        ids = sorted(r.entity_id.value for r in recipients)
        assert ids == expected_ids

    @pytest.mark.parametrize(
        "distance,expected_ids",
        [
            (0, [1, 2]),
            (1, [1, 2]),
            (2, [1, 2]),
            (3, [1]),
            (4, [1]),
            (5, [1]),
        ],
    )
    def test_shout_は_2_hop_までしか届かない(
        self, distance: int, expected_ids: list[int]
    ) -> None:
        """SHOUT は max_hops=2 で listener が 3 hop 以上なら届かない。"""
        graph, _ = _build_linear_graph(distance)
        svc = SoundPropagationService()
        recipients = svc.resolve_recipients(
            EntityId.create(1), SoundVolumeEnum.SHOUT, graph
        )
        ids = sorted(r.entity_id.value for r in recipients)
        assert ids == expected_ids


class TestObservationRecipientResolverSpeech:
    """wiring で組み立てた本物の resolver が hop 制限を尊重するか。"""

    @pytest.mark.parametrize(
        "distance,expected_ids",
        [
            (0, {1, 2}),
            (1, {1, 2}),
            (2, {1}),
            (3, {1}),
            (4, {1}),
            (5, {1}),
        ],
    )
    def test_say_は_1_hop_までしか届かない_resolver経由(
        self, distance: int, expected_ids: set[int]
    ) -> None:
        """create_observation_recipient_resolver 経由でも SAY は max_hops=1。"""
        graph, sids = _build_linear_graph(distance)
        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store=data_store)
        # speaker (player 1) は spot 1 (= sids[0]) に
        status_repo.save(_make_status(1, sids[0].value, Coordinate(0, 0, 0)))
        # listener (player 2) は spot (distance+1) に
        status_repo.save(_make_status(2, sids[distance].value, Coordinate(0, 0, 0)))
        spot_repo = InMemorySpotGraphRepository(graph)
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=MagicMock(),
            spot_graph_repository=spot_repo,
        )
        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            content="hello",
            channel=SpeechChannel.SAY,
            spot_id=sids[0],
            speaker_coordinate=Coordinate(0, 0, 0),
            target_player_id=None,
        )
        pids = {p.value for p in resolver.resolve(event)}
        assert pids == expected_ids
