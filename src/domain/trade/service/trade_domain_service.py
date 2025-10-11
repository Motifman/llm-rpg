from src.domain.trade.aggregate.trade_aggregate import Trade
from src.domain.player.player import Player


class TradeDomainService:
    def execute_trade(self, trade: Trade, buyer: Player, seller: Player):
        """
        取引を実行する
        取引オファー自体はバリデーション済み
        プレイヤーの所持品、取引内容と合致したプレイヤーかのバリデーションを行う
        """
        # すべてのチェックが通ったら、Tradeの内部整合性チェックと状態変更
        trade.accept_by(buyer._player_id, buyer.name, seller.name)  # 例外が発生する可能性がある

        # アイテムと所持金の移動
        buyer.pay_gold_for_trade(trade.requested_gold)
        seller.receive_gold_for_trade(trade.requested_gold)
        item_released = seller.release_item_for_trade(trade.offered_item)
        buyer.receive_item_for_trade(item_released)

    def cancel_trade(self, trade: Trade, player: Player):
        trade.cancel_by(player._player_id, player.name)