from dataclasses import dataclass
from src.domain.player.exception import MpValidationException


@dataclass(frozen=True)
class Mp:
    """MP（マジックポイント）値オブジェクト

    MPは0以上max_mp以下の値を持ちます。
    max_mpは0以上の値である必要があります。
    """
    value: int
    max_mp: int

    def __post_init__(self):
        """バリデーションは__post_init__で実行"""
        if self.max_mp < 0:
            raise MpValidationException(f"max_mpは0以上の値である必要があります。max_mp: {self.max_mp}")
        if self.value > self.max_mp:
            raise MpValidationException(f"MPはmax_mp以下の値である必要があります。value: {self.value}, max_mp: {self.max_mp}")
        if self.value < 0:
            raise MpValidationException(f"MPは0以上の値である必要があります。value: {self.value}")

    @classmethod
    def create(cls, value: int, max_mp: int) -> "Mp":
        """MPを作成するファクトリメソッド

        Args:
            value: MPの値（0以上max_mp以下に制限される）
            max_mp: 最大MP

        Returns:
            Mp: MP値オブジェクト

        Raises:
            MpValidationException: バリデーションエラー時
        """
        # 値を適切な範囲に制限
        actual_value = max(0, min(value, max_mp))
        return cls(actual_value, max_mp)

    def heal(self, amount: int) -> "Mp":
        """MPを回復する

        Args:
            amount: 回復量

        Returns:
            Mp: 回復後のMP

        Raises:
            MpValidationException: 回復量が負の値の場合
        """
        if amount < 0:
            raise MpValidationException(f"回復量は0以上の値である必要があります。amount: {amount}")
        return Mp.create(self.value + amount, self.max_mp)

    def consume(self, amount: int) -> "Mp":
        """MPを消費する

        Args:
            amount: 消費量

        Returns:
            Mp: 消費後のMP

        Raises:
            MpValidationException: 消費量が負の値の場合
        """
        if amount < 0:
            raise MpValidationException(f"消費量は0以上の値である必要があります。amount: {amount}")
        return Mp.create(self.value - amount, self.max_mp)

    def can_consume(self, amount: int) -> bool:
        """指定された量のMPを消費可能かどうか

        Args:
            amount: 消費量

        Returns:
            bool: 消費可能かどうか

        Raises:
            MpValidationException: 消費量が負の値の場合
        """
        if amount < 0:
            raise MpValidationException(f"消費量は0以上の値である必要があります。amount: {amount}")
        return self.value >= amount

    def is_empty(self) -> bool:
        """MPが空（0）かどうか

        Returns:
            bool: MPが空の場合True
        """
        return self.value <= 0

    def is_full(self) -> bool:
        """MPが最大値かどうか

        Returns:
            bool: MPが最大値の場合True
        """
        return self.value == self.max_mp

    def get_percentage(self) -> float:
        """MPの割合を取得（0.0〜1.0）

        Returns:
            float: MPの割合
        """
        if self.max_mp == 0:
            return 0.0
        return self.value / self.max_mp

    def __str__(self) -> str:
        """文字列としてのMP"""
        return f"{self.value}/{self.max_mp}"

    def __eq__(self, other: object) -> bool:
        """等価性比較"""
        if not isinstance(other, Mp):
            return NotImplemented
        return self.value == other.value and self.max_mp == other.max_mp

    def __hash__(self) -> int:
        """ハッシュ値"""
        return hash((self.value, self.max_mp))