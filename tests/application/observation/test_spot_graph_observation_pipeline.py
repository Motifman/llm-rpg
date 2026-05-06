"""スポットグラフ観測パイプラインの統合テスト。

ObservedEventRegistry → SpotGraphRecipientStrategy → SpotGraphObservationFormatter
のフルフローを検証する。
"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.observation_formatter import (
    ObservationFormatter,
)
from ai_rpg_world.application.observation.services.observation_pipeline import (
    ObservationPipeline,
)
from ai_rpg_world.application.observation.services.observation_recipient_resolver import (
    ObservationRecipientResolver,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies.spot_graph_recipient_strategy import (
    SpotGraphRecipientStrategy,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    ConnectionStateChangedEvent,
    EntityEnteredSpotEvent,
    EntityLeftSpotEvent,
    SpotExploredEvent,
    SpotObjectInteractedEvent,
    SpotObjectStateChangedEvent,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import SpotAtmosphere
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId(1)
SPOT_B = SpotId(2)
E1 = EntityId.create(1)
E2 = EntityId.create(2)
E3 = EntityId.create(3)
P1 = PlayerId(1)
P2 = PlayerId(2)
P3 = PlayerId(3)
OBJ_1 = SpotObjectId.create(10)
CONN_AB = ConnectionId.create(100)


def _build_graph() -> SpotGraphAggregate:
    """テスト用のグラフを構築する（2スポット、3エンティティ配置済み）。"""
    graph = SpotGraphAggregate(graph_id=GRAPH_ID)
    interior_a = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=OBJ_1,
                name="古びたドア",
                description="錆びたドア",
                object_type=SpotObjectTypeEnum.OTHER,
                state={},
                interactions=(),
                is_visible=True,
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )
    graph.add_spot(SpotNode(
        spot_id=SPOT_A,
        name="エントランス",
        description="暗い入口",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
        interior=interior_a,
    ))
    graph.add_spot(SpotNode(
        spot_id=SPOT_B,
        name="手術室",
        description="不気味な手術室",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    ))
    graph.add_connection(SpotConnection(
        connection_id=CONN_AB,
        from_spot_id=SPOT_A,
        to_spot_id=SPOT_B,
        name="長い廊下",
        description="",
        travel_ticks=3,
        is_bidirectional=False,
    ))
    graph.place_entity(E1, SPOT_A)
    graph.place_entity(E2, SPOT_A)
    graph.place_entity(E3, SPOT_B)
    graph.clear_events()
    return graph


def _build_pipeline(graph: SpotGraphAggregate) -> ObservationPipeline:
    """統合テスト用のパイプラインを構築する。"""
    repo = MagicMock()
    repo.find_graph.return_value = graph

    player_status_repo = MagicMock()
    statuses = []
    for pid in (P1, P2, P3):
        s = MagicMock()
        s.player_id = pid
        s.attention_level = None
        statuses.append(s)
    player_status_repo.find_all.return_value = statuses
    player_status_repo.find_by_id.return_value = None

    registry = ObservedEventRegistry()

    strategy = SpotGraphRecipientStrategy(
        observed_event_registry=registry,
        spot_graph_repository=repo,
        player_status_repository=player_status_repo,
    )
    resolver = ObservationRecipientResolver(strategies=[strategy])

    name_resolver = MagicMock(spec=ObservationNameResolver)
    name_resolver.player_name.side_effect = lambda pid: {
        1: "探索者A", 2: "探索者B", 3: "探索者C"
    }.get(pid.value, "不明")
    name_resolver.spot_name.return_value = "不明"

    formatter = ObservationFormatter(spot_graph_repository=repo)
    formatter._name_resolver = name_resolver
    formatter._context = ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=None,
        spot_graph_repository=repo,
    )
    from ai_rpg_world.application.observation.services.formatters.spot_graph_formatter import (
        SpotGraphObservationFormatter,
    )
    formatter._formatters = [SpotGraphObservationFormatter(formatter._context)]

    return ObservationPipeline(
        resolver=resolver,
        formatter=formatter,
        player_status_repository=player_status_repo,
    )


class TestPipelineEntityEntered:
    def test_actor_excluded_others_at_spot_receive(self):
        """P1 がスポットAに入室 → 同じスポットの P2 のみ受信、P1 は除外、P3 は別スポット。"""
        graph = _build_graph()
        pipeline = _build_pipeline(graph)
        event = EntityEnteredSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=E1,
            spot_id=SPOT_A,
            from_spot_id=SPOT_B,
        )
        results = pipeline.run(event)
        recipient_ids = {pid.value for pid, _ in results}
        assert 1 not in recipient_ids
        assert 2 in recipient_ids
        assert 3 not in recipient_ids
        _, output = results[0]
        assert output.observation_category == "social"
        assert "探索者A" in output.prose


class TestPipelineEntityLeft:
    def test_actor_excluded_remaining_receive(self):
        """P1 がスポットAを離脱 → 同スポットの P2 のみ受信。"""
        graph = _build_graph()
        pipeline = _build_pipeline(graph)
        event = EntityLeftSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=E1,
            spot_id=SPOT_A,
            to_spot_id=SPOT_B,
        )
        results = pipeline.run(event)
        recipient_ids = {pid.value for pid, _ in results}
        assert 1 not in recipient_ids
        assert 2 in recipient_ids


class TestPipelineObjectInteracted:
    def test_actor_excluded_others_see_action(self):
        """P1 がドアを操作 → P2 が「探索者Aが古びたドアを操作した」を受信。"""
        graph = _build_graph()
        pipeline = _build_pipeline(graph)
        event = SpotObjectInteractedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=E1,
            spot_id=SPOT_A,
            object_id=OBJ_1,
            action_name="open",
            result_message="ドアが開いた",
        )
        results = pipeline.run(event)
        recipient_ids = {pid.value for pid, _ in results}
        assert 1 not in recipient_ids
        assert 2 in recipient_ids
        _, output = results[0]
        assert "古びたドア" in output.prose
        assert "ドアが開いた" not in output.prose


class TestPipelineExplored:
    def test_actor_excluded_others_see_exploration(self):
        graph = _build_graph()
        pipeline = _build_pipeline(graph)
        event = SpotExploredEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=E1,
            spot_id=SPOT_A,
            discoveries=("sub-1",),
        )
        results = pipeline.run(event)
        recipient_ids = {pid.value for pid, _ in results}
        assert 1 not in recipient_ids
        assert 2 in recipient_ids
        _, output = results[0]
        assert "探索" in output.prose
        assert "sub-1" not in output.prose


class TestPipelineConnectionChanged:
    def test_all_at_both_spots_receive(self):
        """通路の状態変化 → 両端スポットの全プレイヤーが受信。"""
        graph = _build_graph()
        pipeline = _build_pipeline(graph)
        event = ConnectionStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=CONN_AB,
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
            traversable=True,
        )
        results = pipeline.run(event)
        recipient_ids = {pid.value for pid, _ in results}
        assert 1 in recipient_ids
        assert 2 in recipient_ids
        assert 3 in recipient_ids
        for _, output in results:
            assert output.observation_category == "environment"
            assert output.schedules_turn is True


class TestPipelineObjectStateChanged:
    def test_all_at_spot_receive(self):
        """オブジェクト状態変化 → そのスポットの全プレイヤーが受信。"""
        graph = _build_graph()
        pipeline = _build_pipeline(graph)
        event = SpotObjectStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            spot_id=SPOT_A,
            object_id=OBJ_1,
            old_state={},
            new_state={"open": True},
        )
        results = pipeline.run(event)
        recipient_ids = {pid.value for pid, _ in results}
        assert 1 in recipient_ids
        assert 2 in recipient_ids
        assert 3 not in recipient_ids
