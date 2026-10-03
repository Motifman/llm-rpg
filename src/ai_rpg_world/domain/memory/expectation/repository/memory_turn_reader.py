"""記憶のターン数を読むだけの口。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.domain.being.value_object.being_id import BeingId


class MemoryTurnReader(ABC):
    """Being の記憶のターン数を読む。

    進めるのは予期の保存先だけにする。証拠や信念に観測のターン数を付ける側は
    読むだけで、時計を進めない。
    """

    @abstractmethod
    def current_turn(self, being_id: BeingId) -> int:
        """記憶のターン数。まだ手を受け取っていなければ 0。"""


__all__ = ["MemoryTurnReader"]
