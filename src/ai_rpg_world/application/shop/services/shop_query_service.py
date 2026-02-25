"""ショップクエリサービス"""
import logging
from typing import List, Optional

from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId

from ai_rpg_world.domain.shop.repository.shop_summary_read_model_repository import (
    ShopSummaryReadModelRepository,
)
from ai_rpg_world.domain.shop.repository.shop_listing_read_model_repository import (
    ShopListingReadModelRepository,
)
from ai_rpg_world.application.shop.contracts.dtos import (
    ShopSummaryDto,
    ShopListingDto,
    ShopDetailDto,
)
from ai_rpg_world.application.shop.exceptions.query_exception import (
    ShopQueryApplicationException,
)
from ai_rpg_world.application.common.exceptions import SystemErrorException


class ShopQueryService:
    """ショップクエリサービス

    ReadModelのみを参照し、ショップ一覧・詳細・出品リストを返す。
    """

    def __init__(
        self,
        shop_summary_read_model_repository: ShopSummaryReadModelRepository,
        shop_listing_read_model_repository: ShopListingReadModelRepository,
    ):
        self._shop_summary_repository = shop_summary_read_model_repository
        self._shop_listing_repository = shop_listing_read_model_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(self, operation, context: dict):
        """共通の例外処理を実行"""
        try:
            return operation()
        except ShopQueryApplicationException:
            raise
        except DomainException as e:
            raise ShopQueryApplicationException.from_domain_error(e)
        except Exception as e:
            self._logger.error(
                "Unexpected error in %s: %s",
                context.get("action", "unknown"),
                str(e),
                extra={"error_details": context},
            )
            raise SystemErrorException(
                f"{context.get('action', 'unknown')} failed: {str(e)}",
                original_exception=e,
            )

    def get_shops_at_location(
        self, spot_id: int, location_area_id: int
    ) -> List[ShopSummaryDto]:
        """指定ロケーションのショップ一覧を取得する（通常は0件または1件）"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_shops_at_location_impl(spot_id, location_area_id),
            context={
                "action": "get_shops_at_location",
                "spot_id": spot_id,
                "location_area_id": location_area_id,
            },
        )

    def _get_shops_at_location_impl(
        self, spot_id: int, location_area_id: int
    ) -> List[ShopSummaryDto]:
        shop = self._shop_summary_repository.find_by_spot_and_location(
            SpotId(spot_id), LocationAreaId(location_area_id)
        )
        if not shop:
            return []
        return [self._summary_to_dto(shop)]

    def get_shop_detail(self, shop_id: int) -> ShopDetailDto:
        """ショップ詳細（サマリ＋出品一覧）を取得する"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_shop_detail_impl(shop_id),
            context={"action": "get_shop_detail", "shop_id": shop_id},
        )

    def _get_shop_detail_impl(self, shop_id: int) -> ShopDetailDto:
        summary_rm = self._shop_summary_repository.find_by_id(ShopId(shop_id))
        if not summary_rm:
            raise ShopQueryApplicationException.shop_not_found(shop_id)
        listings = self._shop_listing_repository.find_by_shop_id(ShopId(shop_id))
        return ShopDetailDto(
            summary=self._summary_to_dto(summary_rm),
            listings=[self._listing_to_dto(rm) for rm in listings],
        )

    def get_shop_summary(self, shop_id: int) -> ShopSummaryDto:
        """ショップサマリを取得する"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_shop_summary_impl(shop_id),
            context={"action": "get_shop_summary", "shop_id": shop_id},
        )

    def _get_shop_summary_impl(self, shop_id: int) -> ShopSummaryDto:
        summary_rm = self._shop_summary_repository.find_by_id(ShopId(shop_id))
        if not summary_rm:
            raise ShopQueryApplicationException.shop_not_found(shop_id)
        return self._summary_to_dto(summary_rm)

    def get_listings_for_shop(self, shop_id: int) -> List[ShopListingDto]:
        """ショップの出品一覧を取得する"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_listings_for_shop_impl(shop_id),
            context={"action": "get_listings_for_shop", "shop_id": shop_id},
        )

    def _get_listings_for_shop_impl(self, shop_id: int) -> List[ShopListingDto]:
        listings = self._shop_listing_repository.find_by_shop_id(ShopId(shop_id))
        return [self._listing_to_dto(rm) for rm in listings]

    def _summary_to_dto(self, rm) -> ShopSummaryDto:
        return ShopSummaryDto(
            shop_id=rm.shop_id,
            spot_id=rm.spot_id,
            location_area_id=rm.location_area_id,
            name=rm.name,
            description=rm.description,
            owner_ids=list(rm.owner_ids),
            listing_count=rm.listing_count,
            created_at=rm.created_at,
        )

    def _listing_to_dto(self, rm) -> ShopListingDto:
        return ShopListingDto(
            shop_id=rm.shop_id,
            listing_id=rm.listing_id,
            item_instance_id=rm.item_instance_id,
            item_name=rm.item_name,
            item_spec_id=rm.item_spec_id,
            price_per_unit=rm.price_per_unit,
            quantity=rm.quantity,
            listed_by=rm.listed_by,
            listed_at=rm.listed_at,
        )
