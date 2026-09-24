"""動的引数候補表が実行時候補と同じ集合を保存することを保証する。"""

from ai_rpg_world.application.llm.contracts.dtos import (
    DestinationToolRuntimeTargetDto,
    InventoryToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    WorldObjectToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services.dynamic_argument_candidates import (
    build_dynamic_argument_candidate_snapshot,
    evaluate_dynamic_argument_choice,
)


def test_snapshot_keeps_action_names_attached_to_their_target() -> None:
    """interact.action_name は対象ごとの対応を崩さず、対象名と一緒に保存する。"""
    context = ToolRuntimeContextDto(
        targets={
            "O1": WorldObjectToolRuntimeTargetDto(
                label="O1",
                kind="spot_graph_object",
                display_name="東の祭壇",
                available_interactions=("offer_wheat", "offer_gold"),
            ),
            "O2": WorldObjectToolRuntimeTargetDto(
                label="O2",
                kind="spot_graph_object",
                display_name="西の祭壇",
                available_interactions=("offer_herb",),
            ),
        }
    )

    snapshot = build_dynamic_argument_candidate_snapshot(context, {"interact"})

    assert snapshot["entries"] == [
        {
            "tool": "interact",
            "argument": "target_label",
            "values": ["東の祭壇", "西の祭壇"],
        },
        {
            "tool": "interact",
            "argument": "action_name",
            "target": "東の祭壇",
            "values": ["offer_wheat", "offer_gold"],
        },
        {
            "tool": "interact",
            "argument": "action_name",
            "target": "西の祭壇",
            "values": ["offer_herb"],
        },
    ]


def test_snapshot_includes_generic_spot_graph_objects_with_interactions() -> None:
    """spot graph の一般DTOでも操作候補があれば interact の対象と操作を保存する。"""
    context = ToolRuntimeContextDto(
        targets={
            "O1": ToolRuntimeTargetDto(
                label="O1",
                kind="spot_graph_object",
                display_name="気象記録簿",
                available_interactions=("log_weather_pretend",),
            ),
        }
    )

    snapshot = build_dynamic_argument_candidate_snapshot(context, {"interact"})

    assert snapshot["entries"] == [
        {
            "tool": "interact",
            "argument": "target_label",
            "values": ["気象記録簿"],
        },
        {
            "tool": "interact",
            "argument": "action_name",
            "target": "気象記録簿",
            "values": ["log_weather_pretend"],
        },
    ]


def test_snapshot_only_contains_candidates_for_exposed_tools() -> None:
    """非公開ツールの候補は、runtime context に値があっても候補表へ載せない。"""
    context = ToolRuntimeContextDto(
        targets={
            "D1": DestinationToolRuntimeTargetDto(label="D1", kind="spot_graph_destination", display_name="山道"),
            "I1": InventoryToolRuntimeTargetDto(label="I1", kind="inventory_item", display_name="薬草"),
        }
    )

    snapshot = build_dynamic_argument_candidate_snapshot(context, {"travel_to"})

    assert snapshot["entries"] == [
        {
            "tool": "travel_to",
            "argument": "destination_label",
            "values": ["山道"],
        }
    ]


def test_snapshot_separates_give_item_player_and_item_candidates() -> None:
    """give_item は渡す品と相手を別引数の候補として保存する。"""
    context = ToolRuntimeContextDto(
        targets={
            "P1": PlayerToolRuntimeTargetDto(label="P1", kind="spot_graph_player", display_name="ユノ", player_id=2),
            "I1": InventoryToolRuntimeTargetDto(label="I1", kind="inventory_item", display_name="麦束"),
        }
    )

    snapshot = build_dynamic_argument_candidate_snapshot(context, {"give_item"})

    assert snapshot["entries"] == [
        {
            "tool": "give_item",
            "argument": "gives[].item_label",
            "values": ["麦束"],
        },
        {
            "tool": "give_item",
            "argument": "gives[].target_player_label",
            "values": ["ユノ"],
        },
    ]


def test_evaluation_checks_action_against_the_selected_target() -> None:
    """interact は対象名が有効でも、別対象の action_name なら入力ミスと判定する。"""
    snapshot = {
        "entries": [
            {"tool": "interact", "argument": "target_label", "values": ["東", "西"]},
            {
                "tool": "interact",
                "argument": "action_name",
                "target": "東",
                "values": ["offer_wheat"],
            },
            {
                "tool": "interact",
                "argument": "action_name",
                "target": "西",
                "values": ["offer_herb"],
            },
        ]
    }

    result = evaluate_dynamic_argument_choice(
        "interact",
        {"target_label": "東", "action_name": "offer_herb"},
        snapshot,
    )

    assert result["status"] == "invalid"
    assert result["violations"][0]["argument"] == "action_name"


def test_evaluation_checks_every_give_entry_without_executing_current_code() -> None:
    """give_item は各配列要素を保存済み候補へ照合し、現在の世界コードを実行しない。"""
    snapshot = {
        "entries": [
            {"tool": "give_item", "argument": "gives[].item_label", "values": ["麦束"]},
            {
                "tool": "give_item",
                "argument": "gives[].target_player_label",
                "values": ["ユノ"],
            },
        ]
    }

    result = evaluate_dynamic_argument_choice(
        "give_item",
        {
            "gives": [
                {"item_label": "麦束", "target_player_label": "ユノ"},
                {"item_label": "薬草", "target_player_label": "ユノ"},
            ]
        },
        snapshot,
    )

    assert result["status"] == "invalid"
    assert result["violations"] == [
        {
            "argument": "gives[1].item_label",
            "value": "薬草",
            "allowed": ["麦束"],
            "reason": "not_in_candidates",
        }
    ]
