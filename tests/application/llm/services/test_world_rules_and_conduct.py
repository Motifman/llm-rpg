"""システムプロンプトが Being の作法と環境の案内を分けて持ち、目的を案内の後ろに置くことを保証する (design_decisions D1630-4)。"""

from __future__ import annotations

import re

import pytest

from ai_rpg_world.application.llm.services.world_llm_prompt import (
    build_world_system_prompt,
    world_conduct_text,
    world_rules,
)

_HEADING_LINE = re.compile(r"^【([^】]+)】$", re.MULTILINE)

#: 環境が決めることの目印。作法の文にあってはいけない。
_ENVIRONMENT_RULE_MARKS = ("ラベル", "say_inline", "勝利条件", "行動の制限", "拒否される")


class TestConductHoldsNoEnvironmentRules:
    """作法の文が、どの環境でも同じ作法だけを持つことを保証する。"""

    @pytest.mark.parametrize("mark", _ENVIRONMENT_RULE_MARKS)
    def test_conduct_does_not_mention_an_environment_rule(self, mark: str) -> None:
        """作法の文には、ラベルの使い方・一言・勝利条件・行動の制限・断られる行動を書かない。"""
        assert mark not in world_conduct_text(episode_index_shown=True, episode_recall_offered=True)

    def test_conduct_sections_are_the_four_manners(self) -> None:
        """作法は【渡される文面の読み方】【行動のしかた】【心がけ】【メモの書き方】の順に並ぶ。"""
        assert _HEADING_LINE.findall(world_conduct_text()) == [
            "渡される文面の読み方",
            "行動のしかた",
            "心がけ",
            "メモの書き方",
        ]


class TestWorldRules:
    """【この世界の決まり】が、環境の決まりを持つことを保証する。"""

    def test_rules_hold_labels_rejection_say_inline_and_goal(self) -> None:
        """勝敗のある世界の決まりは、ラベル、断られる行動、一言、勝利条件の順に 4 行で、【現在の目的】を指す。"""
        rules = world_rules(has_goal=True)

        lines = rules.text.split("\n")
        assert rules.heading == "この世界の決まり"
        starts = (
            "- ラベル（",
            "- 行動は条件を満たさないと拒否される",
            "- `say_inline` を持つツール",
            "- **このシナリオの勝利条件",
        )
        assert len(lines) == len(starts)
        assert all(line.startswith(start) for line, start in zip(lines, starts)), lines
        assert "【現在地と周囲】などに表示されたもの" in lines[0]
        assert "【現在の目的】に記される" in lines[3]

    def test_rules_without_goal_do_not_speak_of_victory(self) -> None:
        """勝敗のない世界の決まりは、勝利条件を書かず、【現在の目的】があれば参照してよいと書く。"""
        text = world_rules(has_goal=False).text

        assert "勝利条件" not in text
        assert "【現在の目的】があれば参照してよい" in text

    def test_action_limit_is_the_last_rule_only_when_given(self) -> None:
        """行動の制限の文を渡すと最後の行になり、渡さなければ行が無い。"""
        assert world_rules(action_limit_text="限りがある").text.split("\n")[-1] == "- 行動の制限: 限りがある"
        assert "行動の制限" not in world_rules().text


class TestSystemPromptOrder:
    """システムプロンプトの並びを保証する。"""

    def test_opening_conduct_orientation_rules_then_goal(self) -> None:
        """冒頭の一文、作法の 4 節、世界の前提、この世界の決まり、人柄、現在の目的の順に並ぶ。"""
        prompt = build_world_system_prompt(
            world_title="町",
            persona_block="【ペルソナ】焼き手。",
            safe_intro="市場のある町。",
            imposed_goal="店を開く。",
        )

        assert prompt.startswith(
            "あなたは【ペルソナ】に書かれた人物として行動するキャラクターである。\n\n【渡される文面の読み方】\n"
        )
        assert _HEADING_LINE.findall(prompt) == [
            "渡される文面の読み方",
            "行動のしかた",
            "心がけ",
            "メモの書き方",
            "世界の前提",
            "この世界の決まり",
            "ペルソナ",
            "現在の目的",
        ]
        assert prompt.endswith("\n\n【現在の目的】\n店を開く。")

    def test_no_goal_section_without_an_imposed_goal(self) -> None:
        """課された目的が無ければ、【現在の目的】の節を出さず、人柄で終わる。"""
        prompt = build_world_system_prompt(world_title="町", persona_block="p", safe_intro="i")

        assert _HEADING_LINE.findall(prompt)[-1] == "ペルソナ"
