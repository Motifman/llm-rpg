from dataclasses import dataclass
from typing import List, Tuple

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


@dataclass(frozen=True)
class QuestReward:
    """クエスト報酬の値オブジェクト

    ゴールド、経験値、アイテム（ItemSpecId, quantity）のリスト。
    プレイヤー発行分は Phase 2 で発行時に予約する。
    """
    gold: int
    exp: int
    item_rewards: Tuple[Tuple[ItemSpecId, int], ...]  # (item_spec_id, quantity)

    def __post_init__(self):
        if self.gold < 0:
            raise ValueError("gold must be non-negative")
        if self.exp < 0:
            raise ValueError("exp must be non-negative")
        for item_spec_id, qty in self.item_rewards:
            if qty <= 0:
                raise ValueError("item quantity must be positive")

    @classmethod
    def of(
        cls,
        gold: int = 0,
        exp: int = 0,
        item_rewards: List[Tuple[ItemSpecId, int]] = None,
    ) -> "QuestReward":
        """報酬を作成"""
        if item_rewards is None:
            item_rewards = []
        return cls(
            gold=gold,
            exp=exp,
            item_rewards=tuple(item_rewards),
        )
