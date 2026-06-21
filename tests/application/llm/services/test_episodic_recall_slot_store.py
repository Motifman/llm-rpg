"""想起スロット (working memory slot) — #526 後続 段階 3。

passive recall を毎 tick 独立に再計算する従来方式から、前 tick の slot 内容を
持ち越す方式へ移行するための store の境界値テスト。

想起の長続き (持ち越し) / 容量上限 N / 滞在期間 L / クールダウン C の 4
パラメータの相互作用を保証する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
    InMemoryEpisodicRecallSlotStore,
    RecallSlotDecision,
    RecallSlotEntry,
    RecallSlotPolicy,
    apply_slot_policy,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId


def _being(value: str = "being_w1_p1") -> BeingId:
    return BeingId(value)


_DEFAULT_POLICY = RecallSlotPolicy(
    capacity=6, insert_per_tick=3, max_residence=5, cooldown_ticks=5
)


class TestRecallSlotPolicyValidation:
    """ポリシーの境界値バリデーション。"""

    def test_負の値はエラーになる(self) -> None:
        """capacity / insert_per_tick / max_residence / cooldown_ticks は 0 以上。"""
        with pytest.raises(ValueError):
            RecallSlotPolicy(
                capacity=-1, insert_per_tick=0, max_residence=0, cooldown_ticks=0
            )

    def test_insert_per_tick_が_capacity_を超えるとエラー(self) -> None:
        """1 tick で容量超の挿入はできないため設定段階で弾く。"""
        with pytest.raises(ValueError):
            RecallSlotPolicy(
                capacity=3, insert_per_tick=4, max_residence=5, cooldown_ticks=5
            )


class TestApplySlotPolicy:
    """``apply_slot_policy`` の主要パスを保証する。"""

    def test_空_slot_から_capacity_と_insert_per_tick_の小さい方まで挿入する(self) -> None:
        """初回 tick はスロット空 → insert_per_tick まで詰める。"""
        decision = apply_slot_policy(
            prev_slot=(),
            candidate_episode_ids_in_score_order=("e1", "e2", "e3", "e4", "e5"),
            cooldown_until={},
            current_tick=0,
            policy=_DEFAULT_POLICY,
        )
        assert [e.episode_id for e in decision.inserted] == ["e1", "e2", "e3"]
        assert [e.episode_id for e in decision.new_slot] == ["e1", "e2", "e3"]
        assert decision.evicted_ids == ()

    def test_前_slot_を持ち越し新規は_K_insert_まで(self) -> None:
        """retained 3 + insert 3 で N=6 を満たす。retained は順序を保つ。"""
        prev = (
            RecallSlotEntry("a", entered_tick=0),
            RecallSlotEntry("b", entered_tick=0),
            RecallSlotEntry("c", entered_tick=0),
        )
        decision = apply_slot_policy(
            prev_slot=prev,
            candidate_episode_ids_in_score_order=("x", "y", "z", "w"),
            cooldown_until={},
            current_tick=1,
            policy=_DEFAULT_POLICY,
        )
        assert [e.episode_id for e in decision.retained] == ["a", "b", "c"]
        assert [e.episode_id for e in decision.inserted] == ["x", "y", "z"]
        assert [e.episode_id for e in decision.new_slot] == [
            "a", "b", "c", "x", "y", "z",
        ]

    def test_max_residence_を超えた_entry_は強制退去する(self) -> None:
        """L=5 で entered_tick=0 の entry は current_tick=5 以降で退去。"""
        prev = (
            RecallSlotEntry("old", entered_tick=0),
            RecallSlotEntry("recent", entered_tick=3),
        )
        decision = apply_slot_policy(
            prev_slot=prev,
            candidate_episode_ids_in_score_order=("new",),
            cooldown_until={},
            current_tick=5,
            policy=_DEFAULT_POLICY,
        )
        assert decision.evicted_ids == ("old",)
        assert [e.episode_id for e in decision.retained] == ["recent"]
        assert [e.episode_id for e in decision.inserted] == ["new"]

    def test_cooldown_中の_episode_は候補から外れる(self) -> None:
        """退去後 C tick の間は再入を許さない (= 慣化の構造的な実装)。"""
        decision = apply_slot_policy(
            prev_slot=(),
            candidate_episode_ids_in_score_order=("e1", "e2"),
            cooldown_until={"e1": 10},  # current_tick=5 では e1 はまだ復帰不可
            current_tick=5,
            policy=_DEFAULT_POLICY,
        )
        assert [e.episode_id for e in decision.inserted] == ["e2"]

    def test_cooldown_満了直後は再入可能(self) -> None:
        """current_tick が cooldown_until に達したら復帰できる (境界値)。"""
        decision = apply_slot_policy(
            prev_slot=(),
            candidate_episode_ids_in_score_order=("e1",),
            cooldown_until={"e1": 10},
            current_tick=10,
            policy=_DEFAULT_POLICY,
        )
        assert [e.episode_id for e in decision.inserted] == ["e1"]

    def test_retained_に既にいる_episode_は候補から除外される(self) -> None:
        """slot 内の重複挿入を防ぐ。"""
        prev = (RecallSlotEntry("a", entered_tick=0),)
        decision = apply_slot_policy(
            prev_slot=prev,
            candidate_episode_ids_in_score_order=("a", "b"),
            cooldown_until={},
            current_tick=1,
            policy=_DEFAULT_POLICY,
        )
        assert [e.episode_id for e in decision.inserted] == ["b"]

    def test_新規候補が高_score_でも既存は押し出さない(self) -> None:
        """N に達していて空き枠無ければ insert 0 件。prefix cache 重視の設計。"""
        prev = tuple(
            RecallSlotEntry(f"e{i}", entered_tick=0) for i in range(6)
        )
        decision = apply_slot_policy(
            prev_slot=prev,
            candidate_episode_ids_in_score_order=("hot",),
            cooldown_until={},
            current_tick=1,
            policy=_DEFAULT_POLICY,
        )
        assert decision.inserted == ()
        assert [e.episode_id for e in decision.new_slot] == [
            f"e{i}" for i in range(6)
        ]


class TestInMemoryEpisodicRecallSlotStore:
    """sidecar store の永続性と cooldown 反映を保証する。"""

    def test_未記録の_being_は空_slot_と空_cooldown_を返す(self) -> None:
        """初期状態の getter は空を返し、書込みなしで例外も出さない。"""
        store = InMemoryEpisodicRecallSlotStore()
        assert store.get_slot(_being()) == ()
        assert dict(store.get_cooldown_until(_being())) == {}

    def test_apply_decision_で_slot_が更新され_evicted_は_cooldown_に積まれる(self) -> None:
        """退去 episode は current_tick + cooldown_ticks まで除外される。"""
        store = InMemoryEpisodicRecallSlotStore()
        being = _being()
        decision = RecallSlotDecision(
            retained=(),
            inserted=(RecallSlotEntry("e1", entered_tick=10),),
            evicted_ids=("old",),
            new_slot=(RecallSlotEntry("e1", entered_tick=10),),
        )
        store.apply_decision(being, decision, current_tick=10, cooldown_ticks=5)
        assert [e.episode_id for e in store.get_slot(being)] == ["e1"]
        assert dict(store.get_cooldown_until(being)) == {"old": 15}

    def test_being_間は隔離される(self) -> None:
        """1P と 2P で slot / cooldown が混ざらないこと。"""
        store = InMemoryEpisodicRecallSlotStore()
        being_a = BeingId("being_w1_p1")
        being_b = BeingId("being_w1_p2")
        decision = RecallSlotDecision(
            retained=(),
            inserted=(RecallSlotEntry("e1", entered_tick=0),),
            evicted_ids=(),
            new_slot=(RecallSlotEntry("e1", entered_tick=0),),
        )
        store.apply_decision(being_a, decision, current_tick=0, cooldown_ticks=5)
        assert store.get_slot(being_a) != ()
        assert store.get_slot(being_b) == ()
