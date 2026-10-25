"""動的引数候補表が実行時候補と同じ集合を保存することを保証する。"""

from ai_rpg_world.application.llm.contracts.dtos import (
    DestinationToolRuntimeTargetDto,
    InventoryToolRuntimeTargetDto,
    MerchantOfferDto,
    MerchantToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
    WorldObjectToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services.dynamic_argument_candidates import (
    build_dynamic_argument_candidate_snapshot,
    evaluate_dynamic_argument_choice,
    inject_dynamic_argument_candidate_table,
    parse_dynamic_argument_candidate_table,
    render_dynamic_argument_candidate_table,
)


def _display_entries(entries: list[dict]) -> list[dict]:
    """表示契約だけを見る試験では、実行時照合専用の補助情報を除く。"""
    hidden = {
        "match",
        "accepted_values",
        "target_accepted_values",
        "required",
        "required_when",
        "alternative",
        "allow_empty",
    }
    return [{key: value for key, value in entry.items() if key not in hidden} for entry in entries]


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

    assert _display_entries(snapshot["entries"]) == [
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

    assert _display_entries(snapshot["entries"]) == [
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

    assert _display_entries(snapshot["entries"]) == [
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

    assert _display_entries(snapshot["entries"]) == [
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


def test_snapshot_covers_meeting_communication_trade_and_management_targets() -> None:
    """会議・会話・取引・ギルド・ショップ・任務の対象引数を公開ツールごとに列挙する。"""
    context = ToolRuntimeContextDto(
        targets={
            "P1": PlayerToolRuntimeTargetDto(
                label="P1", kind="spot_graph_player", display_name="ユノ", player_id=2
            ),
            "SL1": ToolRuntimeTargetDto(
                label="SL1", kind="spot_graph_sub_location", display_name="机の下"
            ),
            "G1": ToolRuntimeTargetDto(label="G1", kind="guild", display_name="調査隊"),
            "SH1": ToolRuntimeTargetDto(label="SH1", kind="shop", display_name="雑貨店"),
            "L1": ToolRuntimeTargetDto(
                label="L1", kind="shop_listing", display_name="薬草の出品"
            ),
            "Q1": ToolRuntimeTargetDto(label="Q1", kind="quest", display_name="失踪者捜索"),
        }
    )
    exposed = {
        "set_sub_location",
        "speak",
        "vote",
        "report_body",
        "trade_offer",
        "trade_accept",
        "guild_add_member",
        "shop_purchase",
        "quest_accept",
    }

    snapshot = build_dynamic_argument_candidate_snapshot(context, exposed)
    candidates = {
        (entry["tool"], entry["argument"]): entry["values"]
        for entry in snapshot["entries"]
    }

    assert candidates == {
        ("set_sub_location", "sub_location_label"): ["机の下"],
        ("speak", "target_label"): ["ユノ"],
        ("vote", "target_player_label"): ["ユノ", ""],
        ("report_body", "target_player_label"): ["ユノ"],
        ("trade_offer", "target_player_label"): ["ユノ"],
        ("trade_accept", "offerer_player_label"): ["ユノ"],
        ("guild_add_member", "guild_label"): ["G1"],
        ("guild_add_member", "target_player_label"): ["P1"],
        ("shop_purchase", "shop_label"): ["SH1"],
        ("shop_purchase", "listing_label"): ["L1"],
        ("quest_accept", "quest_label"): ["Q1"],
    }


def test_tend_to_player_uses_the_schema_argument_name() -> None:
    """tend_to_player は実際の schema と同じ target_player_label を表示する。"""
    context = ToolRuntimeContextDto(
        targets={
            "P1": PlayerToolRuntimeTargetDto(
                label="P1", kind="spot_graph_player", display_name="ユノ", player_id=2
            )
        }
    )

    snapshot = build_dynamic_argument_candidate_snapshot(context, {"tend_to_player"})

    assert snapshot["entries"][0]["argument"] == "target_player_label"


def test_speak_target_candidates_are_names_of_people_in_the_same_place() -> None:
    """同じ場所にいる人への囁き先の候補は、内部ラベル P1 ではなく名前で出る。"""
    context = ToolRuntimeContextDto(
        targets={
            "P1": PlayerToolRuntimeTargetDto(
                label="P1", kind="spot_graph_player", display_name="ユノ", player_id=2
            ),
            "P2": PlayerToolRuntimeTargetDto(
                label="P2", kind="spot_graph_player", display_name="カイ", player_id=3
            ),
        }
    )

    snapshot = build_dynamic_argument_candidate_snapshot(context, {"speak"})

    assert '- speak.target_label: "ユノ", "カイ"' in snapshot["rendered"]
    assert "P1" not in snapshot["rendered"]


def test_whisper_by_name_or_internal_label_is_judged_valid() -> None:
    """囁き先は、実行時の解決と同じく名前でも内部ラベルでも候補に当たる。"""
    context = ToolRuntimeContextDto(
        targets={
            "P1": PlayerToolRuntimeTargetDto(
                label="P1", kind="spot_graph_player", display_name="ユノ", player_id=2
            ),
        }
    )
    snapshot = build_dynamic_argument_candidate_snapshot(context, {"speak"})

    for written in ("ユノ", "P1"):
        result = evaluate_dynamic_argument_choice(
            "speak",
            {"channel": "whisper", "content": "後で話そう", "target_label": written},
            snapshot,
        )
        assert result["status"] == "valid", written


def test_snapshot_covers_trade_items_and_merchant_offers() -> None:
    """個人間取引の差出品と、商人売買の品・商人名も対象候補へ含める。"""
    context = ToolRuntimeContextDto(
        targets={
            "I1": InventoryToolRuntimeTargetDto(
                label="I1", kind="inventory_item", display_name="薬草"
            ),
            "MR1": MerchantToolRuntimeTargetDto(
                label="MR1",
                kind="merchant",
                display_name="商人グスタフ",
                sells=(MerchantOfferDto(item_name="パン", item_spec_id=1, price=3),),
                buys=(MerchantOfferDto(item_name="薬草", item_spec_id=2, price=2),),
            ),
        }
    )

    snapshot = build_dynamic_argument_candidate_snapshot(
        context, {"trade_offer", "buy_item", "sell_item"}
    )
    candidates = {
        (entry["tool"], entry["argument"]): entry["values"]
        for entry in snapshot["entries"]
    }

    assert candidates == {
        ("trade_offer", "gives.items[].item_label"): ["薬草"],
        ("buy_item", "item_label"): ["パン"],
        ("buy_item", "merchant_label"): ["商人グスタフ"],
        ("sell_item", "item_label"): ["薬草"],
        ("sell_item", "merchant_label"): ["商人グスタフ"],
    }


def test_vote_keeps_abstention_when_no_player_target_exists() -> None:
    """投票対象が0人でも、空文字による棄権は候補表から消えない。"""
    snapshot = build_dynamic_argument_candidate_snapshot(
        ToolRuntimeContextDto.empty(), {"vote"}
    )

    assert snapshot["entries"][0]["values"] == [""]
    assert '- vote.target_player_label: ""' in snapshot["rendered"]




def test_candidate_table_is_inserted_immediately_before_action_instruction() -> None:
    """候補表は状態本文やツール定義へ混ぜず、末尾の行動指示の直前へ置く。"""
    instruction = "利用可能なツールから、次に取るべき 1 つの行動だけを選んでください。"
    context = ToolRuntimeContextDto(
        targets={
            "D1": DestinationToolRuntimeTargetDto(
                label="D1",
                kind="spot_graph_destination",
                display_name="集会室",
            ),
        }
    )
    prompt = {
        "messages": [
            {"role": "system", "content": "system"},
            {"role": "user", "content": f"【現在地と周囲】\n通信室\n\n{instruction}"},
        ],
        "action_instruction": instruction,
        "tool_runtime_context": context,
    }

    result = inject_dynamic_argument_candidate_table(prompt, {"travel_to"})

    user = result["messages"][-1]["content"]
    assert user.endswith(instruction)
    assert user.index("【現在選べる対象引数】") < user.index(instruction)
    assert '- travel_to.destination_label: "集会室"' in user
    assert _display_entries(result["dynamic_argument_candidates"]["entries"]) == [
        {
            "tool": "travel_to",
            "argument": "destination_label",
            "values": ["集会室"],
        }
    ]
    assert "【現在選べる対象引数】" not in prompt["messages"][-1]["content"]


def test_empty_candidate_table_keeps_prompt_bytes_unchanged() -> None:
    """動的候補がない局面では空の見出しを足さず、元の本文を完全一致で保つ。"""
    prompt = {
        "messages": [{"role": "user", "content": "次の行動を選ぶ。"}],
        "action_instruction": "次の行動を選ぶ。",
        "tool_runtime_context": ToolRuntimeContextDto.empty(),
    }

    result = inject_dynamic_argument_candidate_table(prompt, {"wait"})

    assert result["messages"] == prompt["messages"]
    assert result["dynamic_argument_candidates"]["rendered"] == ""


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


def test_evaluation_accepts_forms_that_the_runtime_resolver_accepts() -> None:
    """内部ラベル・引用符・表示行の丸写しを実行時と同じく有効と判定する。"""
    context = ToolRuntimeContextDto(
        targets={
            "O1": WorldObjectToolRuntimeTargetDto(
                label="O1",
                kind="spot_graph_object",
                display_name="東の祭壇",
                available_interactions=("offer_wheat",),
            )
        }
    )
    snapshot = build_dynamic_argument_candidate_snapshot(context, {"interact"})

    for target_label, action_name in (
        ("O1", '"offer_wheat"'),
        ('"東の祭壇"', '麦を捧げる → "offer_wheat"'),
        ("O1: 東の祭壇", "offer_wheat"),
    ):
        result = evaluate_dynamic_argument_choice(
            "interact",
            {"target_label": target_label, "action_name": action_name},
            snapshot,
        )
        assert result["status"] == "valid"
        if target_label != "東の祭壇" or action_name != "offer_wheat":
            assert result["candidate_table_status"] == "invalid"


def test_evaluation_does_not_require_optional_or_conditional_arguments() -> None:
    """省略可能・条件付きの対象引数を、resolver拒否として誤集計しない。"""
    context = ToolRuntimeContextDto(
        targets={
            "P1": PlayerToolRuntimeTargetDto(
                label="P1", kind="spot_graph_player", display_name="ユノ", player_id=2
            ),
            "Q1": ToolRuntimeTargetDto(label="Q1", kind="quest", display_name="任務"),
        }
    )
    cases = (
        ("speak", {"channel": "say", "content": "集合しよう"}),
        ("trade_accept", {}),
        ("trade_decline", {}),
        ("vote", {}),
    )

    for tool, arguments in cases:
        snapshot = build_dynamic_argument_candidate_snapshot(context, {tool})
        result = evaluate_dynamic_argument_choice(tool, arguments, snapshot)
        assert result["status"] == "valid"


def test_evaluation_checks_nested_trade_items_only_when_present() -> None:
    """個人間取引は金だけの差出しを許し、品があれば各 item_label を照合する。"""
    context = ToolRuntimeContextDto(
        targets={
            "P1": PlayerToolRuntimeTargetDto(
                label="P1", kind="spot_graph_player", display_name="ユノ", player_id=2
            ),
            "I1": InventoryToolRuntimeTargetDto(
                label="I1", kind="inventory_item", display_name="薬草"
            ),
        }
    )
    snapshot = build_dynamic_argument_candidate_snapshot(context, {"trade_offer"})

    gold_only = evaluate_dynamic_argument_choice(
        "trade_offer",
        {
            "target_player_label": "ユノ",
            "gives": {"gold": 2},
            "asks": {"items": [{"item_label": "水", "quantity": 1}]},
        },
        snapshot,
    )
    invalid_item = evaluate_dynamic_argument_choice(
        "trade_offer",
        {
            "target_player_label": "ユノ",
            "gives": {"items": [{"item_label": "毒草", "quantity": 1}]},
            "asks": {"gold": 1},
        },
        snapshot,
    )

    assert gold_only["status"] == "valid"
    assert invalid_item["status"] == "invalid"
    assert invalid_item["violations"][0]["argument"] == "gives.items[0].item_label"


def test_shop_unlist_accepts_either_listing_label_or_shop_and_listing_id() -> None:
    """出品取消は listing_label と shop_label + listing_id のどちらの経路も有効にする。"""
    context = ToolRuntimeContextDto(
        targets={
            "SH1": ToolRuntimeTargetDto(label="SH1", kind="shop", display_name="雑貨店"),
            "L1": ToolRuntimeTargetDto(
                label="L1", kind="shop_listing", display_name="薬草の出品"
            ),
        }
    )
    snapshot = build_dynamic_argument_candidate_snapshot(context, {"shop_unlist_item"})

    by_id = evaluate_dynamic_argument_choice(
        "shop_unlist_item", {"shop_label": "SH1", "listing_id": 1}, snapshot
    )
    by_label = evaluate_dynamic_argument_choice(
        "shop_unlist_item", {"listing_label": "L1"}, snapshot
    )

    assert by_id["status"] == "valid"
    assert by_label["status"] == "valid"


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


def test_parsing_the_rendered_table_returns_the_same_tools_arguments_targets_and_values() -> None:
    """表示した候補表を読み戻すと、対象つきの行・入れ子の引数・引用符を含む名前まで元の候補と一致する。"""
    entries = [
        {"tool": "travel_to", "argument": "destination_label", "values": ["集会所", "北の竪坑の底"]},
        {"tool": "interact", "argument": "action_name", "target": "古い \"金庫\"", "values": ["open_safe"]},
        {"tool": "give_item", "argument": "gives[].item_label", "values": ["燃料の缶", "カンテラ, 予備"]},
    ]
    prompt = f"本文\n\n{render_dynamic_argument_candidate_table(entries)}\n\n行動を選んでください。"

    parsed = parse_dynamic_argument_candidate_table(prompt)

    assert parsed == [
        {"tool": "travel_to", "argument": "destination_label", "target": None, "values": ["集会所", "北の竪坑の底"]},
        {"tool": "interact", "argument": "action_name", "target": '古い "金庫"', "values": ["open_safe"]},
        {"tool": "give_item", "argument": "gives[].item_label", "target": None, "values": ["燃料の缶", "カンテラ, 予備"]},
    ]


def test_parsing_a_prompt_without_the_table_returns_no_candidates() -> None:
    """候補表の見出しが無い本文からは、候補を 1 つも読み取らない。"""
    assert parse_dynamic_argument_candidate_table("- travel_to.destination_label: \"集会所\"") == []
