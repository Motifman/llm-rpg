from dataclasses import dataclass
from typing import Union
from ai_rpg_world.domain.player.exception import HpValidationException


@dataclass(frozen=True)
class Hp:
    """HP（ヒットポイント）値オブジェクト

    HPは0以上max_hp以下の値を持ちます。
    max_hpは0以上の値である必要があります。
    """
    value: int
    max_hp: int

    def __post_init__(self):
        """バリデーションは__post_init__で実行"""
        if self.max_hp < 0:
            raise HpValidationException(f"max_hpは0以上の値である必要があります。max_hp: {self.max_hp}")
        if self.value > self.max_hp:
            raise HpValidationException(f"HPはmax_hp以下の値である必要があります。value: {self.value}, max_hp: {self.max_hp}")
        if self.value < 0:
            raise HpValidationException(f"HPは0以上の値である必要があります。value: {self.value}")

    @classmethod
    def create(cls, value: int, max_hp: int) -> "Hp":
        """HPを作成するファクトリメソッド

        Args:
            value: HPの値（0以上max_hp以下に制限される）
            max_hp: 最大HP

        Returns:
            Hp: HP値オブジェクト

        Raises:
            HpValidationException: バリデーションエラー時
        """
        # 値を適切な範囲に制限
        actual_value = max(0, min(value, max_hp))
        return cls(actual_value, max_hp)

    def heal(self, amount: int) -> "Hp":
        """HPを回復する

        Args:
            amount: 回復量

        Returns:
            Hp: 回復後のHP

        Raises:
            HpValidationException: 回復量が負の値の場合
        """
        if amount < 0:
            raise HpValidationException(f"回復量は0以上の値である必要があります。amount: {amount}")
        return Hp.create(self.value + amount, self.max_hp)

    def damage(self, amount: int) -> "Hp":
        """HPにダメージを与える

        Args:
            amount: ダメージ量

        Returns:
            Hp: ダメージ後のHP

        Raises:
            HpValidationException: ダメージ量が負の値の場合
        """
        if amount < 0:
            raise HpValidationException(f"ダメージ量は0以上の値である必要があります。amount: {amount}")
        return Hp.create(self.value - amount, self.max_hp)

    def can_consume(self, amount: int) -> bool:
        """指定された量のHPを消費可能かどうか

        Args:
            amount: 消費量

        Returns:
            bool: 消費可能かどうか

        Raises:
            HpValidationException: 消費量が負の値の場合
        """
        if amount < 0:
            raise HpValidationException(f"消費量は0以上の値である必要があります。amount: {amount}")
        return self.value >= amount

    def is_alive(self) -> bool:
        """生存しているかどうか（HPが1以上かどうか）

        Returns:
            bool: 生存している場合True
        """
        return self.value > 0

    def is_full(self) -> bool:
        """HPが最大値かどうか

        Returns:
            bool: HPが最大値の場合True
        """
        return self.value == self.max_hp

    def get_percentage(self) -> float:
        """HPの割合を取得（0.0〜1.0）

        Returns:
            float: HPの割合
        """
        if self.max_hp == 0:
            return 0.0
        return self.value / self.max_hp

    def __str__(self) -> str:
        """文字列としてのHP"""
        return f"{self.value}/{self.max_hp}"

    def __eq__(self, other: object) -> bool:
        """等価性比較"""
        if not isinstance(other, Hp):
            return NotImplemented
        return self.value == other.value and self.max_hp == other.max_hp

    def __hash__(self) -> int:
        """ハッシュ値"""
        return hash((self.value, self.max_hp))