from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId

if TYPE_CHECKING:
    from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate


class HitBoxRepository(Repository["HitBoxAggregate", HitBoxId], ABC):
    """HitBoxのリポジトリインターフェース"""

    @abstractmethod
    def generate_id(self) -> HitBoxId:
        """新しいHitBoxIdを生成する"""
        pass

    @abstractmethod
    def batch_generate_ids(self, count: int) -> list[HitBoxId]:
        """複数の新しいHitBoxIdを生成する"""
        pass

    @abstractmethod
    def save_all(self, entities: list["HitBoxAggregate"]) -> None:
        """複数のHitBoxを一括保存する"""
        pass

    @abstractmethod
    def find_active_by_spot_id(self, spot_id: SpotId) -> list["HitBoxAggregate"]:
        """指定スポット上のアクティブなHitBoxを取得する"""
        pass

    @abstractmethod
    def find_by_spot_id(self, spot_id: SpotId) -> list["HitBoxAggregate"]:
        """指定スポット上の全HitBoxを取得する"""
        pass
