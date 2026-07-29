"""直近出来事に保存する action_summary の自然文整形を保証する。"""

from ai_rpg_world.application.llm.llm_argument_fingerprint import (
    build_argument_fingerprint,
)
from ai_rpg_world.application.llm.services.action_summary_format import (
    ACTION_SUMMARY_FORMATTERS,
    ACTION_SUMMARY_HIDDEN_FIELDS,
    INTENTIONAL_ACTION_SUMMARY_FALLBACK_TOOLS,
    format_action_summary_for_display,
)
from ai_rpg_world.application.llm.services.tool_catalog.memory import get_memory_specs
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    get_spot_graph_specs,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMO_ADD,
    TOOL_NAME_MEMO_DONE,
    TOOL_NAME_SPEECH,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
)


_FULL_ARGS = {
    "target_label": "OBJ1",
    "action_name": "inspect",
    "inner_thought": "何か手がかりがあるはずだ",
    "intention": "祭壇の封印の手がかりを探す",
    "expected_result": "祭壇から封印の手がかりが得られる",
    "emotion_hint": "curiosity",
}


def _all_declared_tool_names() -> set[str]:
    spot = {definition.name for definition, _ in get_spot_graph_specs()}
    memory = {
        definition.name
        for definition, _ in get_memory_specs(
            memo_enabled=True,
            episodic_recall_enabled=True,
            recall_by_handle_enabled=True,
            episodic_explore_related_enabled=True,
            semantic_search_enabled=True,
        )
    }
    return spot | memory


class TestFormatActionSummaryForDisplay:
    """各 tool の行動要約が自然文か明示フォールバックのどちらかになることを保証する。"""

    def test_all_tools_are_explicitly_classified_for_natural_text_or_fallback(
        self,
    ) -> None:
        """新 tool を足したら自然文あり / 意図的フォールバックのどちらかに分類しないと落ちる。"""
        natural = set(ACTION_SUMMARY_FORMATTERS)
        fallback = set(INTENTIONAL_ACTION_SUMMARY_FALLBACK_TOOLS)
        all_tools = _all_declared_tool_names()

        assert natural | fallback == all_tools
        assert natural & fallback == set()

    def test_natural_text_examples_for_high_volume_tools(self) -> None:
        """speak / memo / spot action は JSON ではなく短い自然文になる。"""
        assert (
            format_action_summary_for_display(
                TOOL_NAME_SPEECH,
                {"channel": "say", "content": "北へ行く"},
            )
            == "あなたは言った: 「北へ行く」"
        )
        assert (
            format_action_summary_for_display(TOOL_NAME_MEMO_ADD, {"content": "長い本文"})
            == "メモを書いた"
        )
        assert (
            format_action_summary_for_display(
                TOOL_NAME_MEMO_DONE,
                {"memo_ids": ["bb0aaa", "88cd0a", "bda741"]},
            )
            == "メモ 3 件を完了にした (bb0aaa, 88cd0a, bda741)"
        )
        assert (
            format_action_summary_for_display(
                TOOL_NAME_SPOT_GRAPH_INTERACT,
                {"target_label": "流木の山", "action_name": "gather"},
            )
            == "「流木の山」に gather した"
        )
        assert (
            format_action_summary_for_display(
                TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
                {"destination_label": "干潟"},
            )
            == "干潟へ移動した"
        )
        assert (
            format_action_summary_for_display(
                TOOL_NAME_SPOT_GRAPH_USE_ITEM,
                {"item_label": "貝"},
            )
            == "「貝」を使った"
        )
        assert (
            format_action_summary_for_display(TOOL_NAME_SPOT_GRAPH_LISTEN, {})
            == "耳を澄ました"
        )
        assert (
            format_action_summary_for_display(TOOL_NAME_SPOT_GRAPH_EXPLORE, {})
            == "この場所を探索した"
        )

    def test_hidden_fields_include_inner_thought_and_duplicate_content(self) -> None:
        """JSON フォールバックから心の声・発話本文・メモ本文・予測などの重複入力を落とす。"""
        assert ACTION_SUMMARY_HIDDEN_FIELDS == frozenset(
            {
                "content",
                "reason",
                "inner_thought",
                "intention",
                "expected_result",
                "emotion_hint",
            }
        )

    def test_unknown_tool_falls_back_without_exposing_hidden_fields(self) -> None:
        """look_around のような幻覚 tool 名でも例外を投げず、隠すべき入力は JSON に出さない。"""
        out = format_action_summary_for_display(
            "look_around",
            {
                "content": "本文",
                "inner_thought": "考え",
                "expected_result": "予測",
                "target_label": "周囲",
            },
        )
        assert out == 'look_around({"target_label": "周囲"}) を実行しました。'
        assert "content" not in out
        assert "inner_thought" not in out
        assert "expected_result" not in out

    def test_no_args_returns_bare_summary(self) -> None:
        """args が空なら自然文 formatter は空入力向けの短文を返す。"""
        assert format_action_summary_for_display(TOOL_NAME_SPOT_GRAPH_EXPLORE, None) == "この場所を探索した"

    def test_does_not_mutate_input_args(self) -> None:
        """入力 args を破壊しない。"""
        args = dict(_FULL_ARGS)
        format_action_summary_for_display(TOOL_NAME_SPOT_GRAPH_INTERACT, args)
        assert args == _FULL_ARGS

    def test_fingerprint_is_independent_of_display(self) -> None:
        """loop_guard 用 fingerprint は raw args から計算され、表示整形に影響されない。"""
        fp_full = build_argument_fingerprint(_FULL_ARGS)
        fp_outcome_only = build_argument_fingerprint(
            {"target_label": "OBJ1", "action_name": "inspect"}
        )
        assert fp_full == fp_outcome_only
