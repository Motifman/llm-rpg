"""``tool_phase_mapping.phase_for_tool`` の対応表テスト。"""

import pytest

from ai_rpg_world.application.intent.tool_phase_mapping import phase_for_tool
from ai_rpg_world.domain.intent.value_object.intent_phase import IntentPhase


class TestPhaseForTool:
    """``phase_for_tool`` の解釈挙動。"""

    @pytest.mark.parametrize(
        "tool_name, expected",
        [
            ("spot_graph_travel_to", IntentPhase.MOVEMENT),
            ("spot_graph_interact", IntentPhase.INTERACTION),
            ("spot_graph_explore", IntentPhase.INTERACTION),
            ("spot_graph_set_sub_location", IntentPhase.MOVEMENT),
            ("spot_graph_wait", IntentPhase.OTHER),
            ("spot_graph_listen", IntentPhase.INTERACTION),
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
            ("spot_graph_unknown_tool", IntentPhase.INTERACTION),
        ],
    )
    def test_prefix_fallback(
        self, tool_name: str, expected: IntentPhase
    ) -> None:
        """明示マッピングが無い場合 prefix で分類される。"""
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
