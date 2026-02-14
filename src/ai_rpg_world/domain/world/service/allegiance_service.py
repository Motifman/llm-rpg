"""
味方関係を判定するドメインサービス。
同一パック・同一勢力等のルールで「味方」を定義する。
"""

from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.value_object.pack_id import PackId


class AllegianceService(ABC):
    """味方関係を判定するサービスのインターフェース"""

    @abstractmethod
    def is_ally(self, actor_comp, target_comp) -> bool:
        """actor_comp が target_comp を味方とみなすか"""
        pass


class PackAllegianceService(AllegianceService):
    """
    同一 PackId を持つアクターを味方とする実装。
    pack_id が None の場合は味方なし（常に False）。
    """
    def is_ally(self, actor_comp, target_comp) -> bool:
        actor_pack = actor_comp.pack_id
        target_pack = target_comp.pack_id
        if actor_pack is None or target_pack is None:
            return False
        return actor_pack == target_pack
