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
class DamageHpEffect(ItemEffect):
    """HP 減少効果のデータ。毒キノコ・腐った食料など、食べると害になるアイテム用。

    HealEffect の対称。``amount`` は正の整数で「減らす量」を表す。
    実際の適用は ConsumableEffectHandler が ``player_status.apply_damage(amount)``
    を呼んで行う。
    """

    amount: int

    def __post_init__(self) -> None:
        _validate_non_negative(self.amount, "Damage HP effect")


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
class SatisfyNeedEffect(ItemEffect):
    """欲求回復効果のデータ。need_type_name は NeedType の値文字列（"HUNGER" / "FATIGUE"）。"""

    need_type_name: str
    amount: int

    def __post_init__(self) -> None:
        _validate_non_negative(self.amount, "Satisfy need effect")
        if not self.need_type_name:
            raise ItemEffectValidationException(
                "SatisfyNeedEffect: need_type_name must not be empty"
            )


@dataclass(frozen=True)
class ReviveEffect(ItemEffect):
    """ダウンしたプレイヤーを蘇生させる効果 (Issue #621 Phase 3a)。

    ``hp_rate`` は復帰時の HP 比率 (0.0 〜 1.0)、``max_hp * hp_rate`` で
    HP が復帰し ``is_down`` が解除される。実際の蘇生処理は
    ``ConsumableEffectHandler`` が ``player.revive(hp_rate)`` を呼んで行う。

    domain 上は ``hp_rate=0.0`` も許容する (= 「意識は戻ったが HP は戻らない」
    のような演出余地)。ダウンしていない player への適用は handler 側で
    no-op として扱う (= 既に元気なのに「revive される」ことはあり得るが
    害は無い)。
    """

    hp_rate: float

    def __post_init__(self) -> None:
        if self.hp_rate < 0.0 or self.hp_rate > 1.0:
            raise ItemEffectValidationException(
                f"Revive effect: hp_rate must be in [0.0, 1.0], got {self.hp_rate}"
            )


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
