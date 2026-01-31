from __future__ import annotations

from dataclasses import dataclass
from ai_rpg_world.domain.player.exception.player_exceptions import PlayerInventorySlotIdValidationException


@dataclass(frozen=True)
class SlotId:
    """インベントリスロットID値オブジェクト

    インベントリのスロットを識別するための値オブジェクト。
    0以上の整数値のみを許可する。
    """
    value: int

    def __post_init__(self):
        """バリデーション"""
        if not isinstance(self.value, int):
            raise PlayerInventorySlotIdValidationException(
                f"SlotId must be an integer, got {type(self.value)}: {self.value}"
            )
        if self.value < 0:
            raise PlayerInventorySlotIdValidationException(
                f"SlotId must be >= 0, got {self.value}"
            )

    @classmethod
    def create(cls, value: int) -> "SlotId":
        """ファクトリメソッド"""
        return cls(value)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SlotId):
            return NotImplemented
        return self.value == other.value

    def __lt__(self, other: "SlotId") -> bool:
        return self.value < other.value

    def __hash__(self) -> int:
        return hash(self.value)
