"""ショップクエリ関連の例外"""

from typing import Any

from ai_rpg_world.application.shop.exceptions.base_exception import ShopApplicationException
from ai_rpg_world.domain.common.exception import DomainException


class ShopQueryApplicationException(ShopApplicationException):
    """ショップクエリ用アプリケーション例外"""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        shop_id: int | None = None,
        spot_id: int | None = None,
        location_area_id: int | None = None,
        cause: Exception | None = None,
        **context: Any,
    ) -> None:
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
    def cause(self) -> Exception | None:
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
    def shop_not_found_at_location(cls, spot_id: int, location_area_id: int) -> "ShopQueryApplicationException":
        """指定ロケーションにショップが存在しない場合の例外"""
        return cls(
            f"No shop at location (spot_id={spot_id}, location_area_id={location_area_id})",
            error_code="SHOP_NOT_FOUND_AT_LOCATION",
            spot_id=spot_id,
            location_area_id=location_area_id,
        )
