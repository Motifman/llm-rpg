"""``tool_phase_mapping.phase_for_tool`` の対応表テスト。"""

import pytest

from ai_rpg_world.application.intent.tool_phase_mapping import phase_for_tool
from ai_rpg_world.domain.intent.value_object.intent_phase import IntentPhase


class TestPhaseForTool:
    """``phase_for_tool`` の解釈挙動。"""

    @pytest.mark.parametrize(
        "tool_name, expected",
        [
            ("travel_to", IntentPhase.MOVEMENT),
            ("interact", IntentPhase.INTERACTION),
            ("explore", IntentPhase.INTERACTION),
            ("set_sub_location", IntentPhase.MOVEMENT),
            ("wait", IntentPhase.OTHER),
            ("listen", IntentPhase.INTERACTION),
            ("say", IntentPhase.SOCIAL),
            ("whisper", IntentPhase.SOCIAL),
        ],
    )
    def test_explicit_mapping(
        self, tool_name: str, expected: IntentPhase
    ) -> None:
        """既知のツール名は明示マッピングで返る。"""
        assert phase_for_tool(tool_name) == expected

    @pytest.mark.parametrize(
        "tool_name, expected",
        [
            ("combat_attack", IntentPhase.ATTACK),
            ("move_north", IntentPhase.MOVEMENT),
            ("speech_yell", IntentPhase.SOCIAL),
            ("conversation_start", IntentPhase.SOCIAL),
        ],
    )
    def test_prefix_fallback(
        self, tool_name: str, expected: IntentPhase
    ) -> None:
        """明示マッピングが無い場合 prefix で分類される。

        PR-CC (Y_after_pr639_640 後続): ``spot_graph_`` prefix は廃止
        されたので、fallback ケースから ``spot_graph_unknown_tool`` を除外。
        spot_graph 系 tool は全て _EXPLICIT_TOOL_PHASE で個別マップ済み。
        """
        assert phase_for_tool(tool_name) == expected

    def test_unknown_tool_falls_back_to_other(self) -> None:
        """既知の prefix にも該当しないツールは OTHER。"""
        assert phase_for_tool("totally_unknown_tool") == IntentPhase.OTHER

    def test_empty_string_returns_other(self) -> None:
        """空文字は OTHER (validation は別レイヤーで担保)。"""
        assert phase_for_tool("") == IntentPhase.OTHER

    def test_non_str_returns_other(self) -> None:
        """str 以外は OTHER (戻り値を確実に返すことで上位の例外回避)。"""
        assert phase_for_tool(None) == IntentPhase.OTHER  # type: ignore[arg-type]


class TestSpotGraphToolsAreExplicitlyMapped:
    """PR-CC (Y_after_pr639_640 後続、code-review MEDIUM 反映): 旧
    ``spot_graph_`` prefix fallback を撤去したため、spot_graph 系 tool の
    phase 分類はもう ``_EXPLICIT_TOOL_PHASE`` の網羅性に依存する。

    将来新 spot_graph tool を ``get_spot_graph_specs()`` に追加したときに
    ``_EXPLICIT_TOOL_PHASE`` への追記を忘れると、その tool は静かに
    ``IntentPhase.OTHER`` に落ちる。これは CLAUDE.md の「1 箇所だけ足して
    連動を忘れる」silent failure パターンに近いため、構造テストで検出する。
    """

    def test_全ての_spot_graph_tool_が_明示_phase_dict_に登録されている(self) -> None:
        """``get_spot_graph_specs()`` が返す全 tool 名について、
        ``_EXPLICIT_TOOL_PHASE`` dict の key に含まれることを確認。

        ``wait`` のような意図的に OTHER にマップされた tool と、登録漏れで
        default OTHER に落ちた tool を区別するため、値ではなく **key の
        存在** で判定する。
        """
        from ai_rpg_world.application.intent.tool_phase_mapping import (
            _EXPLICIT_TOOL_PHASE,
        )
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            get_spot_graph_specs,
        )

        specs = get_spot_graph_specs()
        missing: list[str] = []
        for defn, _ in specs:
            # SPEECH_DEFINITION は spot_graph specs にも含まれるが tool_name
            # は "speak" で speech_ prefix mapping (PREFIX_PHASE の
            # SPEECH 経由) で SOCIAL に落ちる。個別 dict になくても OK。
            # したがってここでは「dict にあるか、または SOCIAL 相当か」で許容。
            name = defn.name
            if name in _EXPLICIT_TOOL_PHASE:
                continue
            phase = phase_for_tool(name)
            if phase == IntentPhase.OTHER:
                missing.append(name)
        assert not missing, (
            f"以下の spot_graph tool が _EXPLICIT_TOOL_PHASE dict にも "
            f"prefix mapping にも登録されていない (silent OTHER 化): "
            f"{missing}. tool_phase_mapping.py の _EXPLICIT_TOOL_PHASE "
            "dict を更新すること。"
        )
