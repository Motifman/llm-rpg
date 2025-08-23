from src.domain.trade.trade import TradeOffer
from src.domain.player.player import Player


class TradeService:
    def execute_trade(self, trade_offer: TradeOffer, buyer: Player, seller: Player):
        """
        取引を実行する
        取引オファー自体はバリデーション済み
        プレイヤーの所持品、取引内容と合致したプレイヤーかのバリデーションを行う
        """
        # すべてのチェックが通ったら、TradeOfferの内部整合性チェックと状態変更
        trade_offer.accept_by(buyer._player_id, buyer.name, seller.name)  # 例外が発生する可能性がある
        
        # アイテムと所持金の移動
        buyer.pay_gold_for_trade(trade_offer.requested_gold)
        seller.receive_gold_for_trade(trade_offer.requested_gold)
        item_released = seller.release_item_for_trade(trade_offer.offered_item)
        buyer.receive_item_for_trade(item_released)
    
    def cancel_trade(self, trade_offer: TradeOffer, player: Player):
        trade_offer.cancel_by(player._player_id, player.name)