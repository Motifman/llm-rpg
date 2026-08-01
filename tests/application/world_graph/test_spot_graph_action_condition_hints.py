"""SpotGraphCurrentStateBuilder が action の時刻・天候制約ヒントを snapshot に載せる。"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.world_graph.spot_graph_current_state_builder import (
    SpotGraphCurrentStateBuilder,
    _format_interaction_action_name_with_hints,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


def _build_builder(
    interior: SpotInterior,
    *,
    current_tick: int = 0,
) -> SpotGraphCurrentStateBuilder:
    graph = MagicMock()
    graph.get_entity_spot.return_value = SpotId(1)
    spot_node = MagicMock()
    spot_node.name = "岩礁"
    spot_node.description = ""
    spot_node.atmosphere = None
    spot_node.is_outdoor = True
    graph.get_spot.return_value = spot_node
    graph.presence_at.return_value.present_entity_ids = frozenset()
    graph.monster_presence_at.return_value.present_monster_ids = frozenset()
    graph.iter_outgoing_connections_from.return_value = []

    spot_graph_repo = MagicMock()
    spot_graph_repo.find_graph.return_value = graph
    spot_interior_repo = MagicMock()
    spot_interior_repo.find_by_spot_id.return_value = interior
    player_status_repo = MagicMock()
    player_status_repo.find_by_id.return_value = None
    return SpotGraphCurrentStateBuilder(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        player_status_repository=player_status_repo,
        current_tick_provider=lambda: current_tick,
    )


def test_time_and_weather_preconditions_become_action_condition_hints() -> None:
    """TIME_OF_DAY_IS_NOT / WEATHER_IS_NOT は action 表示用の短い制約ヒントになる。"""
    interaction = InteractionDef(
        action_name="fish_deep",
        display_label="沖で釣りをする",
        preconditions=(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.TIME_OF_DAY_IS_NOT,
                required_time_of_day_phase="night",
            ),
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.WEATHER_IS_NOT,
                required_weather_type="STORM",
            ),
        ),
        effects=(),
    )
    interior = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=SpotObjectId.create(10),
                name="沖の釣り場",
                description="沖へ釣り糸を垂らせる。",
                object_type=SpotObjectTypeEnum.OTHER,
                state={},
                interactions=(interaction,),
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )

    snap = _build_builder(interior).build_snapshot(1)

    assert snap is not None
    assert snap.objects[0].interactions[0].condition_hints == ("夜不可", "嵐不可")


def test_write_player_text_effect_becomes_required_parameter_hint() -> None:
    """WRITE_PLAYER_TEXT は effect 宣言の text_param_key を必須入力として表示する。"""
    interaction = InteractionDef(
        action_name="write_notice",
        display_label="板切れに書き残す",
        preconditions=(),
        effects=(
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
                parameters={},
            ),
        ),
    )
    interior = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=SpotObjectId.create(10),
                name="板切れの掲示",
                description="伝言を書き残せる。",
                object_type=SpotObjectTypeEnum.SIGN,
                state={},
                interactions=(interaction,),
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )

    snap = _build_builder(interior).build_snapshot(1)

    assert snap is not None
    assert snap.objects[0].interactions[0].condition_hints == ("text が要る",)


def test_action_without_required_parameter_effect_has_no_parameter_hint() -> None:
    """必須入力を要求しない action には、存在しないパラメータのヒントを足さない。"""
    interaction = InteractionDef(
        action_name="read_notice",
        display_label="板切れを読む",
        preconditions=(),
        effects=(),
    )
    interior = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=SpotObjectId.create(10),
                name="板切れの掲示",
                description="伝言を読める。",
                object_type=SpotObjectTypeEnum.SIGN,
                state={},
                interactions=(interaction,),
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )

    snap = _build_builder(interior).build_snapshot(1)

    assert snap is not None
    assert snap.objects[0].interactions[0].condition_hints == ()


def test_unknown_time_and_weather_values_are_not_silently_dropped() -> None:
    """未知の phase/weather 値は raw 値を使い、制約ヒント自体を消さない。"""
    interaction = InteractionDef(
        action_name="ritual",
        display_label="儀式をする",
        preconditions=(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.TIME_OF_DAY_IS,
                required_time_of_day_phase="blue_hour",
            ),
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.WEATHER_IS,
                required_weather_type="METEOR_SHOWER",
            ),
        ),
        effects=(),
    )
    interior = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=SpotObjectId.create(10),
                name="儀式場",
                description="空がよく見える。",
                object_type=SpotObjectTypeEnum.OTHER,
                state={},
                interactions=(interaction,),
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )

    snap = _build_builder(interior).build_snapshot(1)

    assert snap is not None
    assert snap.objects[0].interactions[0].condition_hints == (
        "blue_hourのみ",
        "METEOR_SHOWERのみ",
    )


def test_failing_object_state_precondition_remains_with_failure_reason_hint() -> None:
    """OBJECT_STATE が現在失敗していても action を残し、失敗理由は blocking_hints にする。"""
    interaction = InteractionDef(
        action_name="open_chest",
        display_label="箱を開ける",
        preconditions=(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
                target_object_id=SpotObjectId.create(10),
                required_state={"opened": False},
                failure_message="箱はすでに空っぽだ。",
            ),
        ),
        effects=(),
    )
    interior = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=SpotObjectId.create(10),
                name="古い箱",
                description="ふたの開いた箱。",
                object_type=SpotObjectTypeEnum.OTHER,
                state={"opened": True},
                interactions=(interaction,),
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )

    snap = _build_builder(interior).build_snapshot(1)

    assert snap is not None
    assert snap.objects[0].interactions[0].action_name == "open_chest"
    assert snap.objects[0].interactions[0].condition_hints == ()
    assert snap.objects[0].interactions[0].blocking_hints == ("箱はすでに空っぽだ。",)


def test_failing_object_stock_precondition_remains_with_failure_reason_hint() -> None:
    """OBJECT_STOCK_AT_LEAST が未達なら action を残し、枯渇理由は blocking_hints にする。"""
    object_id = SpotObjectId.create(10)
    interaction = InteractionDef(
        action_name="gather_shellfish",
        display_label="貝を採る",
        preconditions=(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.OBJECT_STOCK_AT_LEAST,
                target_object_id=object_id,
                required_quantity=2,
                failure_message="貝は採り尽くした。時間が経てば戻る。",
            ),
        ),
        effects=(),
    )
    interior = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=object_id,
                name="干潟",
                description="貝を探せる。",
                object_type=SpotObjectTypeEnum.OTHER,
                state={
                    "stock": 0,
                    "stock_capacity": 3,
                    "stock_tick": 0,
                    "stock_refill_interval": 10,
                },
                interactions=(interaction,),
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )

    snap = _build_builder(interior, current_tick=5).build_snapshot(1)

    assert snap is not None
    assert snap.objects[0].interactions[0].action_name == "gather_shellfish"
    assert snap.objects[0].interactions[0].condition_hints == ()
    assert snap.objects[0].interactions[0].blocking_hints == (
        "貝は採り尽くした。時間が経てば戻る。",
    )


def test_recovered_object_stock_precondition_does_not_show_failure_hint() -> None:
    """遅延再生後に必要数へ届く備蓄には、枯渇ヒントを出さない。"""
    object_id = SpotObjectId.create(10)
    interaction = InteractionDef(
        action_name="gather_shellfish",
        display_label="貝を採る",
        preconditions=(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.OBJECT_STOCK_AT_LEAST,
                target_object_id=object_id,
                required_quantity=2,
                failure_message="貝は採り尽くした。時間が経てば戻る。",
            ),
        ),
        effects=(),
    )
    interior = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=object_id,
                name="干潟",
                description="貝を探せる。",
                object_type=SpotObjectTypeEnum.OTHER,
                state={
                    "stock": 0,
                    "stock_capacity": 3,
                    "stock_tick": 0,
                    "stock_refill_interval": 10,
                },
                interactions=(interaction,),
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )

    snap = _build_builder(interior, current_tick=20).build_snapshot(1)

    assert snap is not None
    assert snap.objects[0].interactions[0].condition_hints == ()
    assert snap.objects[0].interactions[0].blocking_hints == ()


def test_declarative_and_failing_state_hints_are_split() -> None:
    """宣言由来制約と現在の失敗理由が同時にある action は、別フィールドに分けて保持する。"""
    interaction = InteractionDef(
        action_name="search_beam",
        display_label="梁を探す",
        preconditions=(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.TIME_OF_DAY_IS_NOT,
                required_time_of_day_phase="night",
            ),
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
                target_object_id=SpotObjectId.create(10),
                required_state={"shelf_searched": False},
                failure_message="棚を調べた後",
            ),
        ),
        effects=(),
    )
    interior = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=SpotObjectId.create(10),
                name="崩れた梁",
                description="太い梁が斜めに崩れている。",
                object_type=SpotObjectTypeEnum.OTHER,
                state={"shelf_searched": True},
                interactions=(interaction,),
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )

    snap = _build_builder(interior).build_snapshot(1)

    assert snap is not None
    entry = snap.objects[0].interactions[0]
    assert entry.condition_hints == ("夜不可",)
    assert entry.blocking_hints == ("棚を調べた後",)


def test_fallback_action_text_separates_blocking_reason_from_condition_hints() -> None:
    """fallback テキストでも、現在失敗している action は「いまできない」表記に分ける。"""
    interaction = InteractionDef(
        action_name="search",
        display_label="棚を探す",
        preconditions=(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.TIME_OF_DAY_IS_NOT,
                required_time_of_day_phase="night",
            ),
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
                target_object_id=SpotObjectId.create(10),
                required_state={"shelf_searched": False},
                failure_message="棚を調べた後",
            ),
        ),
        effects=(),
    )
    interior = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=SpotObjectId.create(10),
                name="崩れた梁",
                description="太い梁が斜めに崩れている。",
                object_type=SpotObjectTypeEnum.OTHER,
                state={"shelf_searched": True},
                interactions=(interaction,),
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )

    assert (
        _format_interaction_action_name_with_hints(interaction, interior)
        == "いまできない: 棚を探す (search・棚を調べた後)"
    )
