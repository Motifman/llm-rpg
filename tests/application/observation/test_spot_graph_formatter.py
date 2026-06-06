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

    # Issue #311 後続 (PR #315): 進入 / 退出 prose に方向情報を組み込むため、
    # ``iter_outgoing_connections_from`` のモックも用意する。
    # 既定では SPOT_A ↔ SPOT_B 間に 1 本ずつ双方向の接続を張る。
    def iter_outgoing_connections_from(spot_id):
        conn_ab = MagicMock()
        conn_ab.to_spot_id = SPOT_B
        conn_ab.name = (connection_names or {}).get("200", "長い廊下")
        conn_ba = MagicMock()
        conn_ba.to_spot_id = SPOT_A
        conn_ba.name = (connection_names or {}).get("200", "長い廊下")
        if spot_id == SPOT_A:
            return [conn_ab]
        if spot_id == SPOT_B:
            return [conn_ba]
        return []

    graph.iter_outgoing_connections_from.side_effect = iter_outgoing_connections_from

    # Issue #184: 位置ベース prose 分岐用に get_entity_spot を default で
    # 「位置不明」(None) にしておく。位置を要する個別テストは side_effect
    # を上書きして特定 spot を返すこと。
    graph.get_entity_spot.return_value = None

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

    def test_other_returns_social_with_connection_and_origin(self, formatter):
        """進入観測には接続名 + 進入元のスポット名が乗る (Issue #311 後続)。"""
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
        # 進入元 + 接続名が文中に現れる
        assert "手術室" in result.prose
        assert "長い廊下" in result.prose
        assert result.structured["type"] == "entity_entered_spot"
        assert result.structured["from_spot_name"] == "手術室"
        assert result.structured["from_spot_id_value"] == SPOT_B.value
        assert result.structured["spot_id_value"] == SPOT_A.value
        assert result.structured["connection_name"] == "長い廊下"

    def test_initial_placement_other_omits_from_and_connection(self, formatter):
        """``from_spot_id=None`` (初期配置) は従来通り「やってきた」のみ。"""
        event = EntityEnteredSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            from_spot_id=None,
        )
        result = formatter.format(event, PLAYER_2)
        assert result is not None
        assert "エントランスホール" in result.prose
        assert "から" not in result.prose
        assert "通って" not in result.prose
        # structured には from_spot_name / connection_name が付かない
        assert "from_spot_name" not in result.structured
        assert "connection_name" not in result.structured
        # 共通フィールド (spot_id_value) は乗る
        assert result.structured["spot_id_value"] == SPOT_A.value

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

    def test_other_returns_social_with_destination_and_connection(self, formatter):
        """退出観測には行き先のスポット名 + 通った接続名が乗る (Issue #311 後続)。

        目撃者は人間として「カイトが通路の方向へ歩いて行った」と方向を視認できる
        べき。これで追跡行動 (= 「カイトについて行く」) の手がかりになる。
        """
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
        # 行き先 + 接続名 + 「去っていった」が文中に現れる
        assert "長い廊下" in result.prose
        assert "手術室" in result.prose
        assert "去っていった" in result.prose
        assert result.structured["type"] == "entity_left_spot"
        assert result.structured["to_spot_name"] == "手術室"
        assert result.structured["to_spot_id_value"] == SPOT_B.value
        assert result.structured["connection_name"] == "長い廊下"

    def test_left_falls_back_when_connection_name_unresolved(self):
        """``iter_outgoing_connections_from`` が該当接続を返さないと、
        接続名なしの prose にフォールバックする (= 行き先のみで方向を示す)。"""
        ctx = _make_context(
            player_names={1: "探索者A", 2: "探索者B"},
            spot_names={1: "エントランスホール", 2: "手術室"},
            connection_names={},
        )
        # 接続情報を空にする
        ctx.spot_graph_repository.find_graph.return_value.iter_outgoing_connections_from.side_effect = (
            lambda _sid: []
        )
        fmt = SpotGraphObservationFormatter(ctx)
        event = EntityLeftSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            to_spot_id=SPOT_B,
        )
        result = fmt.format(event, PLAYER_2)
        assert result is not None
        assert "手術室" in result.prose
        assert "去っていった" in result.prose
        # connection_name は構造化にも乗らない
        assert "connection_name" not in result.structured

    def test_left_falls_back_to_legacy_when_destination_unresolved(self):
        """行き先名が「不明なスポット」のときは従来文言にフォールバック。"""
        ctx = _make_context(
            player_names={1: "探索者A", 2: "探索者B"},
            spot_names={1: "エントランスホール"},  # SPOT_B は未登録
        )
        fmt = SpotGraphObservationFormatter(ctx)
        event = EntityLeftSpotEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=ENTITY_1,
            spot_id=SPOT_A,
            to_spot_id=SPOT_B,
        )
        result = fmt.format(event, PLAYER_2)
        assert result is not None
        # 従来文言
        assert result.prose == "探索者Aがこのスポットを去った。"


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


class TestPlayerDroppedItem:
    """drop イベントから「Xが流木を地面に置いた」prose を生成する formatter。"""

    def _make_event(self, *, entity_id=ENTITY_1) -> PlayerDroppedItemEvent:
        return PlayerDroppedItemEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=entity_id,
            spot_id=SPOT_A,
            item_instance_id=ItemInstanceId.create(7),
            item_spec_id=ItemSpecId.create(100),
            item_name="流木",
        )

    def test_actor_本人には_None_を返す(self, formatter):
        """recipient strategy で除外済みのはずだが二重ガード。"""
        event = self._make_event(entity_id=ENTITY_1)
        assert formatter.format(event, PLAYER_1) is None

    def test_他者には_social_で_prose_を返す(self, formatter):
        """「探索者Aが流木を地面に置いた」が同室者に届く。"""
        event = self._make_event(entity_id=ENTITY_1)
        result = formatter.format(event, PLAYER_2)
        assert result is not None
        assert result.observation_category == "social"
        assert result.prose == "探索者Aが流木を地面に置いた。"
        assert result.structured["type"] == "player_dropped_item"
        assert result.structured["item_name"] == "流木"


class TestPlayerPickedUpItem:
    """pickup イベントから「Xが流木を拾い上げた」prose を生成する formatter。"""

    def _make_event(self, *, entity_id=ENTITY_2) -> PlayerPickedUpItemEvent:
        return PlayerPickedUpItemEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            entity_id=entity_id,
            spot_id=SPOT_A,
            item_instance_id=ItemInstanceId.create(7),
            item_spec_id=ItemSpecId.create(100),
            item_name="流木",
        )

    def test_actor_本人には_None_を返す(self, formatter):
        event = self._make_event(entity_id=ENTITY_2)
        assert formatter.format(event, PLAYER_2) is None

    def test_他者には_social_で_prose_を返す(self, formatter):
        """「探索者Bが流木を拾い上げた」が同室者に届く。"""
        event = self._make_event(entity_id=ENTITY_2)
        result = formatter.format(event, PLAYER_1)
        assert result is not None
        assert result.observation_category == "social"
        assert result.prose == "探索者Bが流木を拾い上げた。"
        assert result.structured["type"] == "player_picked_up_item"


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

    def test_prose_is_fact_only_regardless_of_cause(self, formatter):
        """Issue #180 再設計: prose は cause に関わらず事実だけ。

        観測者が本来知り得ない因果情報を文体に焼き込まない (オノマトペや
        「ひとりでに」のような hint を付けない)。観測者ごとの prose 差分化は
        軸 3 (recipient_id の位置による分岐) で別途扱う。
        """
        from ai_rpg_world.domain.world_graph.enum.passage_change_cause import (
            PassageChangeCauseEnum,
        )

        for cause in PassageChangeCauseEnum:
            event = ConnectionStateChangedEvent.create(
                aggregate_id=GRAPH_ID,
                aggregate_type="SpotGraphAggregate",
                connection_id=CONN_1,
                from_spot_id=SPOT_A,
                to_spot_id=SPOT_B,
                traversable=False,
                cause=cause,
            )
            result = formatter.format(event, PLAYER_1)
            assert result is not None
            # 観測者に「誰がトリガしたか」を匂わせる表現を漏らさない
            for leak in ("ガチャッと", "ひとりでに", "連動", "何かの拍子"):
                assert leak not in result.prose, (
                    f"cause={cause} で prose に観測モデルを破る語 {leak!r} が混入: {result.prose!r}"
                )
            # 事実だけが prose に出る
            assert "通行不能になった" in result.prose

    def test_structured_payload_carries_cause_for_machine_use(self, formatter):
        """cause は structured に残し、機械可読 / 解析 / 将来の位置分岐用に保つ。"""
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
        assert result.structured["cause"] == "REACTIVE"
        # default UNKNOWN も structured に表現される
        event2 = ConnectionStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=CONN_1,
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
            traversable=True,
        )
        result2 = formatter.format(event2, PLAYER_1)
        assert result2.structured["cause"] == "UNKNOWN"


class TestConnectionStateChangedPositionAware:
    """Issue #184: 観測者の位置で prose を分岐する (軸 3)。

    直接観測 (両端 spot 内) は素朴な「通行可能/不能になった」prose。
    間接観測 (隣接 spot) は「遠くで...動く音がした」と音だけに縮退する。
    """

    def _build_ctx_with_position(self, recipient_spot):
        """recipient の位置を任意の SpotId にできる context を作る。"""
        ctx = _make_context(
            connection_names={"200": "金庫扉"},
        )
        # ObservationFormatterContext は frozen dataclass なので
        # 内部の repo モックの get_entity_spot を上書きする
        graph = ctx.spot_graph_repository.find_graph()
        graph.get_entity_spot.return_value = recipient_spot
        return ctx

    def test_recipient_at_from_spot_gets_direct_prose(self):
        """from_spot にいる observer は素朴な「通行不能になった」prose。"""
        ctx = self._build_ctx_with_position(SPOT_A)
        formatter = SpotGraphObservationFormatter(ctx)
        event = ConnectionStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=CONN_1,
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
            traversable=False,
        )
        result = formatter.format(event, PLAYER_1)
        assert "通行不能になった" in result.prose
        assert "遠くで" not in result.prose
        assert result.structured["recipient_position"] == "at_from"

    def test_recipient_at_to_spot_gets_direct_prose(self):
        """to_spot にいる observer も直接観測扱い。"""
        ctx = self._build_ctx_with_position(SPOT_B)
        formatter = SpotGraphObservationFormatter(ctx)
        event = ConnectionStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=CONN_1,
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
            traversable=True,
        )
        result = formatter.format(event, PLAYER_1)
        assert "通行可能になった" in result.prose
        assert result.structured["recipient_position"] == "at_to"

    def test_recipient_at_adjacent_spot_gets_sound_only_prose(self):
        """隣接 spot にいる observer は音だけ伝わる: 通行可否情報は得られない。"""
        SPOT_NEIGHBOR = SpotId(99)
        ctx = self._build_ctx_with_position(SPOT_NEIGHBOR)
        formatter = SpotGraphObservationFormatter(ctx)
        event = ConnectionStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=CONN_1,
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
            traversable=False,
        )
        result = formatter.format(event, PLAYER_1)
        # 音だけ。「通行不能」のような確定状態は隣接からは知り得ない
        assert "遠くで" in result.prose
        assert "動く音がした" in result.prose
        assert "通行不能" not in result.prose
        assert "通行可能" not in result.prose
        assert result.structured["recipient_position"] == "adjacent"

    def test_recipient_position_unknown_falls_back_to_direct_prose(self):
        """位置不明 (graph 上に居ない / 引けない) は直接観測 fallback。"""
        ctx = self._build_ctx_with_position(None)  # 引けない
        formatter = SpotGraphObservationFormatter(ctx)
        event = ConnectionStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=CONN_1,
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
            traversable=False,
        )
        result = formatter.format(event, PLAYER_1)
        assert "通行不能になった" in result.prose
        assert result.structured["recipient_position"] == "unknown"


class TestSpotObjectStateChanged:
    """#356 後続: 内部 state vocab の漏洩を防ぐため narrative の有無で分岐。"""

    def test_narrative_無しなら_silent_になる(self, formatter):
        """narrative=None なら formatter は None を返す (observation 非発火)。

        旧挙動は state_delta から "locked が True から False に変わった" を
        機械生成して prompt に流していたが、これは内部用語の漏洩。
        """
        event = SpotObjectStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            spot_id=SPOT_A,
            object_id=OBJECT_1,
            old_state={"locked": True},
            new_state={"locked": False},
        )
        assert formatter.format(event, PLAYER_1) is None

    def test_narrative_有りなら_その_narrative_が_prose_になる(self, formatter):
        """著者が narrative を提供したら、そのまま prose に流れる。"""
        event = SpotObjectStateChangedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            spot_id=SPOT_A,
            object_id=OBJECT_1,
            old_state={"locked": True},
            new_state={"locked": False},
            narrative="鍵がガチャリと外れた音がした",
        )
        result = formatter.format(event, PLAYER_1)
        assert result is not None
        assert result.observation_category == "environment"
        assert result.prose == "鍵がガチャリと外れた音がした"
        assert result.schedules_turn is True
        # 内部 vocab "locked" は prose に出ない
        assert "locked" not in result.prose
        # 構造化 state_delta は残す (機械処理向け、LLM には届かない)
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
