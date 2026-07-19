"""慣化ペナルティ (#526 後続) — 段階 2。

人間の habituation を模す: 直近で recall された episode は、しばらくの間
score を下げる。これにより「同じ場所にいる間に毎ターン同じ episode が
出続ける」状態を抑える。

設計判断:
- sidecar store (``InMemoryEpisodicRecallHabituationStore``) に
  ``last_recalled_tick`` を持つ (episode 本体は触らない / 永続化しない)
- penalty 関数は純関数で境界値テスト可能
- decay_window 経過後は penalty=0 (= 再度引かれる)
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.episodic_recall_habituation_store import (
    InMemoryEpisodicRecallHabituationStore,
    compute_habituation_penalty,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId


class TestComputeHabituationPenalty:
    """``compute_habituation_penalty`` の境界値挙動。"""

    def test_last_tick_unspecified_penalty_zero(self) -> None:
        """そのエピソードを過去に recall していない = penalty なし。"""
        assert compute_habituation_penalty(
            last_recalled_tick=None, current_tick=10, decay_window=5
        ) == 0

    def test_before_tick_recall_penalty_decay_window_equals(self) -> None:
        """0 tick 経過 (= 同 tick / 直前) は最大ペナルティ。"""
        assert compute_habituation_penalty(
            last_recalled_tick=10, current_tick=10, decay_window=5
        ) == 5

    def test_decay_window_equals_age_penalty_zero(self) -> None:
        """decay_window と age が等しいときは penalty が 0 まで減衰。"""
        assert compute_habituation_penalty(
            last_recalled_tick=5, current_tick=10, decay_window=5
        ) == 0

    def test_decay_window_over_age_penalty_zero(self) -> None:
        """十分に時間が経過したら慣化が解け、penalty は出ない。"""
        assert compute_habituation_penalty(
            last_recalled_tick=1, current_tick=100, decay_window=5
        ) == 0

    def test_age(self) -> None:
        """1 tick 経過 → penalty=4, 2 tick → 3, ... という線形減衰。"""
        assert compute_habituation_penalty(
            last_recalled_tick=9, current_tick=10, decay_window=5
        ) == 4
        assert compute_habituation_penalty(
            last_recalled_tick=8, current_tick=10, decay_window=5
        ) == 3
        assert compute_habituation_penalty(
            last_recalled_tick=6, current_tick=10, decay_window=5
        ) == 1

    def test_last_tick_value_penalty_zero(self) -> None:
        """clock skew や test fixture の不整合で last > current のときは
        penalty を出さずに 0 に倒す (silent failure 構造的対処)。"""
        assert compute_habituation_penalty(
            last_recalled_tick=20, current_tick=10, decay_window=5
        ) == 0

    def test_decay_window_zero_penalty_zero(self) -> None:
        """機能を実質的に off にするための境界。"""
        assert compute_habituation_penalty(
            last_recalled_tick=10, current_tick=10, decay_window=0
        ) == 0

    def test_decay_window_negative_raises_exception(self) -> None:
        """誤設定は早めに弾く (configuration validation)。"""
        with pytest.raises(ValueError):
            compute_habituation_penalty(
                last_recalled_tick=10, current_tick=10, decay_window=-1
            )


class TestInMemoryEpisodicRecallHabituationStore:
    """sidecar store の roundtrip と分離。"""

    def test_episode_get_none(self) -> None:
        """未 recall = None を返す (= sentinel として 0 と区別する)。"""
        store = InMemoryEpisodicRecallHabituationStore()
        bid = BeingId("being_w1_p1")
        assert store.get_last_recalled_tick(bid, "ep-1") is None

    def test_record_recall_after_get_can_lookup(self) -> None:
        """書き込んだ tick がそのまま読める。"""
        store = InMemoryEpisodicRecallHabituationStore()
        bid = BeingId("being_w1_p1")
        store.record_recall(bid, ["ep-1", "ep-2"], tick=5)
        assert store.get_last_recalled_tick(bid, "ep-1") == 5
        assert store.get_last_recalled_tick(bid, "ep-2") == 5

    def test_different_being_recall_independent(self) -> None:
        """being が違えば last_recalled_tick も独立 (= 二人プレイで干渉しない)。"""
        store = InMemoryEpisodicRecallHabituationStore()
        b1 = BeingId("being_w1_p1")
        b2 = BeingId("being_w1_p2")
        store.record_recall(b1, ["ep-shared"], tick=3)
        assert store.get_last_recalled_tick(b1, "ep-shared") == 3
        assert store.get_last_recalled_tick(b2, "ep-shared") is None

    def test_same_episode_multiple_tick_record_remains(self) -> None:
        """直近の recall が慣化の起点になるので最新値を保持。"""
        store = InMemoryEpisodicRecallHabituationStore()
        bid = BeingId("being_w1_p1")
        store.record_recall(bid, ["ep-1"], tick=3)
        store.record_recall(bid, ["ep-1"], tick=7)
        assert store.get_last_recalled_tick(bid, "ep-1") == 7

    def test_empty_episode_ids_record_raises_exception(self) -> None:
        """空リスト recall (= 候補 0 件の tick) は no-op。"""
        store = InMemoryEpisodicRecallHabituationStore()
        bid = BeingId("being_w1_p1")
        store.record_recall(bid, [], tick=5)
        assert store.get_last_recalled_tick(bid, "ep-1") is None

    def test_being_id_being_id_raises_type_error(self) -> None:
        """境界での型ガード。"""
        store = InMemoryEpisodicRecallHabituationStore()
        with pytest.raises(TypeError):
            store.record_recall("not-a-being-id", ["ep-1"], tick=5)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            store.get_last_recalled_tick("not-a-being-id", "ep-1")  # type: ignore[arg-type]

    def test_tick_negative_raises_value_error(self) -> None:
        """tick は非負整数。"""
        store = InMemoryEpisodicRecallHabituationStore()
        bid = BeingId("being_w1_p1")
        with pytest.raises(ValueError):
            store.record_recall(bid, ["ep-1"], tick=-1)
