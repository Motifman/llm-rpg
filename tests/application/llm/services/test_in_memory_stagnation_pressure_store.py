"""InMemoryStagnationPressureStore (停滞感 store P-U2) の挙動を検証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.in_memory_stagnation_pressure_store import (
    InMemoryStagnationPressureStore,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

_BEING_A = BeingId("being-a")
_BEING_B = BeingId("being-b")


class TestGetByBeing:
    """未記録時の初期値と、記録済み値の読み出しを保証する。"""

    def test_unrecorded_being_returns_zero(self) -> None:
        """一度も increment/replace されていない being は 0 を返す。"""
        store = InMemoryStagnationPressureStore()
        assert store.get_by_being(_BEING_A) == 0

    def test_get_by_being_rejects_non_being_id(self) -> None:
        """being_id が BeingId でなければ TypeError を投げる。"""
        store = InMemoryStagnationPressureStore()
        with pytest.raises(TypeError):
            store.get_by_being("being-a")  # type: ignore[arg-type]


class TestIncrementByBeing:
    """increment_by_being がカウンタを 1 ずつ増やし、増加後の値を返すことを保証する。"""

    def test_increment_from_zero_returns_one(self) -> None:
        """初回 increment は 0 → 1 になり、1 を返す。"""
        store = InMemoryStagnationPressureStore()
        assert store.increment_by_being(_BEING_A) == 1
        assert store.get_by_being(_BEING_A) == 1

    def test_repeated_increment_accumulates(self) -> None:
        """3 回連続 increment すると 3 になる。"""
        store = InMemoryStagnationPressureStore()
        for _ in range(3):
            store.increment_by_being(_BEING_A)
        assert store.get_by_being(_BEING_A) == 3

    def test_increment_is_isolated_per_being(self) -> None:
        """being ごとにカウンタが独立している (二者間で干渉しない)。"""
        store = InMemoryStagnationPressureStore()
        store.increment_by_being(_BEING_A)
        store.increment_by_being(_BEING_A)
        store.increment_by_being(_BEING_B)
        assert store.get_by_being(_BEING_A) == 2
        assert store.get_by_being(_BEING_B) == 1


class TestResetByBeing:
    """reset_by_being がカウンタを 0 に戻すことを保証する。"""

    def test_reset_after_increments_returns_to_zero(self) -> None:
        """increment を重ねた後に reset すると 0 に戻る。"""
        store = InMemoryStagnationPressureStore()
        store.increment_by_being(_BEING_A)
        store.increment_by_being(_BEING_A)
        store.reset_by_being(_BEING_A)
        assert store.get_by_being(_BEING_A) == 0

    def test_reset_on_untouched_being_is_noop_safe(self) -> None:
        """一度も increment していない being への reset は 0 のまま安全。"""
        store = InMemoryStagnationPressureStore()
        store.reset_by_being(_BEING_A)
        assert store.get_by_being(_BEING_A) == 0


class TestReplaceAllByBeing:
    """snapshot restore 用の bulk overwrite を保証する。"""

    def test_replace_with_positive_value_overwrites_counter(self) -> None:
        """正の値で replace すると、その値がそのままカウンタになる。"""
        store = InMemoryStagnationPressureStore()
        store.increment_by_being(_BEING_A)
        store.replace_all_by_being(_BEING_A, 5)
        assert store.get_by_being(_BEING_A) == 5

    def test_replace_with_zero_clears_being_state(self) -> None:
        """0 で replace すると being_id の内部 state が完全に削除される
        (capture 時の空状態と bit identity を保つ)。"""
        store = InMemoryStagnationPressureStore()
        store.increment_by_being(_BEING_A)
        store.replace_all_by_being(_BEING_A, 0)
        assert _BEING_A not in store._counts
        assert store.get_by_being(_BEING_A) == 0

    def test_replace_with_negative_value_raises_value_error(self) -> None:
        """負の値での replace は不変条件違反として ValueError を投げる。"""
        store = InMemoryStagnationPressureStore()
        with pytest.raises(ValueError):
            store.replace_all_by_being(_BEING_A, -1)
