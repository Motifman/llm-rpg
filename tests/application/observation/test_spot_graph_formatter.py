"""SpotGraphObservationFormatter のユニットテスト。

方針確認:
- 行為者本人(entity_id == recipient_player_id)には None を返す
- 他者には social カテゴリで prose を生成する
- 環境変化（Connection/ObjectState）は全受信者に environment で配信する
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
from ai_rpg_world.application.observation.services.formatters.spot_graph_formatter import (
    SpotGraphObservationFormatter,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
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
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


GRAPH_ID = SpotGraphId.create(999)
SPOT_A = SpotId(1)
SPOT_B = SpotId(2)
PLAYER_1 = PlayerId(1)
PLAYER_2 = PlayerId(2)
ENTITY_1 = EntityId.create(1)
ENTITY_2 = EntityId.create(2)
OBJECT_1 = SpotObjectId.create(100)
CONN_1 = ConnectionId.create(200)


def _make_context(
    *,
    player_names: dict | None = None,
    spot_names: dict | None = None,
    object_names: dict | None = None,
    connection_names: dict | None = None,
) -> ObservationFormatterContext:
    """テスト用コンテキストを構築する。"""
    name_resolver = MagicMock(spec=ObservationNameResolver)

    def resolve_player(pid: PlayerId) -> str:
        if player_names and pid.value in player_names:
            return player_names[pid.value]
        return "不明なプレイヤー"

    name_resolver.player_name.side_effect = resolve_player

    repo = MagicMock()
    graph = MagicMock()
    repo.find_graph.return_value = graph

    def get_spot(sid: SpotId) -> MagicMock:
        spot = MagicMock()
        spot.name = (spot_names or {}).get(sid.value, "不明なスポット")
        interior = MagicMock()

        def get_object(oid):
            obj_name = (object_names or {}).get(str(oid.value), None)
            if obj_name:
                obj = MagicMock()
                obj.name = obj_name
                return obj
            return None

        interior.get_object.side_effect = get_object
        spot.interior = interior
        return spot

    graph.get_spot.side_effect = get_spot

    def get_connection(cid):
        conn = MagicMock()
        conn.name = (connection_names or {}).get(str(cid.value), "通路")
        return conn

    graph.get_connection.side_effect = get_connection

    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=None,
        spot_graph_repository=repo,
    )


@pytest.fixture
def ctx():
    return _make_context(
        player_names={1: "探索者A", 2: "探索者B"},
        spot_names={1: "エントランスホール", 2: "手術室"},
        object_names={"100": "古びたドア"},
        connection_names={"200": "長い廊下"},
    )


@pytest.fixture
def formatter(ctx):
    return SpotGraphObservationFormatter(ctx)


class TestEntityEnteredSpot:
    def test_self_returns_none(self, formatter):
        event = EntityEnteredSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            from_spot_id=SPOT_B,
        )
        assert formatter.format(event, PLAYER_1) is None

    def test_other_returns_social(self, formatter):
        event = EntityEnteredSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            from_spot_id=SPOT_B,
        )
        result = formatter.format(event, PLAYER_2)
        assert result is not None
        assert result.observation_category == "social"
        assert "探索者A" in result.prose
        assert "エントランスホール" in result.prose
        assert result.structured["type"] == "entity_entered_spot"

    def test_initial_placement_self_returns_none(self, formatter):
        event = EntityEnteredSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            from_spot_id=None,
        )
        assert formatter.format(event, PLAYER_1) is None


class TestEntityLeftSpot:
    def test_self_returns_none(self, formatter):
        event = EntityLeftSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            to_spot_id=SPOT_B,
        )
        assert formatter.format(event, PLAYER_1) is None

    def test_other_returns_social(self, formatter):
        event = EntityLeftSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            to_spot_id=SPOT_B,
        )
        result = formatter.format(event, PLAYER_2)
        assert result is not None
        assert result.observation_category == "social"
        assert "探索者A" in result.prose
        assert "去った" in result.prose


class TestSpotObjectInteracted:
    def test_self_returns_none(self, formatter):
        event = SpotObjectInteractedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            object_id=OBJECT_1,
            action_name="open",
            result_message="ドアが開いた",
        )
        assert formatter.format(event, PLAYER_1) is None

    def test_other_returns_social_without_result(self, formatter):
        event = SpotObjectInteractedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            object_id=OBJECT_1,
            action_name="open",
            result_message="ドアが開いた",
        )
        result = formatter.format(event, PLAYER_2)
        assert result is not None
        assert result.observation_category == "social"
        assert "探索者A" in result.prose
        assert "古びたドア" in result.prose
        assert "ドアが開いた" not in result.prose


class TestSpotExplored:
    def test_self_returns_none(self, formatter):
        event = SpotExploredEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            discoveries=("sub-loc-1",),
        )
        assert formatter.format(event, PLAYER_1) is None

    def test_other_returns_social_without_discoveries(self, formatter):
        event = SpotExploredEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            discoveries=("sub-loc-1", "obj-2"),
        )
        result = formatter.format(event, PLAYER_2)
        assert result is not None
        assert result.observation_category == "social"
        assert "探索者A" in result.prose
        assert "探索" in result.prose
        assert "sub-loc-1" not in result.prose


class TestConnectionStateChanged:
    def test_passable_returns_environment(self, formatter):
        event = ConnectionStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=CONN_1,
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
            traversable=True,
        )
        result = formatter.format(event, PLAYER_1)
        assert result is not None
        assert result.observation_category == "environment"
        assert "通行可能" in result.prose
        assert "長い廊下" in result.prose
        assert result.schedules_turn is True

    def test_impassable_returns_environment(self, formatter):
        event = ConnectionStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=CONN_1,
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
            traversable=False,
        )
        result = formatter.format(event, PLAYER_1)
        assert result is not None
        assert "通行不能" in result.prose


class TestSpotObjectStateChanged:
    def test_returns_environment(self, formatter):
        event = SpotObjectStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            spot_id=SPOT_A,
            object_id=OBJECT_1,
            old_state={"locked": True},
            new_state={"locked": False},
        )
        result = formatter.format(event, PLAYER_1)
        assert result is not None
        assert result.observation_category == "environment"
        assert "古びたドア" in result.prose
        assert "変化" in result.prose
        assert result.schedules_turn is True


class TestUnknownEvent:
    def test_returns_none_for_unhandled_event(self, formatter):
        assert formatter.format("not an event", PLAYER_1) is None
