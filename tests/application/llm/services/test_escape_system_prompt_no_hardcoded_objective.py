"""build_escape_system_prompt の system prompt から scenario 固有の hardcoded を撤廃した。

PR-C 背景:
PR-B で objective_text (user prompt の【現在の目的】section) を scenario 駆動に
切り替えた。しかし system prompt 内には別の hardcoded text が残っていた:

1. _DEFAULT_SAFE_INTRO: 「この局面の最優先目標は脱出（または与えられたゴール）に
   到達することである。」 — llm_public_intro が空のときに使われる fallback
2. 行動ルール段: 「最優先の目的は「脱出」である。証拠・記録の収集は脱出と状況判断
   のための手段であり…」 — 全シナリオで使われる固定文

これらは survival_island_v2 のような「脱出ではなく救助」が勝利条件のシナリオで
ノイズになる (LLM の世界モデルが「脱出」に引き寄せられる)。

対処: 両方の hardcoded を「user 文面の【現在の目的】section を参照」というメタ説明
に置き換え。system prompt をシナリオ非依存に保ち、user prompt の objective_text
(PR-B で scenario 駆動化済み) を唯一の真実源にする。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.escape_llm_prompt import (
    _DEFAULT_SAFE_INTRO,
    build_escape_system_prompt,
    safe_world_intro_text,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioMetadata


class TestSystemPromptNoHardcodedEscapeObjective:
    """system prompt と _DEFAULT_SAFE_INTRO から「最優先の目的は脱出」hardcoded を撤廃する。"""

    def test_default_safe_intro_does_not_hardcode_escape(self) -> None:
        """_DEFAULT_SAFE_INTRO に「脱出」hardcoded が残っていない。

        旧文: 「この局面の最優先目標は脱出（または与えられたゴール）に到達することである。」
        survival_island_v2 のように勝利条件が「救助」のシナリオで誤誘導される。
        """
        assert "脱出" not in _DEFAULT_SAFE_INTRO
        # 代わりに「user 文面の【現在の目的】を参照」というメタ説明が入っている
        assert "【現在の目的】" in _DEFAULT_SAFE_INTRO

    def test_system_prompt_does_not_hardcode_escape_as_top_priority(self) -> None:
        """生成された system prompt の【行動ルール】段に「最優先の目的は『脱出』」が無い。"""
        prompt = build_escape_system_prompt(
            world_title="テスト世界",
            persona_block="(空)",
            safe_intro=_DEFAULT_SAFE_INTRO,
            participant_names=(),
        )
        # 「最優先の目的は『脱出』」フレーズが消えていること
        assert "最優先の目的は「脱出」" not in prompt
        # 代わりにシナリオ駆動を促す表現が入っていること
        assert "【現在の目的】" in prompt

    def test_system_prompt_still_emphasizes_grounding_in_observation(self) -> None:
        """旧 hardcoded で語っていた「未発見の真相を断言しない」原則は残っている。

        hardcoded を外しても、grounding に関する規範は別の行で保たれていることを保証する。
        """
        prompt = build_escape_system_prompt(
            world_title="テスト世界",
            persona_block="(空)",
            safe_intro=_DEFAULT_SAFE_INTRO,
            participant_names=(),
        )
        # 既存の行動ルールに「未発見の事実を、すでに知っているかのように断言しない。」が残る
        assert "未発見の事実を" in prompt

    def test_safe_world_intro_text_prefers_scenario_llm_public_intro(self) -> None:
        """シナリオに llm_public_intro があれば fallback を使わない (既存挙動の維持)。"""
        meta = ScenarioMetadata(
            id="t",
            title="t",
            description="",
            theme="",
            difficulty="",
            estimated_ticks=10,
            author="",
            tags=(),
            llm_public_intro="シナリオ固有の世界導入文。",
        )
        assert safe_world_intro_text(meta) == "シナリオ固有の世界導入文。"

    def test_safe_world_intro_text_falls_back_when_empty(self) -> None:
        """llm_public_intro が空のときは _DEFAULT_SAFE_INTRO を使う (シナリオ非依存)。"""
        meta = ScenarioMetadata(
            id="t",
            title="t",
            description="",
            theme="",
            difficulty="",
            estimated_ticks=10,
            author="",
            tags=(),
            llm_public_intro="",
        )
        assert safe_world_intro_text(meta) == _DEFAULT_SAFE_INTRO
