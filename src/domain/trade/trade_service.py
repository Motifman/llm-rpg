from src.domain.trade.trade import TradeOffer
from src.domain.player.player import Player
from domain.trade.trade_exception import (
    InsufficientItemsException,
    InsufficientGoldException,
)

class TradeService:
    def __init__(self):
        pass
    
    def execute_trade(self, trade_offer: TradeOffer, buyer: Player, seller: Player) -> bool:
        """
        取引を実行する
        取引オファー自体はバリデーション済み
        プレイヤーの所持品、取引内容と合致したプレイヤーかのバリデーションを行う
        """
        # まず外部整合性（Playerの状態）をチェック
        if not seller.can_offer_item(trade_offer.offered_item):
            raise InsufficientItemsException("売り手はアイテムを所有していません。")
        if not buyer.can_pay_gold(trade_offer.requested_gold):
            raise InsufficientGoldException("買い手は所持金が足りません。")

        # すべてのチェックが通ったら、TradeOfferの内部整合性チェックと状態変更
        trade_offer.accept_by(buyer.player_id)  # 例外が発生する可能性がある
        
        # アイテムと所持金の移動
        seller.transfer_item_to(buyer, trade_offer.offered_item)
        buyer.transfer_gold_to(seller, trade_offer.requested_gold)
        
        return True
    
    def cancel_trade(self, trade_offer: TradeOffer, player: Player):
        trade_offer.cancel_by(player.player_id)