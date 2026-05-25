"""実シナリオ forbidden_library_demo で speech 距離挙動を再現する。

Issue #227 の調査として、実際の試走と同じ topology (8 spot, リン spawn=
reading_room, カイト spawn=entrance_hall) で master_study から speech_say
を発信したとき、リン (reading_room) が観測を受け取るかを直接確認する。

Pipeline 経路 (resolver + formatter 両方) で 5 hop 先のリンに観測が
出力されないことを assert する。出力されればそれが #227 のバグ箇所。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.observation.services.observation_formatter import (
    ObservationFormatter,
)
from ai_rpg_world.application.observation.services.observation_pipeline import (
    ObservationPipeline,
)
from ai_rpg_world.application.observation.services.observation_recipient_resolver import (
    create_observation_recipient_resolver,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import (
    InMemoryDataStore,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

from tests.application.observation.test_observation_recipient_resolver_extended_events import (
    _make_status,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
SCENARIO_PATH = REPO_ROOT / "data" / "scenarios" / "forbidden_library_demo.json"


def _build_world():
    """forbidden_library_demo を読み込み、speaker=master_study / listener=
    reading_room の配置で必要なリポジトリ群を準備する。"""
    result = ScenarioLoader().load_from_file(SCENARIO_PATH)
    graph = result.graph

    # spot_name -> spot_id を逆引き
    name_to_id = {}
    for sn in graph.iter_spot_nodes():
        name_to_id[sn.name] = sn.spot_id

    master_study_id = name_to_id["館長書斎"]
    reading_room_id = name_to_id["閲覧室"]

    # speaker (player 1, カイト) を master_study に置く
    graph.place_entity(EntityId.create(1), master_study_id)
    # listener (player 2, リン) を reading_room に置く
    graph.place_entity(EntityId.create(2), reading_room_id)

    # PlayerStatus を作る (両プレイヤー、current_spot_id を上記に合わせる)
    data_store = InMemoryDataStore()
    status_repo = InMemoryPlayerStatusRepository(data_store=data_store)
    status_repo.save(_make_status(1, master_study_id.value, Coordinate(0, 0, 0)))
    status_repo.save(_make_status(2, reading_room_id.value, Coordinate(0, 0, 0)))

    spot_repo = InMemorySpotGraphRepository(graph)
    return result, graph, status_repo, spot_repo, master_study_id, reading_room_id


class TestForbiddenLibrarySpeechFromMasterStudy:
    """実シナリオの spot graph で speech の到達範囲を観察する。"""

    def test_master_study_からの_say_は_5_hop_先の_reading_room_に届かない_resolver_層(
        self,
    ) -> None:
        """resolver 層: speaker=master_study / listener=reading_room (5 hop)
        のとき、resolve() の戻り値に listener が含まれないことを assert。"""
        _, _, status_repo, spot_repo, master_study_id, _ = _build_world()
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=MagicMock(),
            spot_graph_repository=spot_repo,
        )
        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            content="リン、聞こえるか！館長書斎にたどり着いたぞ。",
            channel=SpeechChannel.SAY,
            spot_id=master_study_id,
            speaker_coordinate=Coordinate(0, 0, 0),
            target_player_id=None,
        )
        pids = {p.value for p in resolver.resolve(event)}
        # 5 hop 先のリン (player_id=2) は含まれないはず
        assert 2 not in pids, (
            f"BUG: 5 hop 先のリンが resolver 経由で recipient に含まれている: {pids}"
        )

    def test_master_study_からの_say_を_full_pipeline_で実行しても_リンに観測は出ない(
        self,
    ) -> None:
        """ObservationPipeline.run() で formatter を含むフルパスを通したとき、
        リン (5 hop 先) には ObservationOutput が出力されないはず。"""
        _, _, status_repo, spot_repo, master_study_id, _ = _build_world()
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=MagicMock(),
            spot_graph_repository=spot_repo,
        )
        formatter = ObservationFormatter(spot_graph_repository=spot_repo)
        pipeline = ObservationPipeline(
            resolver=resolver,
            formatter=formatter,
            player_status_repository=status_repo,
        )
        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            content="リン、聞こえるか！館長書斎にたどり着いたぞ。",
            channel=SpeechChannel.SAY,
            spot_id=master_study_id,
            speaker_coordinate=Coordinate(0, 0, 0),
            target_player_id=None,
        )
        outputs = pipeline.run(event)
        listener_outputs = [(pid, out) for pid, out in outputs if pid.value == 2]
        assert listener_outputs == [], (
            f"BUG: pipeline 全体で 5 hop 先のリンに観測が届いている: {listener_outputs}"
        )

    @pytest.mark.parametrize(
        "speaker_spot_name,listener_spot_name,expected_hops,should_reach",
        [
            ("入口広間", "閲覧室", 1, True),
            ("書架 A", "閲覧室", 2, False),
            ("書架 B", "閲覧室", 3, False),
            ("解読室", "閲覧室", 4, False),
            ("館長書斎", "閲覧室", 5, False),
        ],
    )
    def test_実シナリオの各スポットからの_say_到達範囲(
        self,
        speaker_spot_name: str,
        listener_spot_name: str,
        expected_hops: int,
        should_reach: bool,
    ) -> None:
        """実シナリオの spot graph で各スポット間距離での SAY 配信判定。"""
        result = ScenarioLoader().load_from_file(SCENARIO_PATH)
        graph = result.graph
        name_to_id = {sn.name: sn.spot_id for sn in graph.iter_spot_nodes()}

        speaker_spot = name_to_id[speaker_spot_name]
        listener_spot = name_to_id[listener_spot_name]
        graph.place_entity(EntityId.create(1), speaker_spot)
        graph.place_entity(EntityId.create(2), listener_spot)

        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store=data_store)
        status_repo.save(_make_status(1, speaker_spot.value, Coordinate(0, 0, 0)))
        status_repo.save(_make_status(2, listener_spot.value, Coordinate(0, 0, 0)))
        spot_repo = InMemorySpotGraphRepository(graph)
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=MagicMock(),
            spot_graph_repository=spot_repo,
        )
        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            content="test",
            channel=SpeechChannel.SAY,
            spot_id=speaker_spot,
            speaker_coordinate=Coordinate(0, 0, 0),
            target_player_id=None,
        )
        pids = {p.value for p in resolver.resolve(event)}
        if should_reach:
            assert 2 in pids, f"{speaker_spot_name}→{listener_spot_name} ({expected_hops} hop) で届くべきだが届いていない: {pids}"
        else:
            assert 2 not in pids, f"{speaker_spot_name}→{listener_spot_name} ({expected_hops} hop) で届かないはずだが届いている: {pids}"
