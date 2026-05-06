"""SpotGraphRecipientStrategy のユニットテスト。

方針確認:
- 行為者本人は配信先から除外される
- 同一スポットの他プレイヤーが配信先に含まれる
- 環境変化は影響スポットの全プレイヤーが対象
"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies.spot_graph_recipient_strategy import (
    SpotGraphRecipientStrategy,
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
PLAYER_3 = PlayerId(3)
ENTITY_1 = EntityId.create(1)
ENTITY_2 = EntityId.create(2)
ENTITY_3 = EntityId.create(3)
OBJECT_1 = SpotObjectId.create(100)
CONN_1 = ConnectionId.create(200)


def _make_strategy(entity_spot_mapping: dict) -> SpotGraphRecipientStrategy:
    """テスト用の Strategy を構築する。"""
    registry_map = {}
    for evt in (
        EntityEnteredSpotEvent,
        EntityLeftSpotEvent,
        SpotObjectInteractedEvent,
        SpotExploredEvent,
        ConnectionStateChangedEvent,
        SpotObjectStateChangedEvent,
    ):
        registry_map[evt] = "spot_graph"
    registry = ObservedEventRegistry(event_to_strategy=registry_map)

    graph = MagicMock()
    graph.entity_spot_mapping.return_value = {
        EntityId.create(eid): SpotId(sid)
        for eid, sid in entity_spot_mapping.items()
    }

    repo = MagicMock()
    repo.find_graph.return_value = graph

    player_status_repo = MagicMock()
    all_player_ids = set()
    for eid in entity_spot_mapping:
        all_player_ids.add(eid)

    statuses = []
    for pid in all_player_ids:
        status = MagicMock()
        status.player_id = PlayerId(pid)
        statuses.append(status)
    player_status_repo.find_all.return_value = statuses

    return SpotGraphRecipientStrategy(
        observed_event_registry=registry,
        spot_graph_repository=repo,
        player_status_repository=player_status_repo,
    )


class TestEntityEnteredSpot:
    def test_excludes_self_includes_others_at_spot(self):
        strategy = _make_strategy({1: 1, 2: 1, 3: 2})
        event = EntityEnteredSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            from_spot_id=SPOT_B,
        )
        recipients = strategy.resolve(event)
        ids = {r.value for r in recipients}
        assert 1 not in ids
        assert 2 in ids
        assert 3 not in ids

    def test_no_others_at_spot(self):
        strategy = _make_strategy({1: 1, 3: 2})
        event = EntityEnteredSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            from_spot_id=SPOT_B,
        )
        assert strategy.resolve(event) == []


class TestEntityLeftSpot:
    def test_excludes_self_includes_remaining_at_spot(self):
        strategy = _make_strategy({1: 1, 2: 1})
        event = EntityLeftSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            to_spot_id=SPOT_B,
        )
        recipients = strategy.resolve(event)
        ids = {r.value for r in recipients}
        assert 1 not in ids
        assert 2 in ids


class TestSpotObjectInteracted:
    def test_excludes_actor(self):
        strategy = _make_strategy({1: 1, 2: 1})
        event = SpotObjectInteractedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            object_id=OBJECT_1,
            action_name="open",
            result_message="opened",
        )
        recipients = strategy.resolve(event)
        ids = {r.value for r in recipients}
        assert 1 not in ids
        assert 2 in ids


class TestSpotExplored:
    def test_excludes_explorer(self):
        strategy = _make_strategy({1: 1, 2: 1, 3: 1})
        event = SpotExploredEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            discoveries=("item",),
        )
        recipients = strategy.resolve(event)
        ids = {r.value for r in recipients}
        assert 1 not in ids
        assert 2 in ids
        assert 3 in ids


class TestConnectionStateChanged:
    def test_includes_players_at_both_spots(self):
        strategy = _make_strategy({1: 1, 2: 2, 3: 1})
        event = ConnectionStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=CONN_1,
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
            traversable=True,
        )
        recipients = strategy.resolve(event)
        ids = {r.value for r in recipients}
        assert 1 in ids
        assert 2 in ids
        assert 3 in ids

    def test_no_duplicate_when_same_spot(self):
        strategy = _make_strategy({1: 1, 2: 1})
        event = ConnectionStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=CONN_1,
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_A,
            traversable=True,
        )
        recipients = strategy.resolve(event)
        assert len(recipients) == 2


class TestSpotObjectStateChanged:
    def test_includes_all_at_spot(self):
        strategy = _make_strategy({1: 1, 2: 1, 3: 2})
        event = SpotObjectStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            spot_id=SPOT_A,
            object_id=OBJECT_1,
            old_state={},
            new_state={"visible": True},
        )
        recipients = strategy.resolve(event)
        ids = {r.value for r in recipients}
        assert 1 in ids
        assert 2 in ids
        assert 3 not in ids


class TestSupports:
    def test_supports_registered_events(self):
        strategy = _make_strategy({})
        event = EntityEnteredSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            from_spot_id=None,
        )
        assert strategy.supports(event) is True

    def test_does_not_support_unregistered(self):
        strategy = _make_strategy({})
        assert strategy.supports("unknown event") is False
