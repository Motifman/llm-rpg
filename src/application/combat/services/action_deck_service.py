from typing import List, TYPE_CHECKING
from src.domain.battle.battle_action import BattleAction
from src.domain.battle.action_slot import ActionSlot
from src.domain.battle.action_mastery import ActionMastery
from src.domain.common.value_object import Level

if TYPE_CHECKING:
    from src.domain.player.player import Player
    from src.domain.battle.action_repository import ActionRepository
    from src.domain.player.player_repository import PlayerRepository


class ActionDeckApplicationService:
    """Actionデッキ関連のアプリケーションサービス"""
    
    def __init__(
        self,
        player_repository: "PlayerRepository",
        action_repository: "ActionRepository"
    ):
        self._player_repository = player_repository
        self._action_repository = action_repository
    
    def learn_player_action(self, player_id: int, action_id: int) -> None:
        """プレイヤーの技習得"""
        # プレイヤーを取得
        player = self._player_repository.find_by_id(player_id)
        if player is None:
            raise ValueError(f"Player not found. player_id: {player_id}")
        
        # 習得可能かチェック（アプリケーション層の責務）
        player_level = Level(player._dynamic_status.level)
        learnable_actions = self._action_repository.get_learnable_actions(player_level.value, player.role)
        if action_id not in learnable_actions:
            raise ValueError(f"Action not learnable for player. action_id: {action_id}")
        
        # アクションスロットを作成
        action_cost = self._action_repository.get_action_cost(action_id)
        action_slot = ActionSlot(action_id, 1, action_cost)
        
        # 技を習得（ドメインロジック）
        player.learn_action(action_slot)
        
        # プレイヤーを保存
        self._player_repository.save(player)
    
    def forget_player_action(self, player_id: int, action_id: int) -> None:
        """プレイヤーの技忘却"""
        # プレイヤーを取得
        player = self._player_repository.find_by_id(player_id)
        if player is None:
            raise ValueError(f"Player not found. player_id: {player_id}")
        
        # 基本技かどうかをチェック（アプリケーション層の責務）
        is_basic = self._action_repository.is_basic_action(action_id)
        
        # 技を忘れる（ドメインロジック）
        player.forget_action(action_id, is_basic)
        
        # プレイヤーを保存
        self._player_repository.save(player)
    
    def evolve_player_action(self, player_id: int, action_id: int) -> None:
        """プレイヤーの技進化"""
        # プレイヤーを取得
        player = self._player_repository.find_by_id(player_id)
        if player is None:
            raise ValueError(f"Player not found. player_id: {player_id}")
        
        # 進化可能かチェック（アプリケーション層の責務）
        mastery = player.get_action_mastery(action_id)
        if mastery is None:
            raise ValueError(f"Action mastery not found. action_id: {action_id}")
        
        # 進化先の取得
        evolved_action_id = self._action_repository.get_evolved_action_id(action_id)
        if evolved_action_id is None:
            raise ValueError(f"No evolution available for action. action_id: {action_id}")
        
        # 進化要件チェック
        requirements = self._action_repository.get_evolution_requirements(action_id)
        if requirements is None:
            raise ValueError(f"No evolution requirements found. action_id: {action_id}")
        
        required_exp, required_level = requirements
        if not mastery.can_evolve(required_exp, required_level):
            raise ValueError(f"Evolution requirements not met. action_id: {action_id}")
        
        # 進化後のコストを取得
        evolved_cost = self._action_repository.get_action_cost(evolved_action_id)
        
        # 技を進化（ドメインロジック）
        player.evolve_action(action_id, evolved_action_id, evolved_cost)
        
        # プレイヤーを保存
        self._player_repository.save(player)
    
    def gain_player_action_experience(self, player_id: int, action_id: int, experience: int) -> None:
        """プレイヤーの技経験値獲得"""
        # プレイヤーを取得
        player = self._player_repository.find_by_id(player_id)
        if player is None:
            raise ValueError(f"Player not found. player_id: {player_id}")
        
        # 経験値を獲得
        player.gain_action_experience(action_id, experience)
        
        # プレイヤーを保存
        self._player_repository.save(player)
    
    def level_up_player_action(self, player_id: int, action_id: int) -> None:
        """プレイヤーの技レベルアップ"""
        # プレイヤーを取得
        player = self._player_repository.find_by_id(player_id)
        if player is None:
            raise ValueError(f"Player not found. player_id: {player_id}")
        
        # 技のレベルアップ
        player.level_up_action(action_id)
        
        # プレイヤーを保存
        self._player_repository.save(player)
    
    def get_available_actions_for_battle(self, player_id: int) -> List[BattleAction]:
        """戦闘用のアクション取得"""
        # プレイヤーを取得
        player = self._player_repository.find_by_id(player_id)
        if player is None:
            raise ValueError(f"Player not found. player_id: {player_id}")
        
        # デッキからアクションIDを取得
        action_ids = player.action_deck.get_action_ids()
        
        # ActionRepositoryから実際のBattleActionを取得
        return self._action_repository.find_by_ids(action_ids)
    
    def get_learnable_actions_for_player(self, player_id: int) -> List[int]:
        """プレイヤーが習得可能な技のリストを取得"""
        # プレイヤーを取得
        player = self._player_repository.find_by_id(player_id)
        if player is None:
            raise ValueError(f"Player not found. player_id: {player_id}")
        
        # 習得可能な技を取得（アプリケーション層でロジックを実装）
        player_level = Level(player._dynamic_status.level)
        all_learnable = self._action_repository.get_learnable_actions(player_level.value, player.role)
        
        # 現在のデッキに対して習得可能な技のみをフィルタリング
        result = []
        for action_id in all_learnable:
            # 既に習得済みかチェック
            if player.action_deck.has_action(action_id):
                continue
            
            # キャパシティチェック
            action_cost = self._action_repository.get_action_cost(action_id)
            action_slot = ActionSlot(action_id, 1, action_cost)
            if player.action_deck.can_add_action(action_slot):
                result.append(action_id)
        
        return result
    
    def can_evolve_action(self, player_id: int, action_id: int) -> bool:
        """技が進化可能かどうかを判定"""
        # プレイヤーを取得
        player = self._player_repository.find_by_id(player_id)
        if player is None:
            raise ValueError(f"Player not found. player_id: {player_id}")
        
        # 習熟度を取得
        mastery = player.get_action_mastery(action_id)
        if mastery is None:
            return False
        
        # 進化先が存在するかチェック
        evolved_action_id = self._action_repository.get_evolved_action_id(action_id)
        if evolved_action_id is None:
            return False
        
        # 進化要件をチェック
        requirements = self._action_repository.get_evolution_requirements(action_id)
        if requirements is None:
            return False
        
        required_exp, required_level = requirements
        return mastery.can_evolve(required_exp, required_level)
    
    def get_action_evolution_preview(self, action_id: int) -> dict:
        """技の進化プレビュー情報を取得"""
        evolved_action_id = self._action_repository.get_evolved_action_id(action_id)
        requirements = self._action_repository.get_evolution_requirements(action_id)
        
        result = {
            "can_evolve": evolved_action_id is not None,
            "evolved_action_id": evolved_action_id,
            "requirements": None
        }
        
        if requirements is not None:
            result["requirements"] = {
                "required_experience": requirements[0],
                "required_level": requirements[1]
            }
        
        return result
    
    def get_player_deck_info(self, player_id: int) -> dict:
        """プレイヤーのデッキ情報を取得"""
        # プレイヤーを取得
        player = self._player_repository.find_by_id(player_id)
        if player is None:
            raise ValueError(f"Player not found. player_id: {player_id}")
        
        deck = player.action_deck
        
        return {
            "current_capacity_usage": deck.current_capacity_usage(),
            "max_capacity": deck.capacity.max_capacity,
            "remaining_capacity": deck.remaining_capacity(),
            "slot_count": deck.slot_count(),
            "is_full": deck.is_full(),
            "action_slots": [
                {
                    "action_id": slot.action_id,
                    "level": slot.level,
                    "cost": slot.cost
                }
                for slot in deck.slots
            ],
            "action_masteries": {
                action_id: {
                    "experience": mastery.experience,
                    "level": mastery.level
                }
                for action_id, mastery in player.action_masteries.items()
            }
        }
