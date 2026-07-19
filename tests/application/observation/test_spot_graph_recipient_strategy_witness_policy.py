"""SpotGraphRecipientStrategy が witness_policy を尊重することの検証 (Phase C)。

drop / pickup イベントに witness_policy=ACTOR_ONLY が乗っているとき、
recipient strategy が空集合を返すこと (= 誰にも観測されない) を確認する。
SAME_SPOT (default) は B-2a 以前の挙動と同じ。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies.spot_graph_recipient_strategy import (
    SpotGraphRecipientStrategy,
)
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    PlayerDroppedItemEvent,
    PlayerPickedUpItemEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(999)
SPOT = SpotId(1)
ENTITY_1 = EntityId.create(1)


def _make_strategy(entity_spot_mapping: dict) -> SpotGraphRecipientStrategy:
    """テスト fixture: 全 event を spot_graph 戦略にマップした registry を作る。"""
    registry_map = {PlayerDroppedItemEvent: "spot_graph", PlayerPickedUpItemEvent: "spot_graph"}
    registry = ObservedEventRegistry(event_to_strategy=registry_map)

    graph = MagicMock()
    graph.entity_spot_mapping.return_value = {
        EntityId.create(eid): SpotId(sid)
        for eid, sid in entity_spot_mapping.items()
    }
    repo = MagicMock()
    repo.find_graph.return_value = graph

    player_status_repo = MagicMock()
    statuses = []
    by_id = {}
    for pid in entity_spot_mapping:
        s = MagicMock()
        s.player_id = PlayerId(pid)
        statuses.append(s)
        by_id[pid] = s
    player_status_repo.find_all.return_value = statuses
    player_status_repo.find_by_id.side_effect = lambda pid: by_id.get(pid.value)

    return SpotGraphRecipientStrategy(
        observed_event_registry=registry,
        spot_graph_repository=repo,
        player_status_repository=player_status_repo,
    )


def _drop_event(witness_policy: WitnessPolicy) -> PlayerDroppedItemEvent:
    return PlayerDroppedItemEvent.create(
        aggregate_id=GRAPH_ID,
        aggregate_type="SpotGraphAggregate",
        entity_id=ENTITY_1,
        spot_id=SPOT,
        item_instance_id=ItemInstanceId.create(7),
        item_spec_id=ItemSpecId.create(100),
        item_name="流木",
        witness_policy=witness_policy,
    )


def _pickup_event(witness_policy: WitnessPolicy) -> PlayerPickedUpItemEvent:
    return PlayerPickedUpItemEvent.create(
        aggregate_id=GRAPH_ID,
        aggregate_type="SpotGraphAggregate",
        entity_id=ENTITY_1,
        spot_id=SPOT,
        item_instance_id=ItemInstanceId.create(7),
        item_spec_id=ItemSpecId.create(100),
        item_name="流木",
        witness_policy=witness_policy,
    )


class TestDropEventWitnessPolicy:
    """drop イベントの witness_policy を尊重する。"""

    def test_same_spot_same_room_other_2(self):
        """default 動作の回帰: actor 1 が drop すると 2 は受信 / 1 は除外。"""
        strategy = _make_strategy({1: 1, 2: 1})
        recipients = strategy.resolve(_drop_event(WitnessPolicy.SAME_SPOT))
        ids = {r.value for r in recipients}
        assert 1 not in ids
        assert 2 in ids

    def test_actor_only_2(self):
        """同室にプレイヤーが居ても recipients は空集合。"""
        strategy = _make_strategy({1: 1, 2: 1, 3: 1})
        recipients = strategy.resolve(_drop_event(WitnessPolicy.ACTOR_ONLY))
        assert recipients == []


class TestPickupEventWitnessPolicy:
    """pickup イベントも drop と対称に witness_policy を尊重する。"""

    def test_same_spot_same_room_other(self):
        """SAME SPOT は同室の他者に届く。"""
        strategy = _make_strategy({1: 1, 2: 1})
        recipients = strategy.resolve(_pickup_event(WitnessPolicy.SAME_SPOT))
        ids = {r.value for r in recipients}
        assert 2 in ids

    def test_actor_only(self):
        """ACTOR ONLY は誰にも届かない。"""
        strategy = _make_strategy({1: 1, 2: 1, 3: 1})
        recipients = strategy.resolve(_pickup_event(WitnessPolicy.ACTOR_ONLY))
        assert recipients == []
