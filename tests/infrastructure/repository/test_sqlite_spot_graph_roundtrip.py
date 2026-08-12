"""スポットグラフ SQLite 永続化のラウンドトリップ検証。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import fields, replace

import pytest

from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.passage_kind import DoorStateEnum, WallStateEnum
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import SpotNotInGraphException
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_position import SpotPosition
from ai_rpg_world.domain.world_graph.value_object.state_display_rule import (
    StateDisplayRule,
)
from ai_rpg_world.infrastructure.repository.spot_graph_persistence_exceptions import (
    SpotGraphConnectionRecordInvariantError,
    SpotGraphSnapshotNotInitializedError,
    SpotGraphStateDecodeError,
    UnsupportedSpotGraphAggregateSchemaError,
    UnsupportedSpotInteriorSchemaError,
)
from ai_rpg_world.infrastructure.repository.spot_graph_sqlite_seed import seed_spot_graph_to_sqlite
from ai_rpg_world.infrastructure.repository.sqlite_spot_graph_repository import SqliteSpotGraphRepository
from ai_rpg_world.infrastructure.repository.sqlite_spot_interior_repository import SqliteSpotInteriorRepository
from ai_rpg_world.infrastructure.repository.sqlite_world_graph_state_codec import (
    _INTERACTION_CONDITION_FIELD_CODECS,
    _interaction_condition_from_dict,
    _interaction_condition_to_dict,
    dumps_spot_graph_aggregate,
    dumps_spot_interior,
    loads_spot_graph_aggregate,
    loads_spot_interior,
    spot_graph_aggregate_to_json_dict,
    spot_interior_to_json_dict,
)
from tests.application.world_graph.test_spot_graph_step4_integration import (
    _graph_with_locked_connection,
    _switch_interior,
)


def _node(i: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


def _bidirectional_graph() -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(_node(1))
    g.add_spot(_node(2))
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(1),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="x",
            description="",
            travel_ticks=0,
            is_bidirectional=True,
        ),
        reverse_connection_id=ConnectionId.create(2),
    )
    g.place_entity(EntityId.create(1), SpotId.create(1))
    g.clear_events()
    return g


def _parallel_edge_graph() -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(SpotGraphId.create(2))
    g.add_spot(_node(1))
    g.add_spot(_node(2))
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(1),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="stairs",
            description="slow",
            travel_ticks=3,
            is_bidirectional=True,
        ),
        reverse_connection_id=ConnectionId.create(2),
    )
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(3),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="vent",
            description="oneway",
            travel_ticks=1,
            is_bidirectional=False,
            passage=Passage.door(DoorStateEnum.LOCKED),
        )
    )
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(4),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="tunnel",
            description="fast",
            travel_ticks=0,
            is_bidirectional=True,
        ),
        reverse_connection_id=ConnectionId.create(5),
    )
    g.place_entity(EntityId.create(9), SpotId.create(1))
    g.clear_events()
    return g


def _memory_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_sqlite_roundtrip_locked_door_graph_and_interior() -> None:
    graph = _graph_with_locked_connection()
    interior = _switch_interior()
    conn = _memory_connection()
    seed_spot_graph_to_sqlite(conn, graph, {SpotId.create(1): interior})

    g_repo = SqliteSpotGraphRepository.for_standalone_connection(conn)
    i_repo = SqliteSpotInteriorRepository.for_standalone_connection(conn)

    loaded = g_repo.find_graph()
    loaded_interior = i_repo.find_by_spot_id(SpotId.create(1))
    assert loaded_interior is not None

    expected = spot_graph_aggregate_to_json_dict(graph)
    actual = spot_graph_aggregate_to_json_dict(loaded)
    assert actual == expected
    assert spot_interior_to_json_dict(loaded_interior) == spot_interior_to_json_dict(interior)


def test_sqlite_roundtrip_preserves_override_for_an_inactive_passage_state() -> None:
    """OPEN 中に保存しても、LOCKED 用の遮音宣言は復元後の再施錠で戻る。"""
    graph = SpotGraphAggregate.empty(SpotGraphId.create(30))
    graph.add_spot(_node(1))
    graph.add_spot(_node(2))
    connection_id = ConnectionId.create(9)
    graph.add_connection(
        SpotConnection(
            connection_id=connection_id,
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="遮音扉",
            description="",
            travel_ticks=1,
            is_bidirectional=False,
            passage=Passage.door(
                DoorStateEnum.LOCKED,
                sound_permeability=0.3,
            ),
        )
    )
    graph.set_connection_passage_state(connection_id, DoorStateEnum.OPEN.value)

    restored = loads_spot_graph_aggregate(dumps_spot_graph_aggregate(graph))
    restored.set_connection_passage_state(connection_id, DoorStateEnum.LOCKED.value)

    relocked = restored.get_connection(connection_id).passage
    assert relocked.sound_permeability == pytest.approx(0.3)


def test_sqlite_roundtrip_preserves_interaction_cooldown_group() -> None:
    """物体操作の共有待ち時間キーと関連宣言は SQLite 復元後も失われない。

    ``cooldown_group`` だけ残して ``cooldown_ticks`` を落とすと、SQLite 構成で
    だけ待ち時間が無効になる。観測文面も含め、同じ InteractionDef として
    往復することを固定する。
    """
    interior = _switch_interior()
    obj = interior.objects[0]
    interaction = replace(
        obj.interactions[0],
        cooldown_ticks=15,
        cooldown_group="shared_attack",
        witness_observation_message_in_dark="暗がりで物音がした。",
    )
    interior = interior.replace_object(
        replace(obj, interactions=(interaction,))
    )

    loaded = loads_spot_interior(dumps_spot_interior(interior))

    assert loaded.objects[0].interactions[0] == interaction


def test_sqlite_roundtrip_preserves_interaction_actor_planes() -> None:
    """幽霊にも許した物体操作は SQLite 復元後も生者専用へ戻らない。"""
    from ai_rpg_world.domain.world_graph.enum.interaction_actor_plane import (
        InteractionActorPlane,
    )

    interior = _switch_interior()
    obj = interior.objects[0]
    interaction = replace(
        obj.interactions[0],
        allowed_actor_planes=(
            InteractionActorPlane.LIVING,
            InteractionActorPlane.DEPARTED,
        ),
    )
    interior = interior.replace_object(
        replace(obj, interactions=(interaction,))
    )

    loaded = loads_spot_interior(dumps_spot_interior(interior))

    assert loaded.objects[0].interactions[0] == interaction


def test_sqlite_roundtrip_preserves_every_interaction_condition_field() -> None:
    """操作条件の全宣言値はSQLite復元後も既定値へ静かに戻らない。"""
    interior = _switch_interior()
    obj = interior.objects[0]
    condition = InteractionCondition(
        condition_type=InteractionConditionTypeEnum.TARGET_PLAYER_STATE_IS,
        target_item_spec_id=ItemSpecId.create(1),
        target_object_id=SpotObjectId.create(2),
        required_state={"role": "crew", "nested": {"count": 2}},
        flag_name="ready",
        failure_message="条件を満たしていない。",
        required_player_count=3,
        prepared_action_id="hold_lever",
        puzzle_input_key="answer",
        required_item_spec_ids=(ItemSpecId.create(4), ItemSpecId.create(5)),
        required_quantity=6,
        state_key="stock",
        need_type="HUNGER",
        need_threshold=7,
        hp_ratio=0.25,
        required_time_of_day_phase="night",
        required_weather_type="STORM",
        item_spec_id_parameter_key="item_spec_id",
        required_lighting="PITCH_BLACK",
        required_spot_id=SpotId.create(8),
    )
    interaction = replace(obj.interactions[0], preconditions=(condition,))
    interior = interior.replace_object(replace(obj, interactions=(interaction,)))

    loaded = loads_spot_interior(dumps_spot_interior(interior))

    assert loaded.objects[0].interactions[0].preconditions == (condition,)


def test_interaction_condition_codec_covers_every_dataclass_field() -> None:
    """条件フィールド追加時にcodec追従を忘れると、構造試験が即座に失敗する。"""
    assert set(_INTERACTION_CONDITION_FIELD_CODECS) == {
        field.name for field in fields(InteractionCondition)
    }


def test_interaction_condition_decoder_keeps_legacy_payload_defaults() -> None:
    """新フィールドを持たない既存SQLite payloadも従来の既定値で復元できる。"""
    restored = _interaction_condition_from_dict({
        "condition_type": "HAS_ITEM",
        "target_item_spec_id": 1,
        "failure_message": "鍵が必要だ。",
    })

    assert restored == InteractionCondition(
        condition_type=InteractionConditionTypeEnum.HAS_ITEM,
        target_item_spec_id=ItemSpecId.create(1),
        failure_message="鍵が必要だ。",
    )


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("required_item_spec_ids", "12"),
        ("required_quantity", True),
        ("required_spot_id", True),
        ("hp_ratio", "0.5"),
        ("required_state", []),
        ("required_player_count", 1.5),
        ("required_lighting", 1),
    ],
)
def test_interaction_condition_decoder_rejects_invalid_json_types(
    field_name: str, invalid_value: object,
) -> None:
    """不正なJSON型をIDや数量へ暗黙変換せず、永続化例外で停止する。"""
    payload = {"condition_type": "ALWAYS", field_name: invalid_value}

    with pytest.raises(SpotGraphStateDecodeError, match=field_name):
        _interaction_condition_from_dict(payload)


def test_spot_interior_v1_payload_remains_readable() -> None:
    """新しい条件項目を持たないschema v1は後方互換で読み込める。"""
    payload = json.loads(dumps_spot_interior(_switch_interior()))
    payload["schema_version"] = 1
    for condition in payload["objects"][0]["interactions"][0]["preconditions"]:
        for field_name in _INTERACTION_CONDITION_FIELD_CODECS:
            if field_name not in {
                "condition_type", "target_item_spec_id", "target_object_id",
                "required_state", "flag_name", "failure_message",
            }:
                condition.pop(field_name, None)

    loaded = loads_spot_interior(json.dumps(payload))

    assert loaded.objects[0].interactions[0].preconditions[0].required_quantity == 1


def test_spot_interior_writer_emits_schema_v2() -> None:
    """全条件項目を保存するpayloadは、旧実装が誤受理しないschema v2を名乗る。"""
    payload = json.loads(dumps_spot_interior(_switch_interior()))

    assert payload["schema_version"] == 2


def test_sqlite_roundtrip_bidirectional() -> None:
    graph = _bidirectional_graph()
    conn = _memory_connection()
    seed_spot_graph_to_sqlite(conn, graph, None)

    g_repo = SqliteSpotGraphRepository.for_standalone_connection(conn)
    loaded = g_repo.find_graph()
    assert spot_graph_aggregate_to_json_dict(loaded) == spot_graph_aggregate_to_json_dict(graph)


def test_sqlite_roundtrip_preserves_passage_field() -> None:
    """SpotConnection.passage が SQLite ラウンドトリップで保持される。"""
    g = SpotGraphAggregate.empty(SpotGraphId.create(99))
    g.add_spot(_node(1))
    g.add_spot(_node(2))
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(7),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="教室間の壁",
            description="",
            travel_ticks=1,
            is_bidirectional=False,
            passage=Passage.wall(WallStateEnum.CRACKED),
        ),
    )
    g.place_entity(EntityId.create(1), SpotId.create(1))
    g.clear_events()

    conn = _memory_connection()
    seed_spot_graph_to_sqlite(conn, g, None)
    loaded = SqliteSpotGraphRepository.for_standalone_connection(conn).find_graph()
    loaded_conn = loaded.get_connection(ConnectionId.create(7))
    assert loaded_conn.passage.kind.value == "WALL"
    assert loaded_conn.passage.state == "CRACKED"
    assert loaded_conn.passage.traversable is False
    assert loaded_conn.passage.sound_permeability == pytest.approx(0.4)


def test_sqlite_roundtrip_parallel_edges_preserves_pairing() -> None:
    graph = _parallel_edge_graph()
    conn = _memory_connection()
    seed_spot_graph_to_sqlite(conn, graph, None)

    loaded = SqliteSpotGraphRepository.for_standalone_connection(conn).find_graph()

    assert spot_graph_aggregate_to_json_dict(loaded) == spot_graph_aggregate_to_json_dict(graph)


def test_sqlite_roundtrip_preserves_optional_spot_position() -> None:
    """SpotNode.position は SQLite の集約 JSON に保存され、読み戻しても同じ座標を持つ。"""
    graph = SpotGraphAggregate.empty(SpotGraphId.create(77))
    graph.add_spot(
        SpotNode(
            spot_id=SpotId.create(1),
            name="海岸",
            description="島の東側の海岸",
            category=SpotCategoryEnum.OTHER,
            parent_id=None,
            position=SpotPosition(x=10.5, y=-4.0),
        )
    )
    graph.add_spot(_node(2))
    graph.clear_events()

    payload = spot_graph_aggregate_to_json_dict(graph)
    assert payload["spots"][0]["position"] == {"x": 10.5, "y": -4.0}
    assert "position" not in payload["spots"][1]

    loaded = loads_spot_graph_aggregate(dumps_spot_graph_aggregate(graph))

    assert spot_graph_aggregate_to_json_dict(loaded) == payload
    assert loaded.get_spot(SpotId.create(1)).position == SpotPosition(x=10.5, y=-4.0)
    assert loaded.get_spot(SpotId.create(2)).position is None


def test_sqlite_roundtrip_preserves_optional_spot_area_id() -> None:
    """SpotNode.area_id は SQLite の集約 JSON に保存され、読み戻しても同じ値を持つ。"""
    graph = SpotGraphAggregate.empty(SpotGraphId.create(78))
    graph.add_spot(
        SpotNode(
            spot_id=SpotId.create(1),
            name="海岸",
            description="島の東側の海岸",
            category=SpotCategoryEnum.OTHER,
            parent_id=None,
            area_id="shore",
        )
    )
    graph.add_spot(_node(2))
    graph.clear_events()

    payload = spot_graph_aggregate_to_json_dict(graph)
    assert payload["spots"][0]["area_id"] == "shore"
    assert "area_id" not in payload["spots"][1]

    loaded = loads_spot_graph_aggregate(dumps_spot_graph_aggregate(graph))

    assert spot_graph_aggregate_to_json_dict(loaded) == payload
    assert loaded.get_spot(SpotId.create(1)).area_id == "shore"
    assert loaded.get_spot(SpotId.create(2)).area_id is None


def test_sqlite_roundtrip_preserves_object_unavailable_hint() -> None:
    """SpotObject.unavailable_hint は interior JSON に保存され、再開後も prompt 表示に使える。"""
    interior = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=SpotObjectId.create(1),
                name="水場",
                description="水が汲める。",
                object_type=SpotObjectTypeEnum.OTHER,
                state={"available": False},
                interactions=(),
                unavailable_hint="今は汲めない・時間を置けば戻る",
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )

    payload = spot_interior_to_json_dict(interior)
    assert payload["objects"][0]["unavailable_hint"] == "今は汲めない・時間を置けば戻る"

    loaded = loads_spot_interior(dumps_spot_interior(interior))

    assert spot_interior_to_json_dict(loaded) == payload
    assert loaded.objects[0].unavailable_hint == "今は汲めない・時間を置けば戻る"


def test_sqlite_encode_includes_object_display_properties() -> None:
    """物体の表示規則・隠す key・暗所可視性は SQLite payload へ書き出される。"""
    interior = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=SpotObjectId.create(1),
                name="箱",
                description="蓋のある箱。",
                object_type=SpotObjectTypeEnum.CHEST,
                state={"opened": False, "read": False},
                interactions=(),
                is_visible_in_dark=True,
                hidden_state_keys=frozenset({"read"}),
                state_display=(
                    StateDisplayRule("opened", False, "蓋は閉じたまま"),
                    StateDisplayRule("opened", True, "蓋が開いている"),
                ),
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )

    payload = spot_interior_to_json_dict(interior)

    assert payload["objects"][0]["is_visible_in_dark"] is True
    assert payload["objects"][0]["hidden_state_keys"] == ["read"]
    assert payload["objects"][0]["state_display"] == [
        {"key": "opened", "value": False, "text": "蓋は閉じたまま"},
        {"key": "opened", "value": True, "text": "蓋が開いている"},
    ]


def test_sqlite_decode_restores_object_display_properties() -> None:
    """SQLite payload から表示規則・隠す key・暗所可視性を復元する。"""
    payload = {
        "schema_version": 1,
        "sub_locations": [],
        "objects": [
            {
                "object_id": 1,
                "name": "箱",
                "description": "蓋のある箱。",
                "object_type": "CHEST",
                "state": {"opened": False, "read": False},
                "interactions": [],
                "is_visible": True,
                "is_visible_in_dark": True,
                "hidden_state_keys": ["read"],
                "state_display": [
                    {"key": "opened", "value": False, "text": "蓋は閉じたまま"},
                    {"key": "opened", "value": True, "text": "蓋が開いている"},
                ],
                "ground_items": [],
            }
        ],
        "ground_items": [],
        "discoverable_items": [],
    }

    loaded = loads_spot_interior(json.dumps(payload, ensure_ascii=False))
    obj = loaded.objects[0]

    assert obj.is_visible_in_dark is True
    assert obj.hidden_state_keys == frozenset({"read"})
    assert [(rule.key, rule.value, rule.text) for rule in obj.state_display] == [
        ("opened", False, "蓋は閉じたまま"),
        ("opened", True, "蓋が開いている"),
    ]
    assert obj.visible_state() == {"__tags__": ("蓋は閉じたまま",)}


def test_sqlite_roundtrip_preserves_object_display_properties() -> None:
    """表示規則・隠す key・暗所可視性は保存と読み戻しを通っても失われない。"""
    interior = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=SpotObjectId.create(1),
                name="箱",
                description="蓋のある箱。",
                object_type=SpotObjectTypeEnum.CHEST,
                state={"opened": False, "read": False},
                interactions=(),
                is_visible_in_dark=True,
                hidden_state_keys=frozenset({"read"}),
                state_display=(
                    StateDisplayRule("opened", False, "蓋は閉じたまま"),
                ),
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )

    loaded = loads_spot_interior(dumps_spot_interior(interior))

    assert spot_interior_to_json_dict(loaded) == spot_interior_to_json_dict(interior)
    assert loaded.objects[0].is_visible_in_dark is True
    assert loaded.objects[0].visible_state() == {"__tags__": ("蓋は閉じたまま",)}


def test_sqlite_roundtrip_preserves_recent_tick_display_rule() -> None:
    """within_ticks と requires_light は保存 payload と復元後の両方に残る。"""
    interior = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=SpotObjectId.create(1),
                name="通気口",
                description="壁の下部にある格子。",
                object_type=SpotObjectTypeEnum.OTHER,
                state={"opened_at_tick": 7},
                interactions=(),
                hidden_state_keys=frozenset({"opened_at_tick"}),
                state_display=(
                    StateDisplayRule(
                        "opened_at_tick",
                        None,
                        "格子の縁の埃が乱れている",
                        within_ticks=5,
                        requires_light=True,
                    ),
                ),
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )

    payload = json.loads(dumps_spot_interior(interior))
    assert payload["objects"][0]["state_display"] == [
        {
            "key": "opened_at_tick",
            "text": "格子の縁の埃が乱れている",
            "within_ticks": 5,
            "requires_light": True,
        }
    ]

    loaded = loads_spot_interior(json.dumps(payload, ensure_ascii=False))
    rule = loaded.objects[0].state_display[0]
    assert rule.within_ticks == 5
    assert rule.requires_light is True


def test_sqlite_roundtrip_preserves_at_least_display_rule() -> None:
    """at_least の下限は保存 payload と復元後の両方に残る。"""
    interior = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=SpotObjectId.create(1),
                name="作業台",
                description="途中の作業が載っている。",
                object_type=SpotObjectTypeEnum.OTHER,
                state={"progress": 3},
                interactions=(),
                state_display=(
                    StateDisplayRule(
                        "progress",
                        None,
                        "作業はかなり進んでいる",
                        at_least=2,
                    ),
                ),
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )

    payload = json.loads(dumps_spot_interior(interior))
    assert payload["objects"][0]["state_display"] == [
        {
            "key": "progress",
            "text": "作業はかなり進んでいる",
            "at_least": 2,
        }
    ]

    loaded = loads_spot_interior(json.dumps(payload, ensure_ascii=False))
    rule = loaded.objects[0].state_display[0]
    assert rule.at_least == 2
    assert loaded.objects[0].visible_state() == {
        "__tags__": ("作業はかなり進んでいる",)
    }


def test_find_graph_without_snapshot_raises_specific_exception() -> None:
    repo = SqliteSpotGraphRepository.for_standalone_connection(_memory_connection())
    with pytest.raises(SpotGraphSnapshotNotInitializedError):
        repo.find_graph()


def test_find_graph_invalid_json_raises_decode_error() -> None:
    conn = _memory_connection()
    repo = SqliteSpotGraphRepository.for_standalone_connection(conn)
    conn.execute("INSERT INTO spot_graph_snapshot (id, payload_json) VALUES (1, ?)", ("not json",))
    conn.commit()

    with pytest.raises(SpotGraphStateDecodeError):
        repo.find_graph()


def test_find_graph_unsupported_schema_raises() -> None:
    conn = _memory_connection()
    repo = SqliteSpotGraphRepository.for_standalone_connection(conn)
    payload = {"schema_version": 999, "graph_id": 1, "spots": [], "connection_records": [], "entity_spot": {}}
    conn.execute(
        "INSERT INTO spot_graph_snapshot (id, payload_json) VALUES (1, ?)",
        (json.dumps(payload),),
    )
    conn.commit()

    with pytest.raises(UnsupportedSpotGraphAggregateSchemaError):
        repo.find_graph()


def test_find_interior_invalid_json_raises_decode_error() -> None:
    conn = _memory_connection()
    repo = SqliteSpotInteriorRepository.for_standalone_connection(conn)
    conn.execute(
        "INSERT INTO spot_graph_interior (spot_id, payload_json) VALUES (?, ?)",
        (1, "not json"),
    )
    conn.commit()

    with pytest.raises(SpotGraphStateDecodeError):
        repo.find_by_spot_id(SpotId.create(1))


def test_find_interior_unsupported_schema_raises() -> None:
    conn = _memory_connection()
    repo = SqliteSpotInteriorRepository.for_standalone_connection(conn)
    conn.execute(
        "INSERT INTO spot_graph_interior (spot_id, payload_json) VALUES (?, ?)",
        (1, json.dumps({"schema_version": 999, "sub_locations": [], "objects": [], "ground_items": [], "discoverable_items": []})),
    )
    conn.commit()

    with pytest.raises(UnsupportedSpotInteriorSchemaError):
        repo.find_by_spot_id(SpotId.create(1))


def test_shared_uow_graph_repository_write_requires_transaction() -> None:
    repo = SqliteSpotGraphRepository.for_shared_unit_of_work(_memory_connection())
    with pytest.raises(RuntimeError, match="アクティブなトランザクション内"):
        repo.save(_bidirectional_graph())


def test_shared_uow_interior_repository_write_requires_transaction() -> None:
    repo = SqliteSpotInteriorRepository.for_shared_unit_of_work(_memory_connection())
    with pytest.raises(RuntimeError, match="アクティブなトランザクション内"):
        repo.save(SpotId.create(1), _switch_interior())


def test_seed_rejects_unknown_interior_spot_and_rolls_back() -> None:
    conn = _memory_connection()
    graph = _bidirectional_graph()

    with pytest.raises(SpotNotInGraphException):
        seed_spot_graph_to_sqlite(conn, graph, {SpotId.create(999): _switch_interior()})

    row = conn.execute("SELECT COUNT(*) FROM spot_graph_snapshot").fetchone()
    assert row is not None
    assert int(row[0]) == 0


def test_seed_rolls_back_when_interior_serialization_fails() -> None:
    conn = _memory_connection()
    graph = _bidirectional_graph()
    bad_interior = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=SpotObjectId.create(1),
                name="Broken",
                description="",
                object_type=SpotObjectTypeEnum.OTHER,
                state={"broken": {1}},
                interactions=(),
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )

    with pytest.raises(TypeError):
        seed_spot_graph_to_sqlite(conn, graph, {SpotId.create(1): bad_interior})

    row = conn.execute("SELECT COUNT(*) FROM spot_graph_snapshot").fetchone()
    assert row is not None
    assert int(row[0]) == 0


def test_loads_spot_graph_aggregate_rejects_broken_bidirectional_record() -> None:
    payload = {
        "schema_version": 2,
        "graph_id": 1,
        "spots": [
            {"spot_id": 1, "name": "S1", "description": "d", "category": "OTHER", "parent_id": None},
            {"spot_id": 2, "name": "S2", "description": "d", "category": "OTHER", "parent_id": None},
        ],
        "connection_records": [
            {
                "kind": "bidirectional",
                "conn": {
                    "connection_id": 1,
                    "from_spot_id": 1,
                    "to_spot_id": 2,
                    "name": "door",
                    "description": "",
                    "travel_ticks": 1,
                    "is_bidirectional": True,
                    "passage_conditions": [],
                    "passage": {
                        "kind": "OPEN",
                        "state": "OPEN",
                        "traversable": True,
                        "sound_permeability": 1.0,
                    },
                },
            }
        ],
        "entity_spot": {},
    }

    with pytest.raises(SpotGraphConnectionRecordInvariantError):
        loads_spot_graph_aggregate(json.dumps(payload))


def test_dumps_spot_graph_aggregate_uses_explicit_pairing_for_parallel_edges() -> None:
    payload = json.loads(dumps_spot_graph_aggregate(_parallel_edge_graph()))
    bidirectional = [record for record in payload["connection_records"] if record["kind"] == "bidirectional"]

    assert len(bidirectional) == 2
    assert {(record["conn"]["connection_id"], record["reverse_connection_id"]) for record in bidirectional} == {
        (1, 2),
        (4, 5),
    }
