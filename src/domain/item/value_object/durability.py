from dataclasses import dataclass
from src.domain.item.exception import DurabilityValidationException


@dataclass(frozen=True)
class Durability:
    """耐久度を表す値オブジェクト"""
    max_value: int
    current: int

    def __post_init__(self):
        """バリデーションは__post_init__で実行"""
        if self.max_value <= 0:
            raise DurabilityValidationException(
                current=self.current,
                max_value=self.max_value,
                reason="max_value must be positive"
            )
        if self.current < 0:
            raise DurabilityValidationException(
                current=self.current,
                max_value=self.max_value,
                reason="current must be >= 0"
            )
        if self.current > self.max_value:
            raise DurabilityValidationException(
                current=self.current,
                max_value=self.max_value,
                reason="current must be <= max_value"
            )

    def use(self, amount: int = 1) -> tuple["Durability", bool]:
        """耐久度を使用する（新しいインスタンスを返す）

        Args:
            amount: 使用する量（デフォルト1）

        Returns:
            tuple: (新しいDurabilityインスタンス, 使用に成功したかどうか)
        """
        if self.current > 0:
            new_current = max(0, self.current - amount)
            return Durability(self.max_value, new_current), True
        return self, False

    @property
    def is_broken(self) -> bool:
        """耐久度が0かどうか"""
        return self.current == 0

    def repair(self, amount: int = 1) -> "Durability":
        """耐久度を回復する（新しいインスタンスを返す）

        Args:
            amount: 回復する量（デフォルト1）

        Returns:
            Durability: 回復された新しいDurabilityインスタンス
        """
        new_current = min(self.max_value, self.current + amount)
        return Durability(self.max_value, new_current)