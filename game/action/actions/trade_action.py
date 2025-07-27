from typing import List, Optional, Dict, Any
from game.action.action_command import ActionCommand
from game.action.action_result import ActionResult
from game.action.action_strategy import ActionStrategy, ArgumentInfo
from game.player.player import Player
from game.core.game_context import GameContext
from game.trade.trade_manager import TradeManager
from game.trade.trade_data import TradeOffer
from game.enums import TradeType, TradeStatus


class TradeActionResult(ActionResult):
    """取引アクションの基底結果クラス"""
    def __init__(self, success: bool, message: str, trade_id: str = None, trade_details: str = ""):
        super().__init__(success, message)
        self.trade_id = trade_id
        self.trade_details = trade_details


class PostTradeResult(TradeActionResult):
    """取引出品結果"""
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は取引を出品しました\n\t取引ID: {self.trade_id}\n\t取引詳細: {self.trade_details}"
        else:
            return f"{player_name} は取引を出品できませんでした\n\t理由: {self.message}"


class AcceptTradeResult(TradeActionResult):
    """取引受託結果"""
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は取引を受託しました\n\t取引ID: {self.trade_id}\n\t取引詳細: {self.trade_details}"
        else:
            return f"{player_name} は取引を受託できませんでした\n\t理由: {self.message}"


class CancelTradeResult(TradeActionResult):
    """取引キャンセル結果"""
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は取引をキャンセルしました\n\t取引ID: {self.trade_id}\n\t取引詳細: {self.trade_details}"
        else:
            return f"{player_name} は取引をキャンセルできませんでした\n\t理由: {self.message}"


class GetMyTradesResult(TradeActionResult):
    """自分の取引取得結果"""
    def __init__(self, success: bool, message: str, trades: List[TradeOffer] = None, include_history: bool = False):
        super().__init__(success, message)
        self.trades = trades or []
        self.include_history = include_history
    
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            trade_count = len(self.trades)
            history_text = "（履歴含む）" if self.include_history else "（アクティブのみ）"
            trades_text = "\n".join([f"\t- {trade.get_trade_summary()}" for trade in self.trades])
            return f"{player_name} の取引一覧{history_text}\n\t取引数: {trade_count}\n{trades_text}"
        else:
            return f"{player_name} の取引一覧を取得できませんでした\n\t理由: {self.message}"


class GetAvailableTradesResult(TradeActionResult):
    """受託可能取引取得結果"""
    def __init__(self, success: bool, message: str, trades: List[TradeOffer] = None, filters: Dict[str, Any] = None):
        super().__init__(success, message)
        self.trades = trades or []
        self.filters = filters or {}
    
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            trade_count = len(self.trades)
            filters_text = f"（フィルタ: {self.filters}）" if self.filters else ""
            trades_text = "\n".join([f"\t- {trade.get_trade_summary()}" for trade in self.trades])
            return f"{player_name} が受託可能な取引一覧{filters_text}\n\t取引数: {trade_count}\n{trades_text}"
        else:
            return f"{player_name} が受託可能な取引一覧を取得できませんでした\n\t理由: {self.message}"


# ActionStrategy クラス

class PostTradeStrategy(ActionStrategy):
    """取引出品戦略"""
    def __init__(self):
        super().__init__("取引出品")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="offered_item_id",
                description="出品するアイテムIDを入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="offered_item_count",
                description="出品するアイテム数を入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="requested_money",
                description="要求するお金を入力してください（アイテム取引の場合は0）",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="requested_item_id",
                description="要求するアイテムIDを入力してください（お金取引の場合は空欄）",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="requested_item_count",
                description="要求するアイテム数を入力してください（デフォルト: 1）",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="trade_type",
                description="取引タイプを選択してください",
                candidates=["global", "direct"]
            ),
            ArgumentInfo(
                name="target_player_id",
                description="直接取引の場合の対象プレイヤーIDを入力してください（グローバル取引の場合は空欄）",
                candidates=None  # 自由入力
            )
        ]
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return game_context.get_trade_manager() is not None
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, 
                           offered_item_id: str, offered_item_count: int, requested_money: int,
                           requested_item_id: str = None, requested_item_count: int = 1,
                           trade_type: str = "global", target_player_id: str = None) -> ActionCommand:
        return PostTradeCommand(offered_item_id, offered_item_count, requested_money,
                              requested_item_id, requested_item_count, trade_type, target_player_id)


class AcceptTradeStrategy(ActionStrategy):
    """取引受託戦略"""
    def __init__(self):
        super().__init__("取引受託")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="trade_id",
                description="受託する取引IDを入力してください",
                candidates=None  # 自由入力
            )
        ]
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return game_context.get_trade_manager() is not None
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, trade_id: str) -> ActionCommand:
        return AcceptTradeCommand(trade_id)


class CancelTradeStrategy(ActionStrategy):
    """取引キャンセル戦略"""
    def __init__(self):
        super().__init__("取引キャンセル")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="trade_id",
                description="キャンセルする取引IDを入力してください",
                candidates=None  # 自由入力
            )
        ]
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return game_context.get_trade_manager() is not None
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, trade_id: str) -> ActionCommand:
        return CancelTradeCommand(trade_id)


class GetMyTradesStrategy(ActionStrategy):
    """自分の取引取得戦略"""
    def __init__(self):
        super().__init__("自分の取引取得")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="include_history",
                description="履歴も含めるかどうかを選択してください",
                candidates=["True", "False"]
            )
        ]
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return game_context.get_trade_manager() is not None
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, include_history: str = "False") -> ActionCommand:
        return GetMyTradesCommand(include_history.lower() == "true")


class GetAvailableTradesStrategy(ActionStrategy):
    """受託可能取引取得戦略"""
    def __init__(self):
        super().__init__("受託可能取引取得")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="offered_item_id",
                description="出品アイテムIDでフィルタする場合を入力してください（空欄可）",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="requested_item_id",
                description="要求アイテムIDでフィルタする場合を入力してください（空欄可）",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="max_price",
                description="最大価格でフィルタする場合を入力してください（空欄可）",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="min_price",
                description="最小価格でフィルタする場合を入力してください（空欄可）",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="trade_type",
                description="取引タイプでフィルタする場合を選択してください（空欄可）",
                candidates=["global", "direct"]
            ),
            ArgumentInfo(
                name="seller_id",
                description="出品者IDでフィルタする場合を入力してください（空欄可）",
                candidates=None  # 自由入力
            )
        ]
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return game_context.get_trade_manager() is not None
    
    def build_action_command(self, acting_player: Player, game_context: GameContext,
                           offered_item_id: str = None, requested_item_id: str = None,
                           max_price: str = None, min_price: str = None,
                           trade_type: str = None, seller_id: str = None) -> ActionCommand:
        filters = {}
        if offered_item_id:
            filters["offered_item_id"] = offered_item_id
        if requested_item_id:
            filters["requested_item_id"] = requested_item_id
        if max_price:
            filters["max_price"] = int(max_price)
        if min_price:
            filters["min_price"] = int(min_price)
        if trade_type:
            filters["trade_type"] = TradeType(trade_type)
        if seller_id:
            filters["seller_id"] = seller_id
        
        return GetAvailableTradesCommand(filters)


# ActionCommand クラス

class PostTradeCommand(ActionCommand):
    """取引出品コマンド"""
    def __init__(self, offered_item_id: str, offered_item_count: int, requested_money: int,
                 requested_item_id: str = None, requested_item_count: int = 1,
                 trade_type: str = "global", target_player_id: str = None):
        super().__init__("取引出品")
        self.offered_item_id = offered_item_id
        self.offered_item_count = offered_item_count
        self.requested_money = requested_money
        self.requested_item_id = requested_item_id
        self.requested_item_count = requested_item_count
        self.trade_type = TradeType(trade_type)
        self.target_player_id = target_player_id

    def execute(self, acting_player: Player, game_context: GameContext) -> PostTradeResult:
        player_id = acting_player.get_player_id()
        trade_manager = game_context.get_trade_manager()
        
        if trade_manager is None:
            return PostTradeResult(False, "取引システムが利用できません", None, "")
        
        try:
            # アイテムの所持チェック
            if not acting_player.has_item(self.offered_item_id):
                return PostTradeResult(False, f"アイテム {self.offered_item_id} を所持していません", None, "")
            
            item_count = acting_player.get_inventory_item_count(self.offered_item_id)
            if item_count < self.offered_item_count:
                return PostTradeResult(False, f"アイテム {self.offered_item_id} が不足しています（所持: {item_count}, 必要: {self.offered_item_count}）", None, "")
            
            # お金の所持チェック（アイテム取引の場合）
            if self.requested_item_id and self.requested_money > 0:
                if acting_player.status.get_money() < self.requested_money:
                    return PostTradeResult(False, f"お金が不足しています（所持: {acting_player.status.get_money()}, 必要: {self.requested_money}）", None, "")
            
            # TradeOfferを作成
            if self.requested_item_id:
                # アイテム同士の取引
                trade_offer = TradeOffer.create_item_trade(
                    seller_id=player_id,
                    offered_item_id=self.offered_item_id,
                    offered_item_count=self.offered_item_count,
                    requested_item_id=self.requested_item_id,
                    requested_item_count=self.requested_item_count,
                    trade_type=self.trade_type,
                    target_player_id=self.target_player_id
                )
            else:
                # お金との取引
                trade_offer = TradeOffer.create_money_trade(
                    seller_id=player_id,
                    offered_item_id=self.offered_item_id,
                    offered_item_count=self.offered_item_count,
                    requested_money=self.requested_money,
                    trade_type=self.trade_type,
                    target_player_id=self.target_player_id
                )
            
            # 取引を出品
            success = trade_manager.post_trade(trade_offer)
            
            if success:
                return PostTradeResult(True, "取引を出品しました", trade_offer.trade_id, trade_offer.get_trade_summary())
            else:
                return PostTradeResult(False, "取引の出品に失敗しました", None, "")
                
        except Exception as e:
            return PostTradeResult(False, f"取引出品中にエラーが発生しました: {str(e)}", None, "")


class AcceptTradeCommand(ActionCommand):
    """取引受託コマンド"""
    def __init__(self, trade_id: str):
        super().__init__("取引受託")
        self.trade_id = trade_id

    def execute(self, acting_player: Player, game_context: GameContext) -> AcceptTradeResult:
        player_id = acting_player.get_player_id()
        trade_manager = game_context.get_trade_manager()
        player_manager = game_context.get_player_manager()
        
        if trade_manager is None:
            return AcceptTradeResult(False, "取引システムが利用できません", None, "")
        
        try:
            # 取引情報を取得
            trade = trade_manager.get_trade(self.trade_id)
            if trade is None:
                return AcceptTradeResult(False, f"取引 {self.trade_id} が見つかりません", None, "")
            
            # 出品者を取得
            seller = player_manager.get_player(trade.seller_id)
            if seller is None:
                return AcceptTradeResult(False, f"出品者 {trade.seller_id} が見つかりません", None, "")
            
            # 取引を受託（アイテム・お金のやり取りを含む）
            completed_trade = trade_manager.accept_trade(self.trade_id, player_id, seller, acting_player)
            return AcceptTradeResult(True, "取引を受託しました", completed_trade.trade_id, completed_trade.get_trade_summary())
            
        except ValueError as e:
            return AcceptTradeResult(False, str(e), None, "")
        except Exception as e:
            return AcceptTradeResult(False, f"取引受託中にエラーが発生しました: {str(e)}", None, "")


class CancelTradeCommand(ActionCommand):
    """取引キャンセルコマンド"""
    def __init__(self, trade_id: str):
        super().__init__("取引キャンセル")
        self.trade_id = trade_id

    def execute(self, acting_player: Player, game_context: GameContext) -> CancelTradeResult:
        player_id = acting_player.get_player_id()
        trade_manager = game_context.get_trade_manager()
        
        if trade_manager is None:
            return CancelTradeResult(False, "取引システムが利用できません", None, "")
        
        try:
            # 取引をキャンセル
            success = trade_manager.cancel_trade(self.trade_id, player_id)
            
            if success:
                # キャンセルされた取引の詳細を取得
                cancelled_trades = trade_manager.get_trade_history({"trade_id": self.trade_id})
                cancelled_trade = cancelled_trades[0] if cancelled_trades else None
                trade_details = cancelled_trade.get_trade_summary() if cancelled_trade else "詳細不明"
                return CancelTradeResult(True, "取引をキャンセルしました", self.trade_id, trade_details)
            else:
                return CancelTradeResult(False, "取引のキャンセルに失敗しました", None, "")
                
        except ValueError as e:
            return CancelTradeResult(False, str(e), None, "")
        except Exception as e:
            return CancelTradeResult(False, f"取引キャンセル中にエラーが発生しました: {str(e)}", None, "")


class GetMyTradesCommand(ActionCommand):
    """自分の取引取得コマンド"""
    def __init__(self, include_history: bool = False):
        super().__init__("自分の取引取得")
        self.include_history = include_history

    def execute(self, acting_player: Player, game_context: GameContext) -> GetMyTradesResult:
        player_id = acting_player.get_player_id()
        trade_manager = game_context.get_trade_manager()
        
        if trade_manager is None:
            return GetMyTradesResult(False, "取引システムが利用できません", [], self.include_history)
        
        try:
            # 自分の取引を取得
            trades = trade_manager.get_player_trades(player_id, self.include_history)
            return GetMyTradesResult(True, "自分の取引を取得しました", trades, self.include_history)
            
        except Exception as e:
            return GetMyTradesResult(False, f"取引取得中にエラーが発生しました: {str(e)}", [], self.include_history)


class GetAvailableTradesCommand(ActionCommand):
    """受託可能取引取得コマンド"""
    def __init__(self, filters: Dict[str, Any] = None):
        super().__init__("受託可能取引取得")
        self.filters = filters or {}

    def execute(self, acting_player: Player, game_context: GameContext) -> GetAvailableTradesResult:
        player_id = acting_player.get_player_id()
        trade_manager = game_context.get_trade_manager()
        
        if trade_manager is None:
            return GetAvailableTradesResult(False, "取引システムが利用できません", [], self.filters)
        
        try:
            # 受託可能な取引を取得
            available_trades = trade_manager.get_available_trades_for_player(player_id)
            
            # フィルタリングを適用
            if self.filters:
                filtered_trades = []
                for trade in available_trades:
                    if trade_manager._matches_filters(trade, self.filters):
                        filtered_trades.append(trade)
                available_trades = filtered_trades
            
            return GetAvailableTradesResult(True, "受託可能な取引を取得しました", available_trades, self.filters)
            
        except Exception as e:
            return GetAvailableTradesResult(False, f"取引取得中にエラーが発生しました: {str(e)}", [], self.filters) 