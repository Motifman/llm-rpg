from abc import abstractmethod
from typing import Optional
from datetime import date

from src.domain.common.repository import Repository
from src.domain.trade.read_model.market_overview_read_model import MarketOverviewReadModel


class MarketOverviewReadModelRepository(Repository[MarketOverviewReadModel, date]):
    """市場全体概要ReadModelリポジトリインターフェース"""

    @abstractmethod
    def find_latest(self) -> Optional[MarketOverviewReadModel]:
        """最新の市場概要を取得

        Returns:
            最新の市場概要データ（存在しない場合はNone）
        """
        pass
