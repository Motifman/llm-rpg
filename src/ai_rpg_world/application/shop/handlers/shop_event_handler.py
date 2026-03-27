"""ショップイベントハンドラ"""
import logging
from typing import TYPE_CHECKING, Callable, Any

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.domain.shop.event.shop_event import (
    ShopCreatedEvent,
    ShopItemListedEvent,
    ShopItemUnlistedEvent,
    ShopItemPurchasedEvent,
)
from ai_rpg_world.domain.shop.read_model.shop_summary_read_model import ShopSummaryReadModel
from ai_rpg_world.domain.shop.read_model.shop_listing_read_model import ShopListingReadModel
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId

if TYPE_CHECKING:
    from ai_rpg_world.domain.shop.repository.shop_summary_read_model_repository import (
        ShopSummaryReadModelRepository,
    )
    from ai_rpg_world.domain.shop.repository.shop_listing_read_model_repository import (
        ShopListingReadModelRepository,
    )


class ShopEventHandler:
    """ショップイベントハンドラ

    ドメインイベントを購読し、ReadModelを更新する。
    投影用スナップショットはイベントペイロードに含まれる前提とし、
    集約・Item リポジトリへは読みにいかない。
    """

    def __init__(
        self,
        shop_summary_read_model_repository: "ShopSummaryReadModelRepository",
        shop_listing_read_model_repository: "ShopListingReadModelRepository",
        unit_of_work_factory: UnitOfWorkFactory,
    ):
        self._shop_summary_read_model_repository = shop_summary_read_model_repository
        self._shop_listing_read_model_repository = shop_listing_read_model_repository
        self._unit_of_work_factory = unit_of_work_factory
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_in_separate_transaction(
        self, operation: Callable[[], Any], context: dict
    ) -> None:
        """別トランザクションで操作を実行。ApplicationException/DomainException は再送出、その他は SystemErrorException でラップして送出する。"""
        unit_of_work = self._unit_of_work_factory.create()
        try:
            with unit_of_work:
                operation()
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception(
                "Failed to handle event in %s: %s",
                context.get("handler", "unknown"),
                e,
                extra=context,
            )
            raise SystemErrorException(
                f"Shop event handling failed in {context.get('handler', 'unknown')}: {e}",
                original_exception=e,
            ) from e

    def handle_shop_created(self, event: ShopCreatedEvent) -> None:
        """ショップ開設イベントのハンドリング"""
        def operation():
            read_model = ShopSummaryReadModel.create(
                shop_id=event.aggregate_id,
                spot_id=event.spot_id,
                location_area_id=event.location_area_id,
                name=event.name,
                description=event.description,
                owner_ids=list(event.owner_ids),
                listing_count=0,
                created_at=event.occurred_at,
            )
            self._shop_summary_read_model_repository.save(read_model)
            self._logger.info(
                "ReadModel updated for shop created: %s", event.aggregate_id.value
            )

        self._execute_in_separate_transaction(operation, {
            "handler": "handle_shop_created",
            "shop_id": event.aggregate_id.value,
        })

    def handle_shop_item_listed(self, event: ShopItemListedEvent) -> None:
        """ショップ出品イベントのハンドリング"""
        def operation():
            p = event.listing_projection
            listing_read_model = ShopListingReadModel.create(
                shop_id=event.aggregate_id,
                listing_id=event.listing_id,
                item_instance_id=event.item_instance_id,
                item_name=p.item_name,
                item_spec_id=p.item_spec_id,
                price_per_unit=event.price_per_unit.value,
                quantity=p.quantity,
                listed_by=event.listed_by,
                listed_at=event.occurred_at,
            )
            self._shop_listing_read_model_repository.save(listing_read_model)

            summary = self._shop_summary_read_model_repository.find_by_id(
                event.aggregate_id
            )
            if summary:
                summary.listing_count += 1
                self._shop_summary_read_model_repository.save(summary)

            self._logger.info(
                "ReadModel updated for shop item listed: shop=%s listing=%s",
                event.aggregate_id.value,
                event.listing_id.value,
            )

        self._execute_in_separate_transaction(operation, {
            "handler": "handle_shop_item_listed",
            "shop_id": event.aggregate_id.value,
            "listing_id": event.listing_id.value,
        })

    def handle_shop_item_unlisted(self, event: ShopItemUnlistedEvent) -> None:
        """ショップ取り下げイベントのハンドリング"""
        def operation():
            self._shop_listing_read_model_repository.delete(event.listing_id)

            summary = self._shop_summary_read_model_repository.find_by_id(
                event.aggregate_id
            )
            if summary and summary.listing_count > 0:
                summary.listing_count -= 1
                self._shop_summary_read_model_repository.save(summary)

            self._logger.info(
                "ReadModel updated for shop item unlisted: shop=%s listing=%s",
                event.aggregate_id.value,
                event.listing_id.value,
            )

        self._execute_in_separate_transaction(operation, {
            "handler": "handle_shop_item_unlisted",
            "shop_id": event.aggregate_id.value,
            "listing_id": event.listing_id.value,
        })

    def handle_shop_item_purchased(self, event: ShopItemPurchasedEvent) -> None:
        """ショップ購入イベントのハンドリング"""
        def operation():
            listing_rm = self._shop_listing_read_model_repository.find_by_id(
                event.listing_id
            )
            if not listing_rm:
                self._logger.warning(
                    "Listing ReadModel not found for purchase update: listing=%s",
                    event.listing_id.value,
                )
                return

            new_quantity = listing_rm.quantity - event.quantity
            if new_quantity <= 0:
                self._shop_listing_read_model_repository.delete(event.listing_id)
                summary = self._shop_summary_read_model_repository.find_by_id(
                    event.aggregate_id
                )
                if summary and summary.listing_count > 0:
                    summary.listing_count -= 1
                    self._shop_summary_read_model_repository.save(summary)
            else:
                listing_rm.quantity = new_quantity
                self._shop_listing_read_model_repository.save(listing_rm)

            self._logger.info(
                "ReadModel updated for shop item purchased: shop=%s listing=%s qty=%s",
                event.aggregate_id.value,
                event.listing_id.value,
                event.quantity,
            )

        self._execute_in_separate_transaction(operation, {
            "handler": "handle_shop_item_purchased",
            "shop_id": event.aggregate_id.value,
            "listing_id": event.listing_id.value,
        })
