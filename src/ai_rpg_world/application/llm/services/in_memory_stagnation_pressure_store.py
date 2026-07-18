"""InMemoryStagnationPressureStore — StagnationPressureRepository の in-memory 実装 (P-U2)。

experiment run の単位で破棄される sidecar。being 同士は外側の dict で分離する
(GoalJournalRepository の in-memory 実装と同型)。
"""

from __future__ import annotations

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.goal.repository.stagnation_pressure_repository import (
    StagnationPressureRepository,
)


class InMemoryStagnationPressureStore(StagnationPressureRepository):
    """being ごとに停滞感カウンタ (int) を保持する。"""

    def __init__(self) -> None:
        self._counts: dict[BeingId, int] = {}

    def get_by_being(self, being_id: BeingId) -> int:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        return self._counts.get(being_id, 0)

    def increment_by_being(self, being_id: BeingId) -> int:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        new_value = self._counts.get(being_id, 0) + 1
        self._counts[being_id] = new_value
        return new_value

    def reset_by_being(self, being_id: BeingId) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        self._counts[being_id] = 0

    def replace_all_by_being(self, being_id: BeingId, value: int) -> None:
        """snapshot 復元用の bulk overwrite。0 なら being_id の state を完全に
        削除する (= capture 時の空状態と bit identity を保つ、他 store と同じ作法)。"""
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError("value must be int")
        if value < 0:
            raise ValueError("value must be 0 or greater")
        if value:
            self._counts[being_id] = value
        else:
            self._counts.pop(being_id, None)


__all__ = ["InMemoryStagnationPressureStore"]
