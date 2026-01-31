from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.enum.trade_enum import TradeType
from ai_rpg_world.domain.trade.exception.trade_exception import TradeScopeValidationException


@dataclass(frozen=True)
class TradeScope:
    """取引の範囲を表す値オブジェクト

    取引の種類（グローバル/ダイレクト）と対象プレイヤーを表現します。
    """
    trade_type: TradeType
    target_player_id: Optional[PlayerId]

    def __post_init__(self):
        """バリデーションは__post_init__で実行"""
        if self.trade_type == TradeType.DIRECT and self.target_player_id is None:
            raise TradeScopeValidationException("ダイレクト取引の場合はtarget_player_idが必要です")
        if self.trade_type != TradeType.DIRECT and self.target_player_id is not None:
            raise TradeScopeValidationException("グローバル取引の場合はtarget_player_idはNoneである必要があります")

    @classmethod
    def global_trade(cls) -> "TradeScope":
        """グローバル取引を作成"""
        return cls(trade_type=TradeType.GLOBAL, target_player_id=None)

    @classmethod
    def direct_trade(cls, target_player_id: PlayerId) -> "TradeScope":
        """ダイレクト取引を作成"""
        return cls(trade_type=TradeType.DIRECT, target_player_id=target_player_id)

    def is_global(self) -> bool:
        """グローバル取引かどうか"""
        return self.trade_type == TradeType.GLOBAL

    def is_direct(self) -> bool:
        """ダイレクト取引かどうか"""
        return self.trade_type == TradeType.DIRECT

    def __str__(self) -> str:
        """文字列表現"""
        if self.is_global():
            return "グローバル取引"
        else:
            return f"ダイレクト取引(対象: {self.target_player_id})"

    def __repr__(self) -> str:
        """文字列表現"""
        return f"TradeScope(trade_type={self.trade_type.value}, target_player_id={self.target_player_id})"
