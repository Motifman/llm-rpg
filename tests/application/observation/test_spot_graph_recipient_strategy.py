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
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    ConnectionStateChangedEvent,
    EntityEnteredSpotEvent,
    EntityLeftSpotEvent,
    PlayerDroppedItemEvent,
    PlayerPickedUpItemEvent,
    SpotExploredEvent,
    SpotObjectInteractedEvent,
    SpotObjectStateChangedEvent,
    SpotPlayerStateChangedInSpotEvent,
    SpotSoundHeardEvent,
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


def _make_strategy(
    entity_spot_mapping: dict,
    down_player_ids: set[int] | None = None,
) -> SpotGraphRecipientStrategy:
    """テスト用の Strategy を構築する。

    Args:
        entity_spot_mapping: {player_id: spot_id}
        down_player_ids: 倒れている (is_down=True) player_id の集合。
            Issue #621 Phase 4: down 状態の player は recipient から除外される
            ことを検証するテストで使う。
    """
    down_ids: set[int] = down_player_ids or set()
    registry_map = {}
    for evt in (
        EntityEnteredSpotEvent,
        EntityLeftSpotEvent,
        SpotObjectInteractedEvent,
        SpotExploredEvent,
        ConnectionStateChangedEvent,
        SpotObjectStateChangedEvent,
        SpotPlayerStateChangedInSpotEvent,
        PlayerDroppedItemEvent,
        PlayerPickedUpItemEvent,
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
    by_id: dict[int, object] = {}
    for pid in all_player_ids:
        status = MagicMock()
        status.player_id = PlayerId(pid)
        # 既存テストは down 状態を渡さない前提なので bool False をデフォルト
        # にする。MagicMock の自動属性 (truthy) のまま放置すると本番フィルタが
        # 全員を down 扱いしてしまうため、明示的に False をセットする。
        status.is_down = pid in down_ids
        statuses.append(status)
        by_id[pid] = status
    player_status_repo.find_all.return_value = statuses
    player_status_repo.find_by_id.side_effect = lambda pid: by_id.get(pid.value)

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

    def test_others_at_spot(self):
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

    def test_actor_only_observation(self):
        """Phase G #1: witness_policy=ACTOR_ONLY なら同室他者にも届かない。"""
        from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy
        strategy = _make_strategy({1: 1, 2: 1})
        event = SpotObjectInteractedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            object_id=OBJECT_1,
            action_name="examine_photo",
            result_message="壁の写真を見つめた",
            witness_policy=WitnessPolicy.ACTOR_ONLY,
        )
        recipients = strategy.resolve(event)
        assert list(recipients) == []


class TestPlayerDroppedItem:
    """drop event は同スポットの他プレイヤーに witness として配信され、行為者は除外される。"""

    def test_actor_same_room_other_2(self):
        """Player 1 が drop すると、Player 2 (同室) に届き、Player 1 自身には届かない。"""
        strategy = _make_strategy({1: 1, 2: 1})
        event = PlayerDroppedItemEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            item_instance_id=ItemInstanceId.create(7),
            item_spec_id=ItemSpecId.create(100),
            item_name="流木",
        )
        ids = {r.value for r in strategy.resolve(event)}
        assert 1 not in ids
        assert 2 in ids

    def test_different_spot_player(self):
        """SPOT_A での drop は SPOT_B にいる Player 3 には届かない。"""
        strategy = _make_strategy({1: 1, 2: 1, 3: 2})
        event = PlayerDroppedItemEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            item_instance_id=ItemInstanceId.create(7),
            item_spec_id=ItemSpecId.create(100),
            item_name="流木",
        )
        ids = {r.value for r in strategy.resolve(event)}
        assert 2 in ids
        assert 3 not in ids


class TestPlayerPickedUpItem:
    """pickup event も drop と対称な配信仕様。"""

    def test_actor_same_room_other(self):
        """actor を除外して同室の他者に配信する。"""
        strategy = _make_strategy({1: 1, 2: 1, 3: 1})
        event = PlayerPickedUpItemEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_2,
            spot_id=SPOT_A,
            item_instance_id=ItemInstanceId.create(7),
            item_spec_id=ItemSpecId.create(100),
            item_name="流木",
        )
        ids = {r.value for r in strategy.resolve(event)}
        assert 2 not in ids
        assert 1 in ids
        assert 3 in ids


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

    def test_duplicate_when_same_spot(self):
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


class TestConnectionStateChangedAdjacentDelivery:
    """Issue #184: 隣接 spot に居る player にも音として配信する (軸 3)。"""

    def _make_strategy_with_adjacency(
        self,
        entity_spot_mapping: dict,
        adjacency: dict,
    ):
        """from/to spot の周辺 connection を設定できる strategy。

        adjacency: {source_spot_id: [(to_spot_id, sound_permeability), ...]}
        """
        from ai_rpg_world.application.observation.services.recipient_strategies.spot_graph_recipient_strategy import (
            SpotGraphRecipientStrategy,
        )

        registry_map = {ConnectionStateChangedEvent: "spot_graph"}
        registry = ObservedEventRegistry(event_to_strategy=registry_map)

        graph = MagicMock()
        graph.entity_spot_mapping.return_value = {
            EntityId.create(eid): SpotId(sid)
            for eid, sid in entity_spot_mapping.items()
        }

        def _iter_outgoing(spot_id):
            conns = []
            for to_sid, permeability in adjacency.get(spot_id.value, []):
                conn = MagicMock()
                conn.to_spot_id = SpotId(to_sid)
                conn.passage.sound_permeability = permeability
                conns.append(conn)
            return conns

        graph.iter_outgoing_connections_from.side_effect = _iter_outgoing

        repo = MagicMock()
        repo.find_graph.return_value = graph

        player_status_repo = MagicMock()
        statuses = []
        by_id: dict[int, object] = {}
        for pid in entity_spot_mapping:
            status = MagicMock()
            status.player_id = PlayerId(pid)
            statuses.append(status)
            by_id[pid] = status
        player_status_repo.find_all.return_value = statuses
        player_status_repo.find_by_id.side_effect = lambda pid: by_id.get(pid.value)

        return SpotGraphRecipientStrategy(
            observed_event_registry=registry,
            spot_graph_repository=repo,
            player_status_repository=player_status_repo,
        )

    def test_includes_player_in_audible_neighbor_spot(self):
        """SPOT_A → SPOT_C が permeability=0.5 (可聴) なら C にいる人にも届く。"""
        SPOT_C = 3
        strategy = self._make_strategy_with_adjacency(
            entity_spot_mapping={1: 1, 2: 2, 3: SPOT_C},  # P3 が SPOT_C
            adjacency={
                1: [(SPOT_C, 0.5)],  # SPOT_A → SPOT_C は半透過
                2: [],
                SPOT_C: [],
            },
        )
        event = ConnectionStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=CONN_1,
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
            traversable=False,
        )
        recipients = strategy.resolve(event)
        ids = {r.value for r in recipients}
        # 直接観測の P1 (at A), P2 (at B) と、隣接観測の P3 (at C) が全員届く
        assert ids == {1, 2, 3}

    def test_excludes_neighbor_when_passage_is_soundproof(self):
        """permeability < 0.1 は完全遮音 → 隣接 spot の人には届かない。"""
        SPOT_C = 3
        strategy = self._make_strategy_with_adjacency(
            entity_spot_mapping={1: 1, 3: SPOT_C},
            adjacency={
                1: [(SPOT_C, 0.05)],  # ほぼ完全遮音
                SPOT_C: [],
            },
        )
        event = ConnectionStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=CONN_1,
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
            traversable=False,
        )
        recipients = strategy.resolve(event)
        ids = {r.value for r in recipients}
        # P1 だけ直接観測。P3 (隣接だが遮音) は届かない
        assert ids == {1}

    def test_neighbor_via_spot_is_also_audible(self):
        """to_spot から出る隣接 connection も配信対象になる。"""
        SPOT_D = 4
        strategy = self._make_strategy_with_adjacency(
            entity_spot_mapping={2: 2, 4: SPOT_D},
            adjacency={
                1: [],
                2: [(SPOT_D, 0.7)],  # SPOT_B → SPOT_D は高透過
                SPOT_D: [],
            },
        )
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
        # P2 (at B, 直接) + P4 (at D, 隣接)
        assert ids == {2, 4}

    def test_direct_recipient_double_counted_as_neighbor(self):
        """直接観測 spot に居る人が隣接探索でも引かれた場合、重複しない。"""
        # 仮想的: SPOT_A → SPOT_B も双方向 connection があるとして、
        # SPOT_B にいる P2 は直接観測 (to_spot) と隣接観測の両方の候補になる
        strategy = self._make_strategy_with_adjacency(
            entity_spot_mapping={2: 2},
            adjacency={
                1: [(2, 0.7)],  # SPOT_A → SPOT_B 自体
                2: [(1, 0.7)],  # SPOT_B → SPOT_A 自体
            },
        )
        event = ConnectionStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=CONN_1,
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
            traversable=False,
        )
        recipients = strategy.resolve(event)
        ids = [r.value for r in recipients]
        # 重複なし
        assert ids.count(2) == 1


class TestSpotObjectStateChanged:
    def test_includes_all_at_spot(self):
        """actor_entity_id 未指定なら従来通り同スポット全員に配信される。"""
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

    def test_excludes_actor_when_actor_entity_id_set(self):
        """Phase 4-E: actor_entity_id があれば二重観測防止のため行為者を除外する。"""
        strategy = _make_strategy({1: 1, 2: 1, 3: 2})
        event = SpotObjectStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            spot_id=SPOT_A,
            object_id=OBJECT_1,
            old_state={"lit": False},
            new_state={"lit": True},
            actor_entity_id=ENTITY_1,
        )
        recipients = strategy.resolve(event)
        ids = {r.value for r in recipients}
        assert 1 not in ids  # actor 除外
        assert 2 in ids
        assert 3 not in ids


class TestSpotPlayerStateChangedInSpot:
    """Phase 4-E: 公開可能なプレイヤー state 変化は同スポットの他プレイヤーに届く。"""

    def test_excludes_actor_2(self):
        """行為者本人は除外される (本人は current_state プロンプトで自己認識する)。"""
        strategy = _make_strategy({1: 1, 2: 1, 3: 2})
        event = SpotPlayerStateChangedInSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            state_delta=(),
            observation_message="変装が解けた",
        )
        recipients = strategy.resolve(event)
        ids = {r.value for r in recipients}
        assert 1 not in ids
        assert 2 in ids
        assert 3 not in ids


class TestSpotSoundHeardRecipientResolution:
    """SpotSoundHeardEvent は entity_id 本人 (player) にだけ届ける。"""

    def _make_with_sound_event(self, entity_spot_mapping: dict):
        """SpotSoundHeardEvent も registry に含めた strategy を返す。"""
        registry_map = {SpotSoundHeardEvent: "spot_graph"}
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
        by_id: dict[int, object] = {}
        for pid in entity_spot_mapping:
            status = MagicMock()
            status.player_id = PlayerId(pid)
            statuses.append(status)
            by_id[pid] = status
        player_status_repo.find_all.return_value = statuses
        player_status_repo.find_by_id.side_effect = (
            lambda pid: by_id.get(pid.value)
        )

        return SpotGraphRecipientStrategy(
            observed_event_registry=registry,
            spot_graph_repository=repo,
            player_status_repository=player_status_repo,
        )

    def test_known_player_entity(self):
        """entity_id が known player なら recipient に含まれる。"""
        strategy = self._make_with_sound_event({1: 1, 2: 1})
        event = SpotSoundHeardEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            source_spot_id=SPOT_A,
            intensity="MODERATE",
            ambient_description="川のせせらぎ",
        )
        recipients = strategy.resolve(event)
        ids = {p.value for p in recipients}
        assert ids == {1}

    def test_unknown_entity(self):
        """player として登録されていない entity_id は recipient に含まれない。

        monster の `EntityId` を渡したケースを想定。
        """
        strategy = self._make_with_sound_event({1: 1})
        event = SpotSoundHeardEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_2,  # 2 は player として未登録
            spot_id=SPOT_A,
            source_spot_id=SPOT_A,
            intensity="FAINT",
            ambient_description=None,
        )
        recipients = strategy.resolve(event)
        assert recipients == []

    def test_other_player(self):
        """同じ spot に居る他 player には届かない (本人だけ)。"""
        strategy = self._make_with_sound_event({1: 1, 2: 1, 3: 1})
        event = SpotSoundHeardEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            source_spot_id=SPOT_A,
            intensity="LOUD",
            ambient_description=None,
        )
        recipients = strategy.resolve(event)
        ids = {p.value for p in recipients}
        assert ids == {1}


class TestDownPlayerExcluded:
    """Issue #621 Phase 4: 倒れている (is_down=True) player は recipient から除外する。

    観測を届けてもダウン中の player は LLM ターンを回さないので消化されず、
    revive 時に observation_buffer を clear する仕様 (= 復活直前の他者発話を
    引きずらない) と整合させるため、最初から届けないのが最も静かな実装。
    """

    def test_spot_down_player_actor_event(self):
        """drop 観測: 同 spot にいる元気な P2 と倒れた P3 がいるとき、
        recipient は P2 のみ。倒れた P3 は除外される。"""
        strategy = _make_strategy({1: 1, 2: 1, 3: 1}, down_player_ids={3})
        event = PlayerDroppedItemEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            item_instance_id=ItemInstanceId.create(7),
            item_spec_id=ItemSpecId.create(100),
            item_name="流木",
        )
        ids = {r.value for r in strategy.resolve(event)}
        assert ids == {2}

    def test_all_players_event_down_player_excluded(self):
        """SpotObjectStateChangedEvent (actor_entity_id=None) は同 spot 全員に
        届く _resolve_all_at_spot 経路。倒れた player はここでも除外する。"""
        strategy = _make_strategy({1: 1, 2: 1, 3: 1}, down_player_ids={2})
        event = SpotObjectStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            object_id=OBJECT_1,
            spot_id=SPOT_A,
            old_state={"available": True},
            new_state={"available": False},
            actor_entity_id=None,
        )
        ids = {r.value for r in strategy.resolve(event)}
        assert ids == {1, 3}

    def test_down_player_actor_event_other(self):
        """down 中に actor になることは無い前提だが、防御的に: actor 自身は
        actor-exclude で除かれ、他者のうち down している人も除外される。"""
        strategy = _make_strategy({1: 1, 2: 1, 3: 1}, down_player_ids={3})
        event = SpotExploredEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            discoveries=("item",),
        )
        ids = {r.value for r in strategy.resolve(event)}
        # P1 = actor 除外, P3 = down 除外 → P2 のみ残る
        assert ids == {2}


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

    def test_does_support_unregistered(self):
        strategy = _make_strategy({})
        assert strategy.supports("unknown event") is False
