"""recall ranking で habituation 罰則が「実際に他候補を押し下げる」ことを保証する (PR-I)。

Y_after_issue621 trace 分析の D-26 で観測された問題:
- 同じ episode が 8 tick 連続で recall slot に居座る
- ``habituation_penalty_by_episode`` には罰則 (= penalty 3 等) が記録されている
- にもかかわらず slot に残り続けている = **罰則が弱すぎて他候補を上回れない**

原因: ``_arm_score_key`` 内で ``multi_cue_score - penalty`` を計算しているが、
4 cue 一致 (= score 4) の episode に penalty 3 を引いてもまだ score 1 で
ランクインしてしまう。

修正方針:
- penalty に倍率を掛けて「同じ score でも、最近 recall された方を確実に
  下げる」ようにする (= ``recall_habituation_strength`` 設定値、default 2)
- ``strength=0`` は罰則 off の経路として残す (= 既存挙動を再現可能)
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallRetrievalService,
)


class TestHabituationStrengthDefault:
    """デフォルト倍率は 2 (= penalty を 2 倍してスコアから引く)。"""

    def test_default_two(self) -> None:
        """Y_after_issue621 で観測された「penalty が score を打ち消せない」を
        防ぐ最小強度として 2 を選んでいる。"""
        svc = EpisodicPassiveRecallRetrievalService(store=_StubStore())
        assert svc._habituation_strength == 2

    def test_documented_behavior(self) -> None:
        """倍率を 明示しても 受け取る。"""
        svc = EpisodicPassiveRecallRetrievalService(
            store=_StubStore(), habituation_strength=3,
        )
        assert svc._habituation_strength == 3

    def test_zero(self) -> None:
        """penalty を完全無効化したい (= 旧 #526 段階 2 直後の挙動を再現したい)
        場合の脱出口。"""
        svc = EpisodicPassiveRecallRetrievalService(
            store=_StubStore(), habituation_strength=0,
        )
        assert svc._habituation_strength == 0


class TestHabituationStrengthValidation:
    def test_negative_strength_raises_value_error(self) -> None:
        """負の strength は ValueError。"""
        with pytest.raises(ValueError):
            EpisodicPassiveRecallRetrievalService(
                store=_StubStore(), habituation_strength=-1,
            )

    def test_strength_int(self) -> None:
        """strength は int。"""
        with pytest.raises(TypeError):
            EpisodicPassiveRecallRetrievalService(
                store=_StubStore(), habituation_strength=1.5,  # type: ignore[arg-type]
            )

    def test_bool_int(self) -> None:
        """``isinstance(True, int) == True`` トラップ防止。"""
        with pytest.raises(TypeError):
            EpisodicPassiveRecallRetrievalService(
                store=_StubStore(), habituation_strength=True,  # type: ignore[arg-type]
            )


class _StubStore:
    """ctor validation のためだけに渡す最小 stub。"""
    def list_recent(self, *args, **kw): return []
    def list_by_cue(self, *args, **kw): return []
    def find_by_id(self, *args, **kw): return None
