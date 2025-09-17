import random
from typing import List, Optional
from src.domain.battle.combat_state import CombatState
from src.domain.battle.battle_action import BattleAction
from src.domain.battle.battle_enum import ParticipantType


class MonsterActionService:
    """モンスターの行動選択ドメインサービス（リポジトリに依存しない）"""

    def select_monster_action(
        self,
        monster_state: CombatState,
        available_actions: List[BattleAction],
        all_participants: List[CombatState]
    ) -> Optional[BattleAction]:
        """モンスターの行動を選択（純粋なドメインロジック）"""
        if not available_actions:
            return None

        # シンプルなAIロジック
        return self._select_action_with_ai(monster_state, available_actions, all_participants)

    def _select_action_with_ai(
        self,
        monster_state: CombatState,
        available_actions: List[BattleAction],
        all_participants: List[CombatState]
    ) -> Optional[BattleAction]:
        """AIによる行動選択"""

        # 生存しているプレイヤーを取得
        alive_players = [
            p for p in all_participants
            if p.participant_type == ParticipantType.PLAYER and p.is_alive()
        ]

        if not alive_players:
            return None

        # HPが少ない場合、回復アクションを優先
        if monster_state.current_hp.value < monster_state.current_hp.max_hp * 0.3:
            heal_actions = [a for a in available_actions if a.heal_hp_amount and a.heal_hp_amount > 0]
            if heal_actions:
                return random.choice(heal_actions)

        # 通常攻撃を優先
        attack_actions = [a for a in available_actions if a.damage_multiplier and a.damage_multiplier > 0]
        if attack_actions:
            return random.choice(attack_actions)

        # それ以外の場合、ランダムに選択
        return random.choice(available_actions) if available_actions else None
