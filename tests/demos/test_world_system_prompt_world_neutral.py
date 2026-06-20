"""層2 (#526 / U5): escape system prompt の goal/escape 前提を has_goal で中立化する。

勝敗条件のあるシナリオ (has_goal=True) は従来どおりの文面で prompt 不変。勝敗のない
永続世界 (has_goal=False) では「脱出できない」「勝利条件 (最終目的)」等の escape/goal
前提を中立文に置き換える (= 永続世界に escape 前提が漏れない)。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.world_llm_prompt import (
    build_world_system_prompt,
    limited_action_and_time_pressure_text,
)


def _build(*, has_goal: bool) -> str:
    return build_world_system_prompt(
        world_title="テスト世界",
        persona_block="【ペルソナ】テスト",
        safe_intro="導入文",
        participant_names=(),
        has_goal=has_goal,
    )


class TestTimePressureText:
    """行動量の圧テキストの goal 依存。"""

    def test_has_goal_true_keeps_escape_wording(self) -> None:
        """has_goal=True (既定) は従来どおり「脱出できない」を含む。"""
        text = limited_action_and_time_pressure_text()
        assert text == limited_action_and_time_pressure_text(has_goal=True)
        assert "脱出できない" in text

    def test_has_goal_false_drops_escape_wording(self) -> None:
        """has_goal=False は「脱出できない」を落とし、行動量に限りがある事実は残す。"""
        text = limited_action_and_time_pressure_text(has_goal=False)
        assert "脱出できない" not in text
        assert "総量には限りがある" in text
        assert "残り行動量" in text


class TestBuildWorldSystemPromptGoalFraming:
    """build_world_system_prompt の goal/escape 前提が has_goal で切り替わる。"""

    def test_has_goal_true_contains_goal_and_escape_framing(self) -> None:
        """has_goal=True: 勝利条件 (最終目的) 行と「脱出できない」を含む (従来挙動)。"""
        prompt = _build(has_goal=True)
        assert "勝利条件 (最終目的)" in prompt
        assert "全て最終目的のための手段である" in prompt
        assert "脱出できない" in prompt

    def test_has_goal_false_neutralizes_goal_and_escape_framing(self) -> None:
        """has_goal=False: 勝敗・最終目的・脱出の前提が消え、中立文になる。"""
        prompt = _build(has_goal=False)
        assert "勝利条件 (最終目的)" not in prompt
        assert "全て最終目的のための手段である" not in prompt
        assert "脱出できない" not in prompt
        # 中立文: 勝敗を否定し、現在の目的があれば参照する旨
        assert "固定された勝敗や達成すべき最終目的はない" in prompt
        assert "【現在の目的】" in prompt

    def test_default_is_has_goal_true(self) -> None:
        """has_goal 未指定なら True 扱い (既存呼び出し・テストの prompt 不変)。"""
        assert _build(has_goal=True) == build_world_system_prompt(
            world_title="テスト世界",
            persona_block="【ペルソナ】テスト",
            safe_intro="導入文",
            participant_names=(),
        )
