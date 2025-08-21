from dataclasses import dataclass
from typing import TYPE_CHECKING
from src.domain.item.item_effect import ItemEffect
from src.domain.item.item import Item

if TYPE_CHECKING:
    from src.domain.player.player import Player


@dataclass(frozen=True)
class ConsumableItem(Item):
    """消費可能なアイテム"""
    effect: ItemEffect = None

    def use(self, player: 'Player'): # 引数をGameContextに変更
        """アイテムを使用し、効果を適用する"""
        self.effect.apply(player)