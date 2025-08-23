
from typing import List
from src.domain.monster.monster_enum import Race
from src.domain.monster.drop_reward import DropReward
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.battle.battle_enum import Element
from src.domain.battle.battle_action import BattleAction
from src.domain.battle.combat_entity import CombatEntity


class Monster(CombatEntity):
    def __init__(
        self,
        monster_instance_id: int,
        monster_type_id: int,
        name: str,
        description: str,
        race: Race,
        element: Element,
        current_spot_id: int,
        base_status: BaseStatus,
        dynamic_status: DynamicStatus,
        available_actions: List[BattleAction],
        drop_reward: DropReward,
        allowed_areas: List[int]
    ):
        # 基底クラスの初期化
        super().__init__(name, race, element, current_spot_id, base_status, dynamic_status)
        
        # モンスター固有の属性
        self._monster_instance_id = monster_instance_id
        self._monster_type_id = monster_type_id
        self._description = description
        self._available_actions = available_actions
        self._drop_reward = drop_reward
        self._allowed_areas = allowed_areas

    @property
    def monster_instance_id(self) -> int:
        return self._monster_instance_id
    
    @property
    def monster_type_id(self) -> int:
        return self._monster_type_id
    
    @property
    def description(self) -> str:
        return self._description

    # ===== モンスター固有のメソッド =====
    
    def get_drop_reward(self) -> DropReward:
        return self._drop_reward
    
    def get_available_actions(self) -> List[BattleAction]:
        return self._available_actions
    
    def can_appear_in_area(self, area_id: int) -> bool:
        return area_id in self._allowed_areas