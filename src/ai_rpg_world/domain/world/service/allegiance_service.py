"""
味方関係を判定するドメインサービス。
同一パック・同一勢力等のルールで「味方」を定義する。
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.entity.world_object_component import (
        ActorComponent,
        WorldObjectComponent,
    )
    from ai_rpg_world.domain.world.value_object.pack_id import PackId


class AllegianceService(ABC):
    """味方関係を判定するサービスのインターフェース"""

    @abstractmethod
    def is_ally(self, actor_comp: "WorldObjectComponent | None", target_comp: "WorldObjectComponent | None") -> bool:
        """actor_comp が target_comp を味方とみなすか"""
        pass


class PackAllegianceService(AllegianceService):
    """
    同一 PackId を持つアクターを味方とする実装。
    pack_id が None の場合は味方なし（常に False）。
    """
    def is_ally(self, actor_comp: "WorldObjectComponent | None", target_comp: "WorldObjectComponent | None") -> bool:
        # pack_id は ActorComponent の属性。味方関係はアクター同士でしか
        # 成り立たないので、片方でもアクターでなければ味方ではない。
        if not isinstance(actor_comp, ActorComponent) or not isinstance(
            target_comp, ActorComponent
        ):
            return False
        actor_pack = actor_comp.pack_id
        target_pack = target_comp.pack_id
        if actor_pack is None or target_pack is None:
            return False
        return bool(actor_pack == target_pack)
