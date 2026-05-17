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

    def test_default_cause_uses_plain_prose(self, formatter):
        """既定の UNKNOWN cause では従来通り素朴な prose (後方互換)。"""
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
        # 既存挙動: 「ガチャッと」「ひとりでに」等のオノマトペは付かない
        assert "ガチャッと" not in result.prose
        assert "ひとりでに" not in result.prose

    def test_actor_action_cause_yields_active_onomatopoeia(self, formatter):
        """Issue #180: actor 由来は「ガチャッと」で能動感を伝える。"""
        from ai_rpg_world.domain.world_graph.enum.passage_change_cause import (
            PassageChangeCauseEnum,
        )

        event = ConnectionStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=CONN_1,
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
            traversable=False,
            cause=PassageChangeCauseEnum.ACTOR_ACTION,
        )
        result = formatter.format(event, PLAYER_1)
        assert result is not None
        assert "ガチャッと" in result.prose
        assert "通行不能" in result.prose
        # 「誰が」は秘匿される
        assert result.structured["cause"] == "ACTOR_ACTION"

    def test_reactive_cause_yields_passive_onomatopoeia(self, formatter):
        """Issue #180: reactive_binding 由来は「ひとりでに」で自動感を伝える。"""
        from ai_rpg_world.domain.world_graph.enum.passage_change_cause import (
            PassageChangeCauseEnum,
        )

        event = ConnectionStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=CONN_1,
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
            traversable=False,
            cause=PassageChangeCauseEnum.REACTIVE,
        )
        result = formatter.format(event, PLAYER_1)
        assert result is not None
        assert "ひとりでに" in result.prose
        assert "通行不能" in result.prose
        assert result.structured["cause"] == "REACTIVE"

    def test_synchronized_action_cause_yields_linked_prose(self, formatter):
        """SYNCHRONIZED_ACTION 由来は「連動して」と表現される。"""
        from ai_rpg_world.domain.world_graph.enum.passage_change_cause import (
            PassageChangeCauseEnum,
        )

        event = ConnectionStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=CONN_1,
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
            traversable=True,
            cause=PassageChangeCauseEnum.SYNCHRONIZED_ACTION,
        )
        result = formatter.format(event, PLAYER_1)
        assert result is not None
        assert "連動" in result.prose
        assert result.structured["cause"] == "SYNCHRONIZED_ACTION"

    def test_scenario_event_cause_yields_distinct_prose(self, formatter):
        """SCENARIO_EVENT 由来は「何かの拍子に」と表現される。"""
        from ai_rpg_world.domain.world_graph.enum.passage_change_cause import (
            PassageChangeCauseEnum,
        )

        event = ConnectionStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=CONN_1,
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
            traversable=False,
            cause=PassageChangeCauseEnum.SCENARIO_EVENT,
        )
        result = formatter.format(event, PLAYER_1)
        assert result is not None
        assert "何かの拍子" in result.prose
        assert result.structured["cause"] == "SCENARIO_EVENT"


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
        # Phase 4-E: 状態差分が具体的なテキストとして含まれる
        assert "locked" in result.prose
        assert result.schedules_turn is True
        # 構造化 state_delta も載る
        assert result.structured["state_delta"] == [
            {"key": "locked", "before": True, "after": False}
        ]


class TestSpotObjectStateChangedActorExclusion:
    """Phase 4-E: actor_entity_id が自分のとき formatter が None を返す (二重ガード)。"""

    def test_actor_self_returns_none(self, formatter):
        from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
        event = SpotObjectStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            spot_id=SPOT_A,
            object_id=OBJECT_1,
            old_state={"lit": False},
            new_state={"lit": True},
            actor_entity_id=EntityId.create(PLAYER_1.value),
        )
        assert formatter.format(event, PLAYER_1) is None


class TestSpotPlayerStateChangedInSpot:
    """Phase 4-E: プレイヤー state 公開変化の formatter 出力を検証。"""

    def test_renders_observation_message_when_present(self, formatter):
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
            SpotPlayerStateChangedInSpotEvent,
        )
        from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
            StateDeltaEntry,
        )
        from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
        event = SpotPlayerStateChangedInSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=EntityId.create(PLAYER_2.value),
            spot_id=SPOT_A,
            state_delta=(StateDeltaEntry(key="disguised", before=True, after=False),),
            observation_message="変装が解けた",
        )
        result = formatter.format(event, PLAYER_1)
        assert result is not None
        assert "変装が解けた" in result.prose
        assert result.observation_category == "social"
        assert result.structured["state_delta"] == [
            {"key": "disguised", "before": True, "after": False}
        ]

    def test_renders_state_delta_when_no_message(self, formatter):
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
            SpotPlayerStateChangedInSpotEvent,
        )
        from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
            StateDeltaEntry,
        )
        from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
        event = SpotPlayerStateChangedInSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=EntityId.create(PLAYER_2.value),
            spot_id=SPOT_A,
            state_delta=(StateDeltaEntry(key="posture", before="standing", after="kneeling"),),
        )
        result = formatter.format(event, PLAYER_1)
        assert result is not None
        assert "posture" in result.prose
        assert "kneeling" in result.prose

    def test_actor_self_returns_none(self, formatter):
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
            SpotPlayerStateChangedInSpotEvent,
        )
        from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
        event = SpotPlayerStateChangedInSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=EntityId.create(PLAYER_1.value),
            spot_id=SPOT_A,
            state_delta=(),
            observation_message="should not appear",
        )
        # 自分が actor の場合 formatter は None を返す (二重ガード)
        assert formatter.format(event, PLAYER_1) is None


class TestUnknownEvent:
    def test_returns_none_for_unhandled_event(self, formatter):
        assert formatter.format("not an event", PLAYER_1) is None
