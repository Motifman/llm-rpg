from typing import Optional, List
from datetime import datetime
from src.application.trade.contracts.commands import (
    CreateTradeCommand,
    ExecuteTradeCommand,
    CancelTradeCommand,
    GetPlayerTradesCommand,
    GetGlobalTradesCommand
)
from src.application.trade.contracts.dtos import (
    CreateTradeResultDto,
    ExecuteTradeResultDto,
    CancelTradeResultDto,
    PlayerTradesDto,
    GlobalTradesDto,
    TradeOfferDto,
    TradeItemDto
)
from src.domain.trade.trade_service import TradeService
from src.domain.trade.trade import TradeOffer, TradeItem
from src.domain.player.player_repository import PlayerRepository
from src.domain.trade.trade_repository import TradeRepository
from src.domain.trade.trade_event_dispatcher import TradeEventDispatcher
from src.domain.trade.trade_exception import (
    InsufficientItemsException,
    InsufficientGoldException,
    InvalidTradeStatusException,
    CannotAcceptOwnTradeException,
    CannotAcceptTradeWithOtherPlayerException,
    CannotCancelTradeWithOtherPlayerException,
    ItemNotTradeableException,
)


class TradeApplicationService:
    """取引アプリケーションサービス"""
    
    def __init__(
        self,
        trade_service: TradeService,
        player_repository: PlayerRepository,
        trade_repository: TradeRepository,
        event_dispatcher: TradeEventDispatcher = None
    ):
        self._trade_service = trade_service
        self._player_repository = player_repository
        self._trade_repository = trade_repository
        self._event_dispatcher = event_dispatcher
    
    def create_trade(self, command: CreateTradeCommand) -> CreateTradeResultDto:
        """取引を作成する
        
        Args:
            command: 取引作成コマンド
            
        Returns:
            CreateTradeResultDto: 作成結果
        """
        try:
            # 1. 売り手プレイヤーを取得
            seller = self._player_repository.find_by_id(command.seller_id)
            if not seller:
                return CreateTradeResultDto(
                    success=False,
                    message="取引作成に失敗しました",
                    error_message=f"売り手プレイヤーが見つかりません: {command.seller_id}"
                )
            
            # 2. アイテムの所有確認
            trade_item = seller.prepare_trade_offer(command)
            
            # 3. 取引オファーを作成
            trade_offer = TradeOffer.create_trade(
                trade_id=self._trade_repository.generate_trade_id(),
                seller_id=command.seller_id,
                requested_gold=command.requested_gold,
                trade_item=trade_item,
                created_at=datetime.now(),
                trade_type=command.trade_type,
                target_player_id=command.target_player_id,
                seller_name=seller.name,
                target_player_name=self._get_target_player_name(command.target_player_id) if command.target_player_id else None
            )
            
            # 4. 取引を保存
            self._trade_repository.save(trade_offer)
            
            # 5. ドメインイベントをディスパッチ
            if self._event_dispatcher:
                events = trade_offer.get_events()
                self._event_dispatcher.dispatch_all_events(events)
                trade_offer.clear_events()
            
            return CreateTradeResultDto(
                success=True,
                trade_id=trade_offer.trade_id,
                message=f"取引を作成しました (ID: {trade_offer.trade_id})"
            )
        
        except (InsufficientItemsException, ItemNotTradeableException) as e:
            return CreateTradeResultDto(
                success=False,
                message="取引作成に失敗しました",
                error_message=str(e)
            )
    
    def execute_trade(self, command: ExecuteTradeCommand) -> ExecuteTradeResultDto:
        """取引を実行する
        
        Args:
            command: 取引実行コマンド
            
        Returns:
            ExecuteTradeResultDto: 実行結果
        """
        try:
            # 1. 取引オファーを取得
            trade_offer = self._trade_repository.find_by_id(command.trade_id)
            if not trade_offer:
                return ExecuteTradeResultDto(
                    success=False,
                    trade_id=command.trade_id,
                    seller_id=0,
                    buyer_id=command.buyer_id,
                    offered_item=TradeItemDto(item_id=0),
                    requested_gold=0,
                    message="取引実行に失敗しました",
                    error_message=f"取引が見つかりません: {command.trade_id}"
                )
            
            # 2. プレイヤーを取得
            buyer = self._player_repository.find_by_id(command.buyer_id)
            seller = self._player_repository.find_by_id(trade_offer.seller_id)
            
            if not buyer:
                return ExecuteTradeResultDto(
                    success=False,
                    trade_id=command.trade_id,
                    seller_id=trade_offer.seller_id,
                    buyer_id=command.buyer_id,
                    offered_item=self._convert_to_trade_item_dto(trade_offer.offered_item),
                    requested_gold=trade_offer.requested_gold,
                    message="取引実行に失敗しました",
                    error_message=f"買い手プレイヤーが見つかりません: {command.buyer_id}"
                )
            
            if not seller:
                return ExecuteTradeResultDto(
                    success=False,
                    trade_id=command.trade_id,
                    seller_id=trade_offer.seller_id,
                    buyer_id=command.buyer_id,
                    offered_item=self._convert_to_trade_item_dto(trade_offer.offered_item),
                    requested_gold=trade_offer.requested_gold,
                    message="取引実行に失敗しました",
                    error_message=f"売り手プレイヤーが見つかりません: {trade_offer.seller_id}"
                )
            
            # 3. ドメインサービスで取引実行
            self._trade_service.execute_trade(trade_offer, buyer, seller)
            
            # 4. エンティティを保存
            self._trade_repository.save(trade_offer)
            self._player_repository.save(buyer)
            self._player_repository.save(seller)
            
            # 5. ドメインイベントをディスパッチ
            if self._event_dispatcher:
                events = trade_offer.get_events()
                self._event_dispatcher.dispatch_all_events(events)
                trade_offer.clear_events()
            
            return ExecuteTradeResultDto(
                success=True,
                trade_id=trade_offer.trade_id,
                seller_id=trade_offer.seller_id,
                buyer_id=command.buyer_id,
                offered_item=self._convert_to_trade_item_dto(trade_offer.offered_item),
                requested_gold=trade_offer.requested_gold,
                message=f"取引が成立しました (ID: {trade_offer.trade_id})"
            )
            
        except (InsufficientItemsException, InsufficientGoldException,
                InvalidTradeStatusException, CannotAcceptOwnTradeException,
                CannotAcceptTradeWithOtherPlayerException) as e:
            return ExecuteTradeResultDto(
                success=False,
                trade_id=command.trade_id,
                seller_id=trade_offer.seller_id if trade_offer else 0,
                buyer_id=command.buyer_id,
                offered_item=self._convert_to_trade_item_dto(trade_offer.offered_item) if trade_offer else TradeItemDto(item_id=0),
                requested_gold=trade_offer.requested_gold if trade_offer else 0,
                message="取引実行に失敗しました",
                error_message=str(e)
            )
    
    def cancel_trade(self, command: CancelTradeCommand) -> CancelTradeResultDto:
        """取引をキャンセルする
        
        Args:
            command: 取引キャンセルコマンド
            
        Returns:
            CancelTradeResultDto: キャンセル結果
        """
        try:
            # 1. 取引オファーを取得
            trade_offer = self._trade_repository.find_by_id(command.trade_id)
            if not trade_offer:
                return CancelTradeResultDto(
                    success=False,
                    trade_id=command.trade_id,
                    player_id=command.player_id,
                    message="取引キャンセルに失敗しました",
                    error_message=f"取引が見つかりません: {command.trade_id}"
                )
            
            # 2. プレイヤーを取得
            player = self._player_repository.find_by_id(command.player_id)
            if not player:
                return CancelTradeResultDto(
                    success=False,
                    trade_id=command.trade_id,
                    player_id=command.player_id,
                    message="取引キャンセルに失敗しました",
                    error_message=f"プレイヤーが見つかりません: {command.player_id}"
                )
            
            # 3. ドメインサービスでキャンセル実行
            self._trade_service.cancel_trade(trade_offer, player)
            
            # 4. 取引を保存
            self._trade_repository.save(trade_offer)
            
            # 5. ドメインイベントをディスパッチ
            if self._event_dispatcher:
                events = trade_offer.get_events()
                self._event_dispatcher.dispatch_all_events(events)
                trade_offer.clear_events()
            
            return CancelTradeResultDto(
                success=True,
                trade_id=command.trade_id,
                player_id=command.player_id,
                message=f"取引をキャンセルしました (ID: {command.trade_id})"
            )
            
        except (InvalidTradeStatusException, CannotCancelTradeWithOtherPlayerException) as e:
            return CancelTradeResultDto(
                success=False,
                trade_id=command.trade_id,
                player_id=command.player_id,
                message="取引キャンセルに失敗しました",
                error_message=str(e)
            )
    
    def get_player_trades(self, command: GetPlayerTradesCommand) -> Optional[PlayerTradesDto]:
        """プレイヤーの取引一覧を取得
        
        Args:
            command: プレイヤー取引取得コマンド
            
        Returns:
            PlayerTradesDto: プレイヤーの取引一覧
        """
        # 1. プレイヤーを取得
        player = self._player_repository.find_by_id(command.player_id)
        if not player:
            return None
        
        # 2. プレイヤー関連の取引を取得
        seller_trades = self._trade_repository.find_by_seller_id(command.player_id)
        buyer_trades = self._trade_repository.find_by_buyer_id(command.player_id)
        target_trades = self._trade_repository.find_by_target_player_id(command.player_id)
        
        # 3. 全ての取引を統合
        all_trades = seller_trades + buyer_trades + target_trades
        
        # 4. ステータス別に分類
        active_trades = [t for t in all_trades if t.status.value == "active"]
        completed_trades = [t for t in all_trades if t.status.value == "completed"]
        cancelled_trades = [t for t in all_trades if t.status.value == "cancelled"]
        
        # 5. DTOに変換
        return PlayerTradesDto(
            player_id=player.player_id,
            player_name=player.name,
            active_trades=[self._convert_to_trade_offer_dto(t) for t in active_trades],
            completed_trades=[self._convert_to_trade_offer_dto(t) for t in completed_trades],
            cancelled_trades=[self._convert_to_trade_offer_dto(t) for t in cancelled_trades],
            total_trades=len(all_trades)
        )
    
    def get_global_trades(self, command: GetGlobalTradesCommand) -> GlobalTradesDto:
        """グローバル取引一覧を取得
        
        Args:
            command: グローバル取引取得コマンド
            
        Returns:
            GlobalTradesDto: グローバル取引一覧
        """
        # 1. 基本のグローバル取引を取得
        trades = self._trade_repository.find_global_trades()
        
        # 2. フィルター適用
        filtered_trades = trades
        
        if command.item_id:
            filtered_trades = [t for t in filtered_trades if t.offered_item.item_id == command.item_id]
        
        if command.min_price is not None:
            filtered_trades = [t for t in filtered_trades if t.requested_gold >= command.min_price]
        
        if command.max_price is not None:
            filtered_trades = [t for t in filtered_trades if t.requested_gold <= command.max_price]
        
        # 3. 最新順にソートして制限
        filtered_trades.sort(key=lambda t: t.created_at, reverse=True)
        filtered_trades = filtered_trades[:command.limit]
        
        # 4. フィルター情報を記録
        applied_filters = {
            "item_id": command.item_id,
            "min_price": command.min_price,
            "max_price": command.max_price,
            "limit": command.limit
        }
        
        return GlobalTradesDto(
            trades=[self._convert_to_trade_offer_dto(t) for t in filtered_trades],
            total_count=len(trades),
            filtered_count=len(filtered_trades),
            applied_filters=applied_filters
        )
    
    # ===== プライベートメソッド =====
    
    def _get_target_player_name(self, target_player_id: int) -> str:
        """対象プレイヤーの名前を取得"""
        if target_player_id:
            target_player = self._player_repository.find_by_id(target_player_id)
            return target_player.name if target_player else f"Player{target_player_id}"
        return None
    
    def _convert_to_trade_item_dto(self, trade_item: TradeItem) -> TradeItemDto:
        """TradeItemをTradeItemDtoに変換"""
        return TradeItemDto(
            item_id=trade_item.item_id,
            count=trade_item.count,
            unique_id=trade_item.unique_id
        )
    
    def _convert_to_trade_offer_dto(self, trade_offer: TradeOffer) -> TradeOfferDto:
        """TradeOfferをTradeOfferDtoに変換"""
        # プレイヤー名を取得
        seller = self._player_repository.find_by_id(trade_offer.seller_id)
        seller_name = seller.name if seller else f"Player{trade_offer.seller_id}"
        
        buyer_name = None
        if trade_offer.buyer_id:
            buyer = self._player_repository.find_by_id(trade_offer.buyer_id)
            buyer_name = buyer.name if buyer else f"Player{trade_offer.buyer_id}"
        
        target_player_name = None
        if trade_offer.target_player_id:
            target_player = self._player_repository.find_by_id(trade_offer.target_player_id)
            target_player_name = target_player.name if target_player else f"Player{trade_offer.target_player_id}"
        
        return TradeOfferDto(
            trade_id=trade_offer.trade_id,
            seller_id=trade_offer.seller_id,
            seller_name=seller_name,
            offered_item=self._convert_to_trade_item_dto(trade_offer.offered_item),
            requested_gold=trade_offer.requested_gold,
            trade_type=trade_offer.trade_type,
            target_player_id=trade_offer.target_player_id,
            target_player_name=target_player_name,
            status=trade_offer.status,
            buyer_id=trade_offer.buyer_id,
            buyer_name=buyer_name,
            created_at=trade_offer.created_at,
            completed_at=None  # 現在のドメインモデルにはcompleted_atがない
        )
