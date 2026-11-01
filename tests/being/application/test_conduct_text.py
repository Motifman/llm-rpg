"""Being の作法の文が、環境が出している Being の道具だけを書くことを保証する (design_decisions D1630-6)。"""

from __future__ import annotations

import re

import pytest

from ai_rpg_world.being.application.conduct_text import conduct_text
from ai_rpg_world.being.contract import ContractViolation, OfferedBeingTools

_HEADING_LINE = re.compile(r"^【([^】]+)】$", re.MULTILINE)
_ALL_TOOLS = OfferedBeingTools(
    inner_thought="inner_thought", memo="memo", episode_recall="episode_recall", episode_index_shown=True
)

#: 環境が決めることの目印。作法の文にあってはいけない。
_ENVIRONMENT_RULE_MARKS = ("ラベル", "say_inline", "勝利条件", "行動の制限", "拒否される")


class TestConductHoldsNoEnvironmentRules:
    """作法の文が、どの環境でも同じ作法だけを持つことを保証する。"""

    @pytest.mark.parametrize("mark", _ENVIRONMENT_RULE_MARKS)
    def test_conduct_does_not_mention_an_environment_rule(self, mark: str) -> None:
        """道具を全部出しても、作法の文にはラベルの使い方・一言・勝利条件・行動の制限・断られる行動を書かない。"""
        assert mark not in conduct_text(_ALL_TOOLS)

    def test_conduct_sections_are_the_four_manners(self) -> None:
        """道具を全部出すと、作法は【渡される文面の読み方】【行動のしかた】【心がけ】【メモの書き方】の順に並ぶ。"""
        assert _HEADING_LINE.findall(conduct_text(_ALL_TOOLS)) == [
            "渡される文面の読み方",
            "行動のしかた",
            "心がけ",
            "メモの書き方",
        ]


class TestConductFollowsTheOfferedTools:
    """出していない道具を作法の文が指さないことを保証する。"""

    def test_inner_thought_line_only_when_offered(self) -> None:
        """独白の引数を出さないと【行動のしかた】は tool call の 1 行だけになり、出すとその名前で独白の書き方が続く。"""
        without = conduct_text(OfferedBeingTools())
        with_it = conduct_text(OfferedBeingTools(inner_thought="monologue"))

        assert "独白" not in without
        assert "- `monologue` を持つツールでは、必ず `monologue` を含め、" in with_it

    def test_memo_section_only_when_offered(self) -> None:
        """メモの引数を出さないと【メモの書き方】の節が無く、出すとその名前を指す。"""
        assert "【メモの書き方】" not in conduct_text(OfferedBeingTools())
        assert "- 行動の tool の `note` に、あとで使いたいことを書ける。" in conduct_text(
            OfferedBeingTools(memo="note")
        )

    def test_episode_index_line_only_when_shown(self) -> None:
        """目次を出さないと思い出す道具があっても目次の行を書かず、出すと目次の読み方を書く。"""
        hidden = conduct_text(OfferedBeingTools(episode_recall="episode_recall"))
        shown = conduct_text(OfferedBeingTools(episode_index_shown=True))

        assert "【思い出せる出来事】" not in hidden
        assert "episode_recall" not in hidden
        assert "- 【思い出せる出来事】は、自分が昔の出来事を書き残した記憶の目次である。目次の一行だけから" in shown

    def test_recall_sentence_only_when_the_recall_tool_is_offered(self) -> None:
        """目次を出し、思い出す道具も出すと、その名前で本文の読み方を書く。"""
        shown = conduct_text(OfferedBeingTools(episode_recall="recall_episode", episode_index_shown=True))

        assert "本文は `recall_episode` で呼び名を指定して思い出したときだけ読める。" in shown


class TestOfferedBeingTools:
    """環境が渡す道具の一覧の形を確かめることを保証する。"""

    def test_blank_name_is_rejected(self) -> None:
        """道具の名前に空白だけの文字列を渡すと ContractViolation を投げる。"""
        with pytest.raises(ContractViolation):
            OfferedBeingTools(memo="  ")

    def test_non_bool_index_flag_is_rejected(self) -> None:
        """目次を出すかに bool でない値を渡すと ContractViolation を投げる。"""
        with pytest.raises(ContractViolation):
            OfferedBeingTools(episode_index_shown=1)  # type: ignore[arg-type]
