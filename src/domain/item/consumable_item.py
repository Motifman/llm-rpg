from dataclasses import dataclass
from src.domain.player.player import Player
from src.domain.item.item_effect import ItemEffect
from src.domain.item.stackable_item import StackableItem


@dataclass
class ConsumableItem(StackableItem):
    """消費可能なアイテム"""
    effect: ItemEffect

    def use(self, player: Player): # 引数をGameContextに変更
        """アイテムを使用し、効果を適用する"""
        if self.quantity > 0:
            self.effect.apply(player)
        else:
            raise ValueError(f"Quantity must be > 0. quantity: {self.quantity}")