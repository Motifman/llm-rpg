"""アイテム効果の値オブジェクト。

消費可能アイテムが持つ効果の「データ」のみを定義する。
効果の適用（PlayerStatusAggregate への反映）はアプリケーション層の
ConsumableEffectHandler が担当し、ドメイン間の依存を避ける。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ai_rpg_world.domain.item.exception import ItemEffectValidationException


def _validate_non_negative(value: int, name: str) -> None:
    if value < 0:
        raise ItemEffectValidationException(f"{name}: amount must be >= 0, got {value}")


class ItemEffect(ABC):
    """アイテム効果の基底。値オブジェクトとしてデータのみを保持する。"""

    @abstractmethod
    def __repr__(self) -> str:
        ...


@dataclass(frozen=True)
class HealEffect(ItemEffect):
    """HP回復効果のデータ"""

    amount: int

    def __post_init__(self) -> None:
        _validate_non_negative(self.amount, "Heal effect")


@dataclass(frozen=True)
class RecoverMpEffect(ItemEffect):
    """MP回復効果のデータ"""

    amount: int

    def __post_init__(self) -> None:
        _validate_non_negative(self.amount, "Recover MP effect")


@dataclass(frozen=True)
class GoldEffect(ItemEffect):
    """所持金増加効果のデータ。amount はアプリケーション層で earn_gold に渡される。"""

    amount: int

    def __post_init__(self) -> None:
        _validate_non_negative(self.amount, "Gold effect")


@dataclass(frozen=True)
class ExpEffect(ItemEffect):
    """経験値増加効果のデータ"""

    amount: int

    def __post_init__(self) -> None:
        _validate_non_negative(self.amount, "Exp effect")


@dataclass(frozen=True)
class CompositeItemEffect(ItemEffect):
    """複数効果をまとめたデータ"""

    effects: tuple[ItemEffect, ...]

    def __post_init__(self) -> None:
        if self.effects is None:
            raise ItemEffectValidationException(
                "CompositeItemEffect: effects must not be None"
            )
        if not isinstance(self.effects, tuple):
            object.__setattr__(self, "effects", tuple(self.effects))
        for i, sub in enumerate(self.effects):
            if not isinstance(sub, ItemEffect):
                raise ItemEffectValidationException(
                    f"CompositeItemEffect: effects[{i}] must be ItemEffect, got {type(sub).__name__}"
                )
