from typing import List, Optional
from game.action.action_command import ActionCommand
from game.action.action_result import ActionResult
from game.action.action_strategy import ActionStrategy, ArgumentInfo
from game.player.player import Player
from game.core.game_context import GameContext
from game.battle.battle_manager import BattleManager
from game.enums import TurnActionType, BattleState, PlayerState


class BattleStartResult(ActionResult):
    def __init__(self, success: bool, message: str, battle_id: str = ""):
        super().__init__(success, message)
        self.battle_id = battle_id
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は戦闘を開始しました\n\t戦闘ID: {self.battle_id}"
        else:
            return f"{player_name} は戦闘を開始できませんでした\n\t理由: {self.message}"


class BattleStartStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("戦闘開始")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return []

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        # 通常状態の時のみ戦闘を開始できる
        if not acting_player.is_in_normal_state():
            return False
            
        spot_manager = game_context.get_spot_manager()
        current_spot = spot_manager.get_spot(acting_player.get_current_spot_id())
        if current_spot is None:
            return False
        
        monsters = current_spot.get_visible_monsters()
        return len(monsters) > 0

    def build_action_command(self, acting_player: Player, game_context: GameContext) -> ActionCommand:
        return BattleStartCommand()


class BattleStartCommand(ActionCommand):
    def __init__(self):
        super().__init__("戦闘開始")

    def execute(self, acting_player: Player, game_context: GameContext) -> BattleStartResult:
        battle_manager = game_context.get_battle_manager()
        if battle_manager is None:
            return BattleStartResult(False, "戦闘マネージャーが利用できません", "")
        
        spot_manager = game_context.get_spot_manager()
        current_spot = spot_manager.get_spot(acting_player.get_current_spot_id())
        if current_spot is None:
            return BattleStartResult(False, "現在の場所が見つかりません", "")
        
        monsters = current_spot.get_visible_monsters()
        if not monsters:
            return BattleStartResult(False, "この場所にはモンスターがいません", "")
        
        try:
            battle_id = battle_manager.start_battle(acting_player.get_current_spot_id(), monsters, acting_player)
            # プレイヤーの状態を戦闘状態に変更
            acting_player.set_player_state(PlayerState.BATTLE)
            return BattleStartResult(True, "戦闘を開始しました", battle_id)
        except Exception as e:
            return BattleStartResult(False, f"戦闘開始に失敗しました: {e}", "")


class BattleJoinResult(ActionResult):
    def __init__(self, success: bool, message: str, battle_id: str = ""):
        super().__init__(success, message)
        self.battle_id = battle_id
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は戦闘に参加しました\n\t戦闘ID: {self.battle_id}"
        else:
            return f"{player_name} は戦闘に参加できませんでした\n\t理由: {self.message}"


class BattleJoinStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("戦闘に参加")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return []

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        # 通常状態の時のみ戦闘に参加できる
        if not acting_player.is_in_normal_state():
            return False
            
        battle_manager = game_context.get_battle_manager()
        if battle_manager is None:
            return False
        
        current_spot_id = acting_player.get_current_spot_id()
        battle = battle_manager.get_battle_by_spot(current_spot_id)
        return battle is not None and battle.state == BattleState.ACTIVE

    def build_action_command(self, acting_player: Player, game_context: GameContext) -> ActionCommand:
        return BattleJoinCommand()


class BattleJoinCommand(ActionCommand):
    def __init__(self):
        super().__init__("戦闘に参加")

    def execute(self, acting_player: Player, game_context: GameContext) -> BattleJoinResult:
        battle_manager = game_context.get_battle_manager()
        if battle_manager is None:
            return BattleJoinResult(False, "戦闘マネージャーが利用できません", "")
        
        current_spot_id = acting_player.get_current_spot_id()
        battle = battle_manager.get_battle_by_spot(current_spot_id)
        if battle is None:
            return BattleJoinResult(False, "この場所で戦闘が行われていません", "")
        
        if battle.state != BattleState.ACTIVE:
            return BattleJoinResult(False, "戦闘は既に終了しています", battle.battle_id)
        
        player_id = acting_player.get_player_id()
        if player_id in battle.participants:
            return BattleJoinResult(False, "既に戦闘に参加しています", battle.battle_id)
        
        try:
            battle_manager.join_battle(battle.battle_id, acting_player)
            # プレイヤーの状態を戦闘状態に変更
            acting_player.set_player_state(PlayerState.BATTLE)
            return BattleJoinResult(True, "戦闘に参加しました", battle.battle_id)
        except Exception as e:
            return BattleJoinResult(False, f"戦闘参加に失敗しました: {e}", battle.battle_id)


class BattleActionResult(ActionResult):
    def __init__(self, success: bool, message: str, action_type: TurnActionType, target_id: str = ""):
        super().__init__(success, message)
        self.action_type = action_type
        self.target_id = target_id
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            action_name = self.action_type.value
            target_info = f" (対象: {self.target_id})" if self.target_id else ""
            return f"{player_name} は{action_name}を実行しました{target_info}\n\t{self.message}"
        else:
            return f"{player_name} は行動を実行できませんでした\n\t理由: {self.message}"


class BattleActionStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("戦闘時の行動")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        battle_manager = game_context.get_battle_manager()
        if battle_manager is None:
            return []
        
        current_spot_id = acting_player.get_current_spot_id()
        battle = battle_manager.get_battle_by_spot(current_spot_id)
        if battle is None:
            return []
        
        # 利用可能なモンスターのリストを取得
        available_monsters = []
        for monster_id, monster in battle.monsters.items():
            if monster.is_alive():
                available_monsters.append(monster_id)
        
        return [
            ArgumentInfo(
                name="action_type",
                description="実行する行動を選択してください",
                candidates=[action.value for action in TurnActionType]
            ),
            ArgumentInfo(
                name="target_monster_id",
                description="攻撃対象のモンスターIDを選択してください（攻撃の場合のみ必要）",
                candidates=available_monsters
            )
        ]

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        # 戦闘状態の時のみ戦闘行動ができる
        if not acting_player.is_in_battle_state():
            return False
            
        battle_manager = game_context.get_battle_manager()
        if battle_manager is None:
            return False
        
        current_spot_id = acting_player.get_current_spot_id()
        battle = battle_manager.get_battle_by_spot(current_spot_id)
        if battle is None:
            return False
        
        player_id = acting_player.get_player_id()
        return player_id in battle.participants and battle.state == BattleState.ACTIVE

    def build_action_command(self, acting_player: Player, game_context: GameContext, action_type: str, target_monster_id: str = "") -> ActionCommand:
        try:
            action_enum = TurnActionType(action_type)
        except ValueError:
            action_enum = TurnActionType.ATTACK
        
        return BattleActionCommand(action_enum, target_monster_id)


class BattleActionCommand(ActionCommand):
    def __init__(self, action_type: TurnActionType, target_monster_id: str = ""):
        super().__init__("戦闘時の行動")
        self.action_type = action_type
        self.target_monster_id = target_monster_id

    def execute(self, acting_player: Player, game_context: GameContext) -> BattleActionResult:
        battle_manager = game_context.get_battle_manager()
        if battle_manager is None:
            return BattleActionResult(False, "戦闘マネージャーが利用できません", self.action_type, self.target_monster_id)
        
        current_spot_id = acting_player.get_current_spot_id()
        battle = battle_manager.get_battle_by_spot(current_spot_id)
        if battle is None:
            return BattleActionResult(False, "この場所で戦闘が行われていません", self.action_type, self.target_monster_id)
        
        player_id = acting_player.get_player_id()
        if player_id not in battle.participants:
            return BattleActionResult(False, "戦闘に参加していません", self.action_type, self.target_monster_id)
        
        if battle.state != BattleState.ACTIVE:
            return BattleActionResult(False, "戦闘は既に終了しています", self.action_type, self.target_monster_id)
        
        # 攻撃の場合、ターゲットの存在確認
        if self.action_type == TurnActionType.ATTACK:
            if not self.target_monster_id:
                return BattleActionResult(False, "攻撃には対象のモンスターIDが必要です", self.action_type, self.target_monster_id)
            
            if self.target_monster_id not in battle.monsters:
                return BattleActionResult(False, f"モンスターID {self.target_monster_id} が見つかりません", self.action_type, self.target_monster_id)
            
            target_monster = battle.monsters[self.target_monster_id]
            if not target_monster.is_alive():
                return BattleActionResult(False, f"モンスター {self.target_monster_id} は既に倒されています", self.action_type, self.target_monster_id)
        
        try:
            # BattleManagerを通してBattleを取得し、execute_player_action関数を実行
            turn_action = battle.execute_player_action(player_id, self.target_monster_id, self.action_type)
            
            # 戦闘終了チェック
            if battle.is_battle_finished():
                battle_result = battle.get_battle_result()
                result_text = "勝利" if battle_result.victory else "敗北"
                if battle_result.escaped:
                    result_text = "逃走"
                
                # 戦闘に参加している全プレイヤーの状態を通常状態に戻す
                player_manager = game_context.get_player_manager()
                for participant_id in battle.participants:
                    participant = player_manager.get_player(participant_id)
                    if participant:
                        participant.set_player_state(PlayerState.NORMAL)
                
                message = f"行動を実行しました。戦闘が終了しました: {result_text}"
            else:
                message = f"行動を実行しました: {turn_action.message}"
            
            return BattleActionResult(True, message, self.action_type, self.target_monster_id)
        except Exception as e:
            return BattleActionResult(False, f"行動の実行に失敗しました: {e}", self.action_type, self.target_monster_id)

