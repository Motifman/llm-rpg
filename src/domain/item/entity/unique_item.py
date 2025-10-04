from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.domain.item.item import Item


@dataclass(frozen=True)
class UniqueItem(Item):
    """ユニークIDで識別されるアイテム（エンティティ）の基底クラス"""
    unique_id: int = 0
    
    def __post_init__(self):
        super().__post_init__()
        if self.unique_id < 0:
            raise ValueError(f"unique_id must be >= 0. unique_id: {self.unique_id}")

    def __eq__(self, other):
        if not isinstance(other, UniqueItem):
            return NotImplemented
        return self.unique_id == other.unique_id

    def __hash__(self):
        return hash(self.unique_id)




