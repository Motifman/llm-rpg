from abc import abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from src.domain.common.repository import Repository
from src.domain.trade.read_model.personal_trade_listing_read_model import PersonalTradeListingReadModel
from src.domain.trade.value_object.trade_id import TradeId
from src.domain.player.value_object.player_id import PlayerId


@dataclass(frozen=True)
class PersonalTradePageSpec:
    """個人取引ページング仕様"""
    limit: int
    offset: Optional[int] = None


class PersonalTradeListingReadModelRepository(Repository[PersonalTradeListingReadModel, TradeId]):
    """個人取引ReadModelリポジトリインターフェース"""

    @abstractmethod
    def find_for_player(
        self,
        player_id: PlayerId,
        page_spec: PersonalTradePageSpec
    ) -> tuple[List[PersonalTradeListingReadModel], bool]:
        """プレイヤー宛の取引を取得（ページング）

        Args:
            player_id: プレイヤーID
            page_spec: ページング仕様

        Returns:
            (取引リスト, 次のページが存在するか)
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
