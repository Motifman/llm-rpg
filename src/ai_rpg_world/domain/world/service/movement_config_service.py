from abc import ABC, abstractmethod
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType


class MovementConfigService(ABC):
    """移動に関する設定値（スタミナ消費量など）を提供するドメインサービス"""

    @abstractmethod
    def get_stamina_cost(self, terrain_type: TerrainType) -> float:
        """指定された地形の1マス移動あたりのスタミナ消費量を取得"""
        pass


class DefaultMovementConfigService(MovementConfigService):
    """デフォルトの移動設定実装"""

    def __init__(self, base_stamina_cost: float = 1.0):
        self._base_stamina_cost = base_stamina_cost

    def get_stamina_cost(self, terrain_type: TerrainType) -> float:
        # 地形コストに比例してスタミナを消費させる例
        # 地形が1.0以上のコストなら、その分消費
        return self._base_stamina_cost * max(1.0, terrain_type.base_cost.value)
