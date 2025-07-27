from typing import List, Optional
from game.action.action_command import ActionCommand
from game.action.action_result import ActionResult
from game.action.action_strategy import ActionStrategy, ArgumentInfo
from game.player.player import Player
from game.core.game_context import GameContext
from game.conversation.conversation_manager import ConversationManager
from game.conversation.message_data import LocationChatMessage


class ConversationActionResult(ActionResult):
    """会話アクションの基底結果クラス"""
    def __init__(self, success: bool, message: str, session_id: str = None, participants: List[str] = None, history: str = ""):
        super().__init__(success, message)
        self.session_id = session_id
        self.participants = participants or []
        self.history = history


class StartConversationResult(ConversationActionResult):
    """会話開始結果"""
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            participants_text = ", ".join(self.participants) if self.participants else "なし"
            return f"{player_name} は会話を開始しました\n\tセッションID: {self.session_id}\n\t参加者: {participants_text}\n\t会話履歴:\n{self.history}"
        else:
            return f"{player_name} は会話を開始できませんでした\n\t理由: {self.message}"


class JoinConversationResult(ConversationActionResult):
    """会話参加結果"""
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            participants_text = ", ".join(self.participants) if self.participants else "なし"
            return f"{player_name} は会話に参加しました\n\tセッションID: {self.session_id}\n\t参加者: {participants_text}\n\t会話履歴:\n{self.history}"
        else:
            return f"{player_name} は会話に参加できませんでした\n\t理由: {self.message}"


class SpeakResult(ConversationActionResult):
    """発言結果"""
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            participants_text = ", ".join(self.participants) if self.participants else "なし"
            return f"{player_name} は発言しました\n\tセッションID: {self.session_id}\n\t参加者: {participants_text}\n\t会話履歴:\n{self.history}"
        else:
            return f"{player_name} は発言できませんでした\n\t理由: {self.message}"


class LeaveConversationResult(ConversationActionResult):
    """会話離脱結果"""
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            participants_text = ", ".join(self.participants) if self.participants else "なし"
            return f"{player_name} は会話から離脱しました\n\tセッションID: {self.session_id}\n\t参加者: {participants_text}\n\t会話履歴:\n{self.history}"
        else:
            return f"{player_name} は会話から離脱できませんでした\n\t理由: {self.message}"


# ActionStrategy クラス

class StartSpotConversationStrategy(ActionStrategy):
    """スポット全体向け会話セッション開始戦略"""
    def __init__(self):
        super().__init__("スポット会話開始")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="spot_id",
                description="会話を開始するスポットIDを入力してください",
                candidates=None  # 自由入力
            )
        ]
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, spot_id: str) -> ActionCommand:
        return StartSpotConversationCommand(spot_id)


class StartPrivateConversationStrategy(ActionStrategy):
    """特定プレイヤーとの会話セッション開始戦略"""
    def __init__(self):
        super().__init__("個人会話開始")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="target_player_id",
                description="会話を開始する対象プレイヤーIDを入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="spot_id",
                description="会話を行うスポットIDを入力してください",
                candidates=None  # 自由入力
            )
        ]

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext, target_player_id: str, spot_id: str) -> ActionCommand:
        return StartPrivateConversationCommand(target_player_id, spot_id)


class JoinSpotConversationStrategy(ActionStrategy):
    """スポット会話セッション参加戦略"""
    def __init__(self):
        super().__init__("スポット会話参加")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="spot_id",
                description="参加するスポットのIDを入力してください",
                candidates=None  # 自由入力
            )
        ]

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext, spot_id: str) -> ActionCommand:
        return JoinSpotConversationCommand(spot_id)


class SpeakInConversationStrategy(ActionStrategy):
    """会話セッションで発言戦略"""
    def __init__(self):
        super().__init__("会話発言")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="message",
                description="発言内容を入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="target_player_id",
                description="特定のプレイヤーに話しかける場合はプレイヤーIDを入力してください（全体発言の場合は空欄）",
                candidates=None  # 自由入力
            )
        ]

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext, message: str, target_player_id: str = None) -> ActionCommand:
        return SpeakInConversationCommand(message, target_player_id)


class LeaveConversationStrategy(ActionStrategy):
    """会話セッション抜け戦略"""
    def __init__(self):
        super().__init__("会話離脱")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return []  # 引数不要

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext) -> ActionCommand:
        return LeaveConversationCommand()


# ActionCommand クラス

class StartSpotConversationCommand(ActionCommand):
    """スポット全体向け会話セッション開始コマンド"""
    def __init__(self, spot_id: str):
        super().__init__("スポット会話開始")
        self.spot_id = spot_id

    def execute(self, acting_player: Player, game_context: GameContext) -> StartConversationResult:
        player_id = acting_player.get_player_id()
        conversation_manager = game_context.get_conversation_manager()
        
        if conversation_manager is None:
            return StartConversationResult(False, "会話システムが利用できません", None, [], "")
        
        # 既に会話に参加しているかチェック
        if conversation_manager.is_player_in_conversation(player_id):
            return StartConversationResult(False, "既に他の会話に参加しています", None, [], "")
        
        # セッション開始
        session_id = conversation_manager.start_conversation_session(self.spot_id, player_id)
        
        # 参加メッセージを記録
        join_message = LocationChatMessage(
            sender_id="System",
            spot_id=self.spot_id,
            content=f"{acting_player.get_name()} が会話を開始しました",
            target_player_id=None
        )
        conversation_manager.record_message(join_message)
        
        # 参加者と会話履歴を取得
        participants = list(conversation_manager.get_session_participants(session_id))
        history = conversation_manager.get_conversation_history_as_text(session_id)
        
        return StartConversationResult(True, f"{self.spot_id} で会話を開始しました", session_id, participants, history)


class StartPrivateConversationCommand(ActionCommand):
    """特定プレイヤーとの会話セッション開始コマンド"""
    def __init__(self, target_player_id: str, spot_id: str):
        super().__init__("個人会話開始")
        self.target_player_id = target_player_id
        self.spot_id = spot_id

    def execute(self, acting_player: Player, game_context: GameContext) -> StartConversationResult:
        player_id = acting_player.get_player_id()
        conversation_manager = game_context.get_conversation_manager()
        
        if conversation_manager is None:
            return StartConversationResult(False, "会話システムが利用できません", None, [], "")
        
        # 既に会話に参加しているかチェック
        if conversation_manager.is_player_in_conversation(player_id):
            return StartConversationResult(False, "既に他の会話に参加しています", None, [], "")
        
        # 個人宛セッション開始
        session_id = conversation_manager.start_private_conversation(player_id, self.spot_id)
        
        # 参加者と会話履歴を取得
        participants = list(conversation_manager.get_session_participants(session_id))
        history = conversation_manager.get_conversation_history_as_text(session_id)
        
        return StartConversationResult(True, f"{self.target_player_id} との個人会話を開始しました", session_id, participants, history)


class JoinSpotConversationCommand(ActionCommand):
    """スポット会話セッション参加コマンド"""
    def __init__(self, spot_id: str):
        super().__init__("スポット会話参加")
        self.spot_id = spot_id

    def execute(self, acting_player: Player, game_context: GameContext) -> JoinConversationResult:
        player_id = acting_player.get_player_id()
        conversation_manager = game_context.get_conversation_manager()
        
        if conversation_manager is None:
            return JoinConversationResult(False, "会話システムが利用できません", None, [], "")
        
        # 既に会話に参加しているかチェック
        if conversation_manager.is_player_in_conversation(player_id):
            return JoinConversationResult(False, "既に他の会話に参加しています", None, [], "")
        
        # スポットにアクティブなセッションがあるかチェック
        active_session = conversation_manager.get_active_session_for_spot(self.spot_id)
        if active_session is None:
            return JoinConversationResult(False, f"{self.spot_id} にアクティブな会話セッションがありません", None, [], "")
        
        # セッションに参加
        session_id = conversation_manager.join_conversation(player_id, self.spot_id)
        if session_id is None:
            return JoinConversationResult(False, "会話セッションに参加できませんでした", None, [], "")
        
        # 参加メッセージを記録
        join_message = LocationChatMessage(
            sender_id="System",
            spot_id=self.spot_id,
            content=f"{acting_player.get_name()} が会話に参加しました",
            target_player_id=None
        )
        conversation_manager.record_message(join_message)
        
        # 参加者と会話履歴を取得
        participants = list(conversation_manager.get_session_participants(session_id))
        history = conversation_manager.get_conversation_history_as_text(session_id)
        
        return JoinConversationResult(True, f"{self.spot_id} の会話に参加しました", session_id, participants, history)


class SpeakInConversationCommand(ActionCommand):
    """会話セッションで発言コマンド"""
    def __init__(self, message: str, target_player_id: str = None):
        super().__init__("会話発言")
        self.message = message
        self.target_player_id = target_player_id

    def execute(self, acting_player: Player, game_context: GameContext) -> SpeakResult:
        player_id = acting_player.get_player_id()
        conversation_manager = game_context.get_conversation_manager()
        
        if conversation_manager is None:
            return SpeakResult(False, "会話システムが利用できません", None, [], "")
        
        # 会話に参加しているかチェック
        if not conversation_manager.is_player_in_conversation(player_id):
            return SpeakResult(False, "会話に参加していません", None, [], "")
        
        # メッセージを作成
        message = LocationChatMessage(
            sender_id=player_id,
            spot_id=acting_player.get_current_spot_id(),
            content=self.message,
            target_player_id=self.target_player_id
        )
        
        # メッセージを記録
        session_id = conversation_manager.record_message(message)
        
        # 参加者と会話履歴を取得
        participants = list(conversation_manager.get_session_participants(session_id))
        history = conversation_manager.get_conversation_history_as_text(session_id)
        
        return SpeakResult(True, "発言しました", session_id, participants, history)


class LeaveConversationCommand(ActionCommand):
    """会話セッション抜けコマンド"""
    def __init__(self):
        super().__init__("会話離脱")

    def execute(self, acting_player: Player, game_context: GameContext) -> LeaveConversationResult:
        player_id = acting_player.get_player_id()
        conversation_manager = game_context.get_conversation_manager()
        
        if conversation_manager is None:
            return LeaveConversationResult(False, "会話システムが利用できません", None, [], "")
        
        # 会話に参加しているかチェック
        if not conversation_manager.is_player_in_conversation(player_id):
            return LeaveConversationResult(False, "会話に参加していません", None, [], "")
        
        # 現在のセッション情報を取得
        session_id = conversation_manager.player_sessions.get(player_id)
        spot_id = acting_player.get_current_spot_id()
        
        # 離脱メッセージを記録
        leave_message = LocationChatMessage(
            sender_id="System",
            spot_id=spot_id,
            content=f"{acting_player.get_name()} が会話から離脱しました",
            target_player_id=None
        )
        conversation_manager.record_message(leave_message)
        
        # 参加者と会話履歴を取得（離脱前）
        participants = list(conversation_manager.get_session_participants(session_id))
        history = conversation_manager.get_conversation_history_as_text(session_id)
        
        # セッションから離脱
        conversation_manager.leave_conversation(player_id)
        
        return LeaveConversationResult(True, "会話から離脱しました", session_id, participants, history)