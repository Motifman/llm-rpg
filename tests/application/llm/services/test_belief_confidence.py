"""compute_belief_confidence の単体テスト (U3b)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.belief_confidence import (
    BASE_CONFIDENCE,
    compute_belief_confidence,
)


class TestComputeBeliefConfidence:
    """支持件数・反証件数から belief の confidence を再計算するルール関数。"""

    def test_zero_support_and_contradict_returns_base_confidence(self) -> None:
        """支持 0 件・反証 0 件のとき、confidence は BASE_CONFIDENCE と一致する。"""
        assert compute_belief_confidence(0, 0) == BASE_CONFIDENCE

    def test_support_increases_confidence(self) -> None:
        """支持件数が増えるほど confidence は単調に上がる。"""
        low = compute_belief_confidence(1, 0)
        high = compute_belief_confidence(3, 0)
        assert low < high

    def test_contradict_decreases_confidence(self) -> None:
        """反証件数が増えるほど confidence は単調に下がる。"""
        low = compute_belief_confidence(3, 0)
        high_contradict = compute_belief_confidence(3, 2)
        assert high_contradict < low

    def test_result_is_clamped_to_unit_interval(self) -> None:
        """支持・反証が極端でも confidence は [0, 1] に収まる。"""
        assert compute_belief_confidence(100, 0) == 1.0
        assert compute_belief_confidence(0, 100) == 0.0

    def test_negative_support_count_raises_value_error(self) -> None:
        """support_count に負数を渡すと ValueError になる (不正な呼び出しを検出する)。"""
        with pytest.raises(ValueError):
            compute_belief_confidence(-1, 0)

    def test_negative_contradict_count_raises_value_error(self) -> None:
        """contradict_count に負数を渡すと ValueError になる。"""
        with pytest.raises(ValueError):
            compute_belief_confidence(0, -1)


class TestConfirmationSupportWeight:
    """P3b: CONFIRMATION 由来の支持を通常支持の半分 (0.5) に軽く数える。"""

    def test_default_zero_is_backward_compatible(self) -> None:
        """confirmation_support_count 未指定なら導入前と完全一致。"""
        assert compute_belief_confidence(4, 1, 0) == compute_belief_confidence(4, 1)

    def test_confirmation_support_counts_half(self) -> None:
        """全支持が CONFIRMATION なら実効支持は半分 (支持4→実効2)。"""
        all_confirmation = compute_belief_confidence(4, 0, 4)
        half_support = compute_belief_confidence(2, 0, 0)
        assert all_confirmation == pytest.approx(half_support)
        # 通常支持4件より確実に低い。
        assert all_confirmation < compute_belief_confidence(4, 0, 0)

    def test_partial_confirmation(self) -> None:
        """支持4のうち2件が CONFIRMATION → 実効3件 (2*1.0 + 2*0.5)。"""
        partial = compute_belief_confidence(4, 0, 2)
        assert partial == pytest.approx(compute_belief_confidence(3, 0, 0))

    def test_confirmation_exceeding_support_raises(self) -> None:
        with pytest.raises(ValueError):
            compute_belief_confidence(2, 0, 3)

    def test_negative_confirmation_raises(self) -> None:
        with pytest.raises(ValueError):
            compute_belief_confidence(3, 0, -1)


class TestHearsaySupportWeight:
    """P10: HEARSAY (伝聞) 由来の支持を通常支持の半分 (0.5) に軽く数える。"""

    def test_default_zero_is_backward_compatible(self) -> None:
        """hearsay_support_count 未指定なら導入前と完全一致 (既定 0)。"""
        assert compute_belief_confidence(4, 1) == compute_belief_confidence(
            4, 1, 0, 0
        )

    def test_hearsay_support_counts_half(self) -> None:
        """全支持が HEARSAY なら実効支持は半分 (支持4→実効2)。"""
        all_hearsay = compute_belief_confidence(4, 0, 0, 4)
        half_support = compute_belief_confidence(2, 0, 0, 0)
        assert all_hearsay == pytest.approx(half_support)
        # 通常支持4件 (直接体験) より確実に低い — 伝聞だけで生まれた belief の
        # confidence は同数の直接体験由来より低いこと (設計メモ §4)。
        assert all_hearsay < compute_belief_confidence(4, 0, 0, 0)

    def test_hearsay_and_confirmation_are_disjoint_subsets(self) -> None:
        """CONFIRMATION と HEARSAY はどちらも支持の内数で、両方 0.5 掛けされる。

        支持4のうち CONFIRMATION 1件・HEARSAY 1件 → 実効 2*1.0 + 2*0.5 = 3件。
        """
        both = compute_belief_confidence(4, 0, 1, 1)
        assert both == pytest.approx(compute_belief_confidence(3, 0, 0, 0))

    def test_hearsay_exceeding_support_raises(self) -> None:
        with pytest.raises(ValueError):
            compute_belief_confidence(2, 0, 0, 3)

    def test_confirmation_plus_hearsay_exceeding_support_raises(self) -> None:
        """CONFIRMATION と HEARSAY の合計が支持を超えたら ValueError (内数の整合)。"""
        with pytest.raises(ValueError):
            compute_belief_confidence(3, 0, 2, 2)

    def test_negative_hearsay_raises(self) -> None:
        with pytest.raises(ValueError):
            compute_belief_confidence(3, 0, 0, -1)
