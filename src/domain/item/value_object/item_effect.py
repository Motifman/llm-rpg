from abc import ABC, abstractmethod
from typing import List, TYPE_CHECKING, Union
from src.domain.common.value_object import Exp, Gold

if TYPE_CHECKING:
    from src.domain.player.player import Player


class ItemEffect(ABC):
    """アイテムの効果"""
    @abstractmethod
    def apply(self, player: 'Player'):
        pass


class HealEffect(ItemEffect):
    """回復効果"""
    def __init__(self, amount: int):
        if amount < 0:
            raise ValueError(f"Amount must be >= 0. amount: {amount}")
        self.amount = amount

    def apply(self, player: 'Player'):
        player.heal(self.amount)


class RecoverMpEffect(ItemEffect):
    """MP回復効果"""
    def __init__(self, amount: int):
        if amount < 0:
            raise ValueError(f"Amount must be >= 0. amount: {amount}")
        self.amount = amount

    def apply(self, player: 'Player'):
        player.recover_mp(self.amount)


class GoldEffect(ItemEffect):
    """所持金増加効果"""
    def __init__(self, amount: int):
        if amount < 0:
            raise ValueError(f"Amount must be >= 0. amount: {amount}")
        self.gold = Gold(amount)

    def apply(self, player: 'Player'):
        player.receive_gold(self.gold)


class ExpEffect(ItemEffect):
    """経験値増加効果"""
    def __init__(self, amount: int):
        if amount < 0:
            raise ValueError(f"Amount must be >= 0. amount: {amount}")
        self.amount = amount

    def apply(self, player: 'Player'):
        # プレイヤーの現在のmax_expを使用してExpオブジェクトを作成
        exp = Exp(self.amount, player._dynamic_status._exp.max_exp)
        player.receive_exp(exp)


class CompositeItemEffect(ItemEffect):
    """複合効果"""
    def __init__(self, effects: List[ItemEffect]):
        self.effects = effects

    def apply(self, player: 'Player'):
        for effect in self.effects:
            effect.apply(player)

