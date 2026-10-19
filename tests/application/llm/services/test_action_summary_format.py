"""直近出来事に保存する action_summary の自然文整形を保証する。"""

from ai_rpg_world.application.llm.llm_argument_fingerprint import (
    build_argument_fingerprint,
)
from ai_rpg_world.application.llm.services.action_summary_format import (
    ACTION_DISPLAY_PHRASE_KEY,
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
    "emotion_hint": "curiosity",
}


def _all_declared_tool_names() -> set[str]:
    spot = {definition.name for definition, _ in get_spot_graph_specs()}
    memory = {
        definition.name
        for definition, _ in get_memory_specs(
            episode_recall_max_handles=3,
            episode_index_revision_enabled=True,
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
        """speak / spot action は JSON ではなく短い自然文になる。"""
        assert (
            format_action_summary_for_display(
                TOOL_NAME_SPEECH,
                {"channel": "say", "content": "北へ行く"},
            )
            == "あなたは言った: 「北へ行く」"
        )
        assert (
            format_action_summary_for_display(
                TOOL_NAME_SPOT_GRAPH_INTERACT,
                {"target_label": "流木の山", "action_name": "gather"},
            )
            == "「流木の山」に働きかけた"
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
        """JSON フォールバックから心の声・発話本文・メモ帳への書き込みなどの重複入力を落とす。"""
        assert ACTION_SUMMARY_HIDDEN_FIELDS == frozenset(
            {
                "content",
                "reason",
                "inner_thought",
                "intention",
                "memo",
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
                "target_label": "周囲",
            },
        )
        assert out == 'look_around({"target_label": "周囲"}) を実行しました。'
        assert "content" not in out
        assert "inner_thought" not in out

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


class TestInteractSummaryUsesTheDisplayLabel:
    """interact の行動の行が、resolver の運んだ表示名を action_name より優先することを保証する。"""

    def test_display_phrase_replaces_the_action_name(self) -> None:
        """resolver が対象名の後ろに続く句 (ACTION_DISPLAY_PHRASE_KEY) を運んでいれば「「対象」〈句〉」と書き、action_name を出さない。成功の行と同じ書き方にそろえる。"""
        summary = format_action_summary_for_display(
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            {"target_label": "昇降機", "action_name": "start_lift", ACTION_DISPLAY_PHRASE_KEY: "で鍵を差して昇降機を動かす"},
        )

        assert summary == "「昇降機」で鍵を差して昇降機を動かす"

    def test_without_display_phrase_the_action_name_is_not_written(self) -> None:
        """表示名が届かない行 (候補に無い操作名で断られたときなど) も、操作名を書かず「「対象」に働きかけた」と書く (#1564)。操作名は呼び出しの値で、世界の言葉ではない。"""
        summary = format_action_summary_for_display(
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            {"target_label": "カンテラ", "action_name": "light_lamp"},
        )

        assert summary == "「カンテラ」に働きかけた"
