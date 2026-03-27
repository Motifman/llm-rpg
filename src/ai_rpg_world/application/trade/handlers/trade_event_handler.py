import logging
from typing import TYPE_CHECKING, Callable, Any

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.domain.trade.event.trade_event import (
    TradeOfferedEvent,
    TradeAcceptedEvent,
    TradeCancelledEvent,
    TradeDeclinedEvent,
)
from ai_rpg_world.domain.trade.read_model.trade_read_model import TradeReadModel
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus

if TYPE_CHECKING:
    from ai_rpg_world.domain.trade.repository.trade_read_model_repository import TradeReadModelRepository


class TradeEventHandler:
    """取引イベントハンドラ

    ドメインイベントを購読し、ReadModelを更新する。
    投影に必要な表示情報はイベントペイロードに含まれる前提とし、
    プロフィール・アイテムリポジトリへは読みにいかない。
    """

    def __init__(
        self,
        trade_read_model_repository: "TradeReadModelRepository",
        unit_of_work_factory: UnitOfWorkFactory,
    ):
        self._trade_read_model_repository = trade_read_model_repository
        self._unit_of_work_factory = unit_of_work_factory
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_in_separate_transaction(self, operation: Callable[[], Any], context: dict) -> None:
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
                f"Trade event handling failed in {context.get('handler', 'unknown')}: {e}",
                original_exception=e,
            ) from e

    def _read_model_from_offered_event(self, event: TradeOfferedEvent) -> TradeReadModel:
        p = event.listing_projection
        return TradeReadModel.create_from_trade_and_item(
            trade_id=event.aggregate_id,
            seller_id=event.seller_id,
            seller_name=p.seller_display_name,
            buyer_id=None,
            buyer_name=None,
            item_instance_id=event.offered_item_id,
            item_name=p.item_name,
            item_quantity=p.item_quantity,
            item_type=p.item_type,
            item_rarity=p.item_rarity,
            item_description=p.item_description,
            item_equipment_type=p.item_equipment_type,
            durability_current=p.durability_current,
            durability_max=p.durability_max,
            requested_gold=event.requested_gold,
            status=TradeStatus.ACTIVE,
            created_at=event.trade_created_at,
        )

    def _read_model_from_accepted_event(self, event: TradeAcceptedEvent) -> TradeReadModel:
        p = event.listing_projection
        return TradeReadModel.create_from_trade_and_item(
            trade_id=event.aggregate_id,
            seller_id=event.seller_id,
            seller_name=p.seller_display_name,
            buyer_id=event.buyer_id,
            buyer_name=event.buyer_display_name,
            item_instance_id=event.offered_item_id,
            item_name=p.item_name,
            item_quantity=p.item_quantity,
            item_type=p.item_type,
            item_rarity=p.item_rarity,
            item_description=p.item_description,
            item_equipment_type=p.item_equipment_type,
            durability_current=p.durability_current,
            durability_max=p.durability_max,
            requested_gold=event.requested_gold,
            status=TradeStatus.COMPLETED,
            created_at=event.trade_created_at,
        )

    def handle_trade_offered(self, event: TradeOfferedEvent) -> None:
        """取引出品イベントのハンドリング"""

        def operation():
            read_model = self._read_model_from_offered_event(event)
            self._trade_read_model_repository.save(read_model)
            self._logger.info(f"ReadModel updated for trade offered: {event.aggregate_id.value}")

        self._execute_in_separate_transaction(
            operation,
            {"handler": "handle_trade_offered", "trade_id": event.aggregate_id.value},
        )

    def handle_trade_accepted(self, event: TradeAcceptedEvent) -> None:
        """取引受諾イベントのハンドリング"""

        def operation():
            read_model = self._trade_read_model_repository.find_by_id(event.aggregate_id)
            if not read_model:
                read_model = self._read_model_from_accepted_event(event)
                self._trade_read_model_repository.save(read_model)
                self._logger.info(
                    "ReadModel created from TradeAcceptedEvent (Offered 投影が無かった取引): %s",
                    event.aggregate_id.value,
                )
                return

            read_model.buyer_id = event.buyer_id.value
            read_model.buyer_name = event.buyer_display_name
            read_model.status = TradeStatus.COMPLETED.name
            self._trade_read_model_repository.save(read_model)
            self._logger.info(f"ReadModel updated for trade accepted: {event.aggregate_id.value}")

        self._execute_in_separate_transaction(
            operation,
            {
                "handler": "handle_trade_accepted",
                "trade_id": event.aggregate_id.value,
                "buyer_id": event.buyer_id.value,
            },
        )

    def handle_trade_cancelled(self, event: TradeCancelledEvent) -> None:
        """取引キャンセルイベントのハンドリング"""

        def operation():
            read_model = self._trade_read_model_repository.find_by_id(event.aggregate_id)
            if not read_model:
                self._logger.warning(f"ReadModel not found for trade: {event.aggregate_id.value}")
                return

            read_model.status = TradeStatus.CANCELLED.name
            self._trade_read_model_repository.save(read_model)
            self._logger.info(f"ReadModel updated for trade cancelled: {event.aggregate_id.value}")

        self._execute_in_separate_transaction(
            operation,
            {"handler": "handle_trade_cancelled", "trade_id": event.aggregate_id.value},
        )

    def handle_trade_declined(self, event: TradeDeclinedEvent) -> None:
        """取引拒否イベントのハンドリング"""

        def operation():
            read_model = self._trade_read_model_repository.find_by_id(event.aggregate_id)
            if not read_model:
                self._logger.warning(f"ReadModel not found for trade: {event.aggregate_id.value}")
                return

            read_model.status = TradeStatus.CANCELLED.name
            self._trade_read_model_repository.save(read_model)
            self._logger.info(f"ReadModel updated for trade declined: {event.aggregate_id.value}")

        self._execute_in_separate_transaction(
            operation,
            {"handler": "handle_trade_declined", "trade_id": event.aggregate_id.value},
        )
