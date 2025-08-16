
from typing import List
from src.domain.monster.monster_enum import Race
from src.domain.monster.drop_reward import DropReward
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.battle.battle_enum import StatusEffectType, Element
from src.domain.battle.battle_action import BattleAction
from src.domain.battle.status_effect_result import StatusEffectResult
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
        drop_reward: DropReward
    ):
        # 基底クラスの初期化
        super().__init__(name, race, current_spot_id, base_status, dynamic_status)
        
        # モンスター固有の属性
        self._monster_instance_id = monster_instance_id
        self._monster_type_id = monster_type_id
        self._description = description
        self._element = element
        self._available_actions = available_actions
        self._drop_reward = drop_reward
    
    @property
    def monster_instance_id(self) -> int:
        return self._monster_instance_id
    
    @property
    def monster_type_id(self) -> int:
        return self._monster_type_id
    
    @property
    def description(self) -> str:
        return self._description
    
    @property
    def element(self) -> Element:
        return self._element



    # ===== モンスター固有のメソッド =====
    
    def get_drop_reward(self) -> DropReward:
        return self._drop_reward
    
    def get_available_actions(self) -> List[BattleAction]:
        return self._available_actions
    
    # ===== ステータス表示 =====
    def get_full_status_display(self) -> str:
        lines = [f"=== {self.name} ==="]
        lines.append(f"HP: {self.hp}/{self.max_hp}")
        lines.append(f"MP: {self.mp}/{self.max_mp}")
        lines.append("")
        lines.append("=== ステータス ===")
        lines.append(f"攻撃力: {self.attack} (ベース:{self._base_status.attack} + 効果:{self._dynamic_status.get_effect_bonus(StatusEffectType.ATTACK_UP)})")
        lines.append(f"防御力: {self.defense} (ベース:{self._base_status.defense} + 効果:{self._dynamic_status.get_effect_bonus(StatusEffectType.DEFENSE_UP)})")
        lines.append(f"素早さ: {self.speed} (ベース:{self._base_status.speed} + 効果:{self._dynamic_status.get_effect_bonus(StatusEffectType.SPEED_UP)})")
        lines.append("")
        
        return "\n".join(lines)