"""MemoryKind enum の値・列挙挙動。"""

from __future__ import annotations

from ai_rpg_world.domain.being.value_object.memory_kind import MemoryKind


class TestMemoryKindValues:
    """MemoryKind の各メンバーが期待値を持つ。"""

    def test_four(self) -> None:
        """Phase 2 PR3 時点で SHORT_TERM / EPISODIC / SEMANTIC / MEMO の 4 種類。"""
        kinds = {k for k in MemoryKind}
        assert kinds == {
            MemoryKind.SHORT_TERM,
            MemoryKind.EPISODIC,
            MemoryKind.SEMANTIC,
            MemoryKind.MEMO,
        }

    def test_value_snake_case_string(self) -> None:
        """シリアライズ用に各 enum value は snake_case 文字列。"""
        assert MemoryKind.SHORT_TERM.value == "short_term"
        assert MemoryKind.EPISODIC.value == "episodic"
        assert MemoryKind.SEMANTIC.value == "semantic"
        assert MemoryKind.MEMO.value == "memo"

    def test_str(self) -> None:
        """str を継承しているので文字列との比較が可能。"""
        assert MemoryKind.EPISODIC == "episodic"
        assert MemoryKind.MEMO != "other"
