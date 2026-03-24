from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.trade.read_model.trade_read_model import TradeReadModel
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_search_filter import TradeSearchFilter
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


@dataclass(frozen=True)
class TradeCursor:
    """取引ページング用のカーソル構造体

    ドメイン層でのカーソル表現。アプリケーション層でのエンコード/デコードは
    別途TradeCursorCodecで行う。
    """
    created_at: datetime
    trade_id: int


class TradeReadModelRepository(Repository[TradeReadModel, TradeId]):
    """取引ReadModelリポジトリインターフェース"""


    @abstractmethod
    def find_recent_trades(self, limit: int = 10, cursor: Optional[TradeCursor] = None) -> Tuple[List[TradeReadModel], Optional[TradeCursor]]:
        """最新の取引を取得（カーソルベースページング）

        Args:
            limit: 取得する最大件数
            cursor: ページングカーソル（Noneの場合は最初のページ）

        Returns:
            (取引リスト, 次のページのカーソル)
        """
        pass

    @abstractmethod
    def find_trades_for_player(self, player_id: PlayerId, limit: int = 10, cursor: Optional[TradeCursor] = None) -> Tuple[List[TradeReadModel], Optional[TradeCursor]]:
        """プレイヤー宛の取引を取得（カーソルベースページング）

        Args:
            player_id: プレイヤーID
            limit: 取得する最大件数
            cursor: ページングカーソル（Noneの場合は最初のページ）

        Returns:
            (取引リスト, 次のページのカーソル)
        """
        pass

    @abstractmethod
    def find_active_trades_as_seller(
        self,
        seller_id: PlayerId,
        limit: int = 10,
        cursor: Optional[TradeCursor] = None,
    ) -> Tuple[List[TradeReadModel], Optional[TradeCursor]]:
        """出品者の ACTIVE 取引のみを取得（カーソルベースページング）

        `my_trades.selling` 専用。`seller_id` が一致しステータスが ACTIVE のみを対象とし、
        並びは `created_at` 降順、`trade_id` を tie-break とする。`next_cursor` は
        このストリーム上の次ページ位置を指す。

        Args:
            seller_id: 出品者プレイヤーID
            limit: 取得する最大件数
            cursor: ページングカーソル（Noneの場合は最初のページ）

        Returns:
            (取引リスト, 次のページのカーソル)
        """
        pass

    @abstractmethod
    def find_active_trades(self, limit: int = 50, cursor: Optional[TradeCursor] = None) -> Tuple[List[TradeReadModel], Optional[TradeCursor]]:
        """アクティブな取引を取得（カーソルベースページング）

        Args:
            limit: 取得する最大件数
            cursor: ページングカーソル（Noneの場合は最初のページ）

        Returns:
            (取引リスト, 次のページのカーソル)
        """
        pass

    @abstractmethod
    def search_trades(self, filter: TradeSearchFilter, limit: int = 20, cursor: Optional[TradeCursor] = None) -> Tuple[List[TradeReadModel], Optional[TradeCursor]]:
        """フィルタ条件で取引を検索（カーソルベースページング）

        Args:
            filter: 検索フィルタ条件
            limit: 取得する最大件数
            cursor: ページングカーソル（Noneの場合は最初のページ）

        Returns:
            (取引リスト, 次のページのカーソル)
        """
        pass
