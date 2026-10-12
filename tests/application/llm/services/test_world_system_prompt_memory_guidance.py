"""システムプロンプトの記憶の指示が、出ている欄と手段だけを指すことを保証する (#1616)。

記憶の部品を止めた run (`var/runs/mine_v1_007_memo`) で、本文が【関連する記憶】と
「能動想起の手段を試す」を指示し続け、エージェントが無い欄と無いツールを探した。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.world_llm_prompt import (
    build_world_system_prompt,
)

_RULE_WITH_BOTH = (
    "具体的な過去の出来事 (どこで何をした等) は【関連する記憶】または能動想起で"
    "取り出した内容だけが「確かな記憶」である。【関連する記憶】が空のときは、"
    "ペルソナから想像で補わず、能動想起の手段を試すか、「思い出せない」と素直に伝える。"
)
_LIMIT_WITH_BOTH = (
    "【関連する記憶】も同様で、自動的に思い出せた分のみが載る "
    "(= 空でも「過去そのものが無い」とは限らない)。"
    "空のときに過去を語る必要があれば、能動想起の手段で取り出してから語ること。"
)


def _build(*, relevant_memories_shown: bool, active_recall_offered: bool) -> str:
    return build_world_system_prompt(
        world_title="テスト世界",
        persona_block="【ペルソナ】名前: エイダ",
        safe_intro="周囲を観察しながら暮らす世界。",
        relevant_memories_shown=relevant_memories_shown,
        active_recall_offered=active_recall_offered,
    )


class TestMemoryGuidanceNamesOnlyWhatIsOffered:
    """記憶の指示が、【関連する記憶】と能動想起のそれぞれの有無に合わせて書き分けられる。"""

    def test_both_offered_keeps_the_previous_wording(self) -> None:
        """【関連する記憶】と能動想起の両方があるとき、これまでの 2 文がそのまま出る。"""
        prompt = _build(relevant_memories_shown=True, active_recall_offered=True)

        assert _RULE_WITH_BOTH in prompt
        assert _LIMIT_WITH_BOTH in prompt

    def test_without_active_recall_the_prompt_never_mentions_it(self) -> None:
        """能動想起のツールが無いとき、本文に「能動想起」が出ず、【関連する記憶】は指す。"""
        prompt = _build(relevant_memories_shown=True, active_recall_offered=False)

        assert "能動想起" not in prompt
        assert "【関連する記憶】" in prompt

    def test_without_relevant_memories_the_prompt_never_names_the_section(self) -> None:
        """【関連する記憶】が出ない設定では、本文がその欄の名前を出さず、能動想起は指す。"""
        prompt = _build(relevant_memories_shown=False, active_recall_offered=True)

        assert "関連する記憶" not in prompt
        assert "能動想起" in prompt

    def test_without_either_the_prompt_names_neither(self) -> None:
        """どちらも無いとき、本文は【関連する記憶】も能動想起も出さない。"""
        prompt = _build(relevant_memories_shown=False, active_recall_offered=False)

        assert "関連する記憶" not in prompt
        assert "能動想起" not in prompt

    @pytest.mark.parametrize(
        ("relevant_memories_shown", "active_recall_offered"),
        [(True, False), (False, True), (False, False)],
    )
    def test_the_persona_is_never_a_source_of_past_events(
        self, relevant_memories_shown: bool, active_recall_offered: bool
    ) -> None:
        """記憶の部品をどれだけ止めても、過去の出来事をペルソナから想像で補わない指示と「思い出せない」と伝えてよい指示は残る。"""
        prompt = _build(
            relevant_memories_shown=relevant_memories_shown,
            active_recall_offered=active_recall_offered,
        )

        assert "ペルソナから想像で補わず" in prompt
        assert "「思い出せない」と素直に伝える" in prompt
