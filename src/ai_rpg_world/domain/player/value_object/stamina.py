from dataclasses import dataclass
from ai_rpg_world.domain.player.exception import StaminaValidationException


@dataclass(frozen=True)
class Stamina:
    """スタミナ値オブジェクト

    スタミナは0以上max_stamina以下の値を持ちます。
    max_staminaは0以上の値である必要があります。
    """
    value: int
    max_stamina: int

    def __post_init__(self):
        """バリデーションは__post_init__で実行"""
        if self.max_stamina < 0:
            raise StaminaValidationException(f"max_staminaは0以上の値である必要があります。max_stamina: {self.max_stamina}")
        if self.value > self.max_stamina:
            raise StaminaValidationException(f"スタミナはmax_stamina以下の値である必要があります。value: {self.value}, max_stamina: {self.max_stamina}")
        if self.value < 0:
            raise StaminaValidationException(f"スタミナは0以上の値である必要があります。value: {self.value}")

    @classmethod
    def create(cls, value: int, max_stamina: int) -> "Stamina":
        """スタミナを作成するファクトリメソッド

        Args:
            value: スタミナの値（0以上max_stamina以下に制限される）
            max_stamina: 最大スタミナ

        Returns:
            Stamina: スタミナ値オブジェクト

        Raises:
            StaminaValidationException: バリデーションエラー時
        """
        # 値を適切な範囲に制限
        actual_value = max(0, min(value, max_stamina))
        return cls(actual_value, max_stamina)

    def consume(self, amount: int) -> "Stamina":
        """スタミナを消費する

        Args:
            amount: 消費量

        Returns:
            Stamina: 消費後のスタミナ

        Raises:
            StaminaValidationException: 消費量が負の値の場合
        """
        if amount < 0:
            raise StaminaValidationException(f"消費量は0以上の値である必要があります。amount: {amount}")
        return Stamina.create(self.value - amount, self.max_stamina)

    def recover(self, amount: int) -> "Stamina":
        """スタミナを回復する

        Args:
            amount: 回復量

        Returns:
            Stamina: 回復後のスタミナ

        Raises:
            StaminaValidationException: 回復量が負の値の場合
        """
        if amount < 0:
            raise StaminaValidationException(f"回復量は0以上の値である必要があります。amount: {amount}")
        return Stamina.create(self.value + amount, self.max_stamina)

    def can_consume(self, amount: int) -> bool:
        """指定された量のスタミナを消費可能かどうか

        Args:
            amount: 消費量

        Returns:
            bool: 消費可能かどうか

        Raises:
            StaminaValidationException: 消費量が負の値の場合
        """
        if amount < 0:
            raise StaminaValidationException(f"消費量は0以上の値である必要があります。amount: {amount}")
        return self.value >= amount

    def is_empty(self) -> bool:
        """スタミナが空（0）かどうか

        Returns:
            bool: スタミナが空の場合True
        """
        return self.value <= 0

    def is_full(self) -> bool:
        """スタミナが最大値かどうか

        Returns:
            bool: スタミナが最大値の場合True
        """
        return self.value == self.max_stamina

    def get_percentage(self) -> float:
        """スタミナの割合を取得（0.0〜1.0）

        Returns:
            float: スタミナの割合
        """
        if self.max_stamina == 0:
            return 0.0
        return self.value / self.max_stamina

    def __str__(self) -> str:
        """文字列としてのスタミナ"""
        return f"{self.value}/{self.max_stamina}"

    def __eq__(self, other: object) -> bool:
        """等価性比較"""
        if not isinstance(other, Stamina):
            return NotImplemented
        return self.value == other.value and self.max_stamina == other.max_stamina

    def __hash__(self) -> int:
        """ハッシュ値"""
        return hash((self.value, self.max_stamina))
