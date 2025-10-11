from dataclasses import dataclass

from src.domain.player.exception.player_exceptions import GoldValidationException


@dataclass(frozen=True)
class Gold:
    """ゴールド値オブジェクト

    ゴールドは0以上の値を持ちます。
    """
    value: int

    def __post_init__(self):
        """バリデーションは__post_init__で実行"""
        if self.value < 0:
            raise GoldValidationException(f"Goldは0以上の値である必要があります。value: {self.value}")

    @classmethod
    def create(cls, value: int) -> "Gold":
        """Goldを作成するファクトリメソッド

        Args:
            value: Goldの値（0以上に制限される）

        Returns:
            Gold: Gold値オブジェクト

        Raises:
            GoldValidationException: バリデーションエラー時
        """
        # 値を適切な範囲に制限
        actual_value = max(0, value)
        return cls(actual_value)

    def add(self, amount: int) -> "Gold":
        """Goldを追加する

        Args:
            amount: 追加量

        Returns:
            Gold: 追加後のGold

        Raises:
            GoldValidationException: 追加量が負の値の場合
        """
        if amount < 0:
            raise GoldValidationException(f"追加量は0以上の値である必要があります。amount: {amount}")
        return Gold.create(self.value + amount)

    def subtract(self, amount: int) -> "Gold":
        """Goldを減算する

        Args:
            amount: 減算量

        Returns:
            Gold: 減算後のGold

        Raises:
            GoldValidationException: 減算量が負の値の場合
        """
        if amount < 0:
            raise GoldValidationException(f"減算量は0以上の値である必要があります。amount: {amount}")
        return Gold.create(self.value - amount)

    def can_subtract(self, amount: int) -> bool:
        """指定された量のGoldを減算可能かどうか

        Args:
            amount: 減算量

        Returns:
            bool: 減算可能かどうか

        Raises:
            GoldValidationException: 減算量が負の値の場合
        """
        if amount < 0:
            raise GoldValidationException(f"減算量は0以上の値である必要があります。amount: {amount}")
        return self.value >= amount

    def __str__(self) -> str:
        """文字列としてのGold"""
        return f"{self.value} G"

    def __eq__(self, other: object) -> bool:
        """等価性比較"""
        if not isinstance(other, Gold):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        """ハッシュ値"""
        return hash(self.value)
