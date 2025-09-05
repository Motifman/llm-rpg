
from typing import List
from src.domain.monster.drop_reward import DropReward
from src.domain.player.base_status import BaseStatus
from src.domain.battle.battle_enum import Element, Race
from src.domain.battle.battle_action import BattleAction
from src.domain.common.aggregate_root import AggregateRoot


class Monster(AggregateRoot):
    def __init__(
        self,
        monster_type_id: int,
        name: str,
        description: str,
        race: Race,
        element: Element,
        base_status: BaseStatus,
        max_hp: int,
        max_mp: int,
        available_actions: List[BattleAction],
        drop_reward: DropReward,
        allowed_areas: List[int]
    ):
        # モンスター固有の属性
        self._monster_type_id = monster_type_id
        self._name = name
        self._description = description
        self._race = race
        self._element = element
        self._base_status = base_status
        self._max_hp = max_hp
        self._max_mp = max_mp
        self._available_actions = available_actions
        self._drop_reward = drop_reward
        self._allowed_areas = allowed_areas

    @property
    def monster_type_id(self) -> int:
        return self._monster_type_id
    
    @property
    def description(self) -> str:
        return self._description

    @property
    def name(self) -> str:
        return self._name
    
    @property
    def race(self) -> Race:
        return self._race
    
    @property
    def element(self) -> Element:
        return self._element
    
    @property
    def base_status(self) -> BaseStatus:
        return self._base_status
    
    @property
    def max_hp(self) -> int:
        return self._max_hp
    
    @property
    def max_mp(self) -> int:
        return self._max_mp

    # ===== モンスター固有のメソッド =====
    def get_drop_reward(self) -> DropReward:
        return self._drop_reward
    
    def get_available_actions(self) -> List[BattleAction]:
        return self._available_actions
    
    def can_appear_in_area(self, area_id: int) -> bool:
        return area_id in self._allowed_areas

    def calculate_status_including_equipment(self) -> BaseStatus:
        """モンスターのステータスを計算（装備なしなのでbase_statusをそのまま返す）"""
        return self._base_status