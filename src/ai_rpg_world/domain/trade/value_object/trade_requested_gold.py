from dataclasses import dataclass

from ai_rpg_world.domain.trade.exception.trade_exception import TradeRequestedGoldValidationException


@dataclass(frozen=True)
class TradeRequestedGold:
    """取引で要求される金額の値オブジェクト

    取引で要求される金額は1以上の値を持ちます。
    """
    value: int

    def __post_init__(self):
        """バリデーションは__post_init__で実行"""
        if self.value <= 0:
            raise TradeRequestedGoldValidationException(f"取引要求金額は1以上の値である必要があります。value: {self.value}")

    @classmethod
    def of(cls, value: int) -> "TradeRequestedGold":
        """TradeRequestedGoldを作成するファクトリメソッド

        Args:
            value: 金額の値（1以上に制限される）

        Returns:
            TradeRequestedGold: TradeRequestedGold値オブジェクト

        Raises:
            TradeRequestedGoldValidationException: バリデーションエラー時
        """
        return cls(value)

    def __str__(self) -> str:
        """文字列としての金額"""
        return f"{self.value} G"

    def __repr__(self) -> str:
        """文字列表現"""
        return f"TradeRequestedGold({self.value})"

    def __eq__(self, other: object) -> bool:
        """等価性比較"""
        if not isinstance(other, TradeRequestedGold):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        """ハッシュ値"""
        return hash(self.value)

    def __int__(self) -> int:
        """intとしての金額"""
        return self.value
