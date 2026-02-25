"""ショップクエリ関連の例外"""
from typing import Optional

from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.application.shop.exceptions.base_exception import ShopApplicationException


class ShopQueryApplicationException(ShopApplicationException):
    """ショップクエリ用アプリケーション例外"""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        shop_id: Optional[int] = None,
        spot_id: Optional[int] = None,
        location_area_id: Optional[int] = None,
        cause: Optional[Exception] = None,
        **context,
    ):
        all_context = dict(context)
        if shop_id is not None:
            all_context["shop_id"] = shop_id
        if spot_id is not None:
            all_context["spot_id"] = spot_id
        if location_area_id is not None:
            all_context["location_area_id"] = location_area_id
        if cause is not None:
            all_context["cause"] = cause
        super().__init__(message, error_code=error_code or "SHOP_QUERY", **all_context)

    @classmethod
    def from_domain_error(cls, e: DomainException) -> "ShopQueryApplicationException":
        """ドメイン例外から変換"""
        return cls(
            f"Domain error in ShopQuery usecase: {e.error_code}",
            error_code="SHOP_QUERY_DOMAIN",
            cause=e,
        )

    @property
    def cause(self) -> Optional[Exception]:
        """原因となった例外"""
        return self.context.get("cause")

    @classmethod
    def shop_not_found(cls, shop_id: int) -> "ShopQueryApplicationException":
        """ショップが見つからない場合の例外"""
        return cls(
            f"Shop not found: {shop_id}",
            error_code="SHOP_NOT_FOUND",
            shop_id=shop_id,
        )

    @classmethod
    def shop_not_found_at_location(
        cls, spot_id: int, location_area_id: int
    ) -> "ShopQueryApplicationException":
        """指定ロケーションにショップが存在しない場合の例外"""
        return cls(
            f"No shop at location (spot_id={spot_id}, location_area_id={location_area_id})",
            error_code="SHOP_NOT_FOUND_AT_LOCATION",
            spot_id=spot_id,
            location_area_id=location_area_id,
        )
