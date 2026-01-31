from abc import abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.trade.read_model.personal_trade_listing_read_model import PersonalTradeListingReadModel
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.repository.cursor import ListingCursor


class PersonalTradeListingReadModelRepository(Repository[PersonalTradeListingReadModel, TradeId]):
    """個人取引ReadModelリポジトリインターフェース"""

    @abstractmethod
    def find_for_player(
        self,
        player_id: PlayerId,
        limit: int = 20,
        cursor: Optional[ListingCursor] = None
    ) -> Tuple[List[PersonalTradeListingReadModel], Optional[ListingCursor]]:
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
    def count_for_player(self, player_id: PlayerId) -> int:
        """プレイヤー宛の取引数をカウント

        Args:
            player_id: プレイヤーID

        Returns:
            取引数
        """
        pass
