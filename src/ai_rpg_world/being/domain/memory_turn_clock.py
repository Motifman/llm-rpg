"""Being の記憶のターン数。世界の tick ではなく本人の歩みで進み、環境を跨いでも続く。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.being.domain.being_id import BeingId


class MemoryTurnInvalid(ValueError):
    """記憶のターン数が 0 以上の int でない。"""


def require_memory_turn(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise MemoryTurnInvalid(f"turn must be int >= 0 (got {value!r})")
    return value


class MemoryTurnReader(ABC):
    """Being の記憶のターン数を読む。

    進めるのは 1 手を受け取る側だけにする。記憶にターン数を付ける側は読むだけで、
    時計を進めない。
    """

    @abstractmethod
    def current_turn(self, being_id: BeingId) -> int:
        """記憶のターン数。まだ手を受け取っていなければ 0。"""


class MemoryTurnClock(MemoryTurnReader):
    """Being ごとの記憶のターン数を持ち、進める。"""

    @abstractmethod
    def advance_turn(self, being_id: BeingId) -> int:
        """エージェントの 1 手を受け取ったときに呼び、ターン数を 1 進めて、進めたあとの値を返す。"""

    @abstractmethod
    def replace_all_by_being(self, being_id: BeingId, *, turn: int) -> None:
        """snapshot の復元用に、ターン数を置き換える (design_decisions 27)。

        0 以上の int でなければ、何も変えずに ``MemoryTurnInvalid`` を投げる。
        """


__all__ = [
    "MemoryTurnClock",
    "MemoryTurnInvalid",
    "MemoryTurnReader",
    "require_memory_turn",
]
