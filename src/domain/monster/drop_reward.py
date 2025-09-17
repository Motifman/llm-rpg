from dataclasses import dataclass, field
from typing import List
from src.domain.item.item_quantity import ItemQuantity
from src.domain.common.value_object import Exp, Gold


@dataclass(frozen=True)
class DropReward:
    gold: Gold = Gold(0)
    exp: Exp = Exp(0)
    items: List[ItemQuantity] = field(default_factory=list)
    information: List[str] = field(default_factory=list)
    
    def __add__(self, other: 'DropReward') -> 'DropReward':
        return DropReward(
            gold=self.gold + other.gold,
            exp=self.exp + other.exp,
            items=self.items + other.items,
            information=self.information + other.information
        )

    def split(self, ratio: List[float]) -> List['DropReward']:
        """
        報酬を指定された比率で複数のDropRewardに分配する
        
        Args:
            ratio: 分配比率のリスト（合計が1.0になる必要がある）
            
        Returns:
            分配されたDropRewardのリスト
            
        Raises:
            ValueError: 比率の合計が1.0でない場合、または負の値が含まれる場合
        """
        if not ratio or len(ratio) == 0:
            raise ValueError("Ratio list cannot be empty")
        
        if any(r < 0 for r in ratio):
            raise ValueError("All ratios must be non-negative")
        
        total_ratio = sum(ratio)
        if abs(total_ratio - 1.0) > 1e-6:  # 浮動小数点の誤差を考慮
            raise ValueError(f"Ratio sum must be 1.0, got {total_ratio}")
        
        result = []
        
        for i, r in enumerate(ratio):
            # ゴールドの分配（小数点以下切り捨て）
            split_gold = Gold(int(self.gold.value * r))
            
            # 経験値の分配（小数点以下切り捨て）
            split_exp = Exp(int(self.exp.value * r))
            
            # アイテムの分配
            split_items = []
            for item_quantity in self.items:
                split_quantity = int(item_quantity.quantity * r)
                if split_quantity > 0:
                    split_items.append(ItemQuantity(item_quantity.item, split_quantity))
            # 情報の分配（最後の要素に残りを全て割り当て）
            if i == len(ratio) - 1:
                split_information = self.information.copy()
            else:
                split_count = int(len(self.information) * r)
                split_information = self.information[:split_count]
            
            result.append(DropReward(
                gold=split_gold,
                exp=split_exp,
                items=split_items,
                information=split_information
            ))
        
        return result


EMPTY_REWARD = DropReward()