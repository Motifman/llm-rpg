from dataclasses import dataclass
from typing import Union
from src.domain.player.exception import BaseStatusValidationException


@dataclass(frozen=True)
class BaseStatus:
    """基礎ステータス値オブジェクト

    プレイヤーの基本的な戦闘能力を表します。
    すべての値は非負の値である必要があります。
    critical_rateとevasion_rateは0.0〜1.0の範囲である必要があります。
    """
    attack: int
    defense: int
    speed: int
    critical_rate: float
    evasion_rate: float

    def __post_init__(self):
        """バリデーションは__post_init__で実行"""
        if self.attack < 0:
            raise BaseStatusValidationException(f"attackは0以上の値である必要があります。attack: {self.attack}")
        if self.defense < 0:
            raise BaseStatusValidationException(f"defenseは0以上の値である必要があります。defense: {self.defense}")
        if self.speed < 0:
            raise BaseStatusValidationException(f"speedは0以上の値である必要があります。speed: {self.speed}")
        if not (0.0 <= self.critical_rate <= 1.0):
            raise BaseStatusValidationException(f"critical_rateは0.0〜1.0の範囲である必要があります。critical_rate: {self.critical_rate}")
        if not (0.0 <= self.evasion_rate <= 1.0):
            raise BaseStatusValidationException(f"evasion_rateは0.0〜1.0の範囲である必要があります。evasion_rate: {self.evasion_rate}")

    @classmethod
    def create(
        cls,
        attack: int,
        defense: int,
        speed: int,
        critical_rate: float,
        evasion_rate: float
    ) -> "BaseStatus":
        """基礎ステータスを作成するファクトリメソッド

        Args:
            attack: 攻撃力
            defense: 防御力
            speed: 速度
            critical_rate: クリティカル率（0.0〜1.0）
            evasion_rate: 回避率（0.0〜1.0）

        Returns:
            BaseStatus: 基礎ステータス値オブジェクト

        Raises:
            BaseStatusValidationException: バリデーションエラー時
        """
        return cls(attack, defense, speed, critical_rate, evasion_rate)

    def __add__(self, other: 'BaseStatus') -> 'BaseStatus':
        """ステータスの加算

        Args:
            other: 加算するステータス

        Returns:
            BaseStatus: 加算結果のステータス

        Raises:
            TypeError: otherがBaseStatusでない場合
        """
        if not isinstance(other, BaseStatus):
            raise TypeError(f"BaseStatus同士の加算のみ可能です。other: {type(other)}")
        return BaseStatus(
            attack=self.attack + other.attack,
            defense=self.defense + other.defense,
            speed=self.speed + other.speed,
            critical_rate=round(min(1.0, self.critical_rate + other.critical_rate), 10),  # 最大1.0に制限、丸め
            evasion_rate=round(min(1.0, self.evasion_rate + other.evasion_rate), 10),  # 最大1.0に制限、丸め
        )

    def __sub__(self, other: 'BaseStatus') -> 'BaseStatus':
        """ステータスの減算

        Args:
            other: 減算するステータス

        Returns:
            BaseStatus: 減算結果のステータス

        Raises:
            TypeError: otherがBaseStatusでない場合
        """
        if not isinstance(other, BaseStatus):
            raise TypeError(f"BaseStatus同士の減算のみ可能です。other: {type(other)}")
        return BaseStatus(
            attack=max(0, self.attack - other.attack),  # 最小0に制限
            defense=max(0, self.defense - other.defense),  # 最小0に制限
            speed=max(0, self.speed - other.speed),  # 最小0に制限
            critical_rate=round(max(0.0, self.critical_rate - other.critical_rate), 10),  # 最小0.0に制限、丸め
            evasion_rate=round(max(0.0, self.evasion_rate - other.evasion_rate), 10),  # 最小0.0に制限、丸め
        )

    def get_total_points(self) -> int:
        """ステータスの合計ポイントを取得

        Returns:
            int: 攻撃力 + 防御力 + 速度の合計
        """
        return self.attack + self.defense + self.speed

    def __str__(self) -> str:
        """文字列としての基礎ステータス"""
        return f"ATK:{self.attack} DEF:{self.defense} SPD:{self.speed} CRT:{self.critical_rate:.2f} EVA:{self.evasion_rate:.2f}"

    def __eq__(self, other: object) -> bool:
        """等価性比較"""
        if not isinstance(other, BaseStatus):
            return NotImplemented
        return (
            self.attack == other.attack
            and self.defense == other.defense
            and self.speed == other.speed
            and abs(self.critical_rate - other.critical_rate) < 1e-10  # 浮動小数点の比較
            and abs(self.evasion_rate - other.evasion_rate) < 1e-10  # 浮動小数点の比較
        )

    def __hash__(self) -> int:
        """ハッシュ値"""
        # 浮動小数点を適切にハッシュ化するために丸める
        return hash((
            self.attack,
            self.defense,
            self.speed,
            round(self.critical_rate, 10),
            round(self.evasion_rate, 10),
        ))


# 空のステータス定数
EMPTY_STATUS = BaseStatus(0, 0, 0, 0.0, 0.0)