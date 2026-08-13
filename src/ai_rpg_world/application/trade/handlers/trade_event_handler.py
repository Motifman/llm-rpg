"""取引イベントを冪等にread modelへ投影するhandler。"""

from __future__ import annotations

from dataclasses import replace
import logging
from typing import Callable

from ai_rpg_world.application.common.exceptions import (
    ApplicationException,
    SystemErrorException,
)
from ai_rpg_world.application.trade.handlers.trade_projection_executor import (
    TradeProjectionExecutorPort,
)
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus
from ai_rpg_world.domain.trade.event.trade_event import (
    TradeAcceptedEvent,
    TradeCancelledEvent,
    TradeDeclinedEvent,
    TradeOfferedEvent,
)
from ai_rpg_world.domain.trade.read_model.trade_read_model import TradeReadModel
from ai_rpg_world.domain.trade.repository.trade_read_model_repository import (
    TradeReadModelRepository,
)


class TradeEventHandler:
    """取引イベントをconsumer inboxと同じ原子性境界で投影する。"""

    OFFERED_CONSUMER_ID = "trade_read_model.offered.v1"
    ACCEPTED_CONSUMER_ID = "trade_read_model.accepted.v1"
    CANCELLED_CONSUMER_ID = "trade_read_model.cancelled.v1"
    DECLINED_CONSUMER_ID = "trade_read_model.declined.v1"

    def __init__(self, projection_executor: TradeProjectionExecutorPort) -> None:
        self._projection_executor = projection_executor
        self._logger = logging.getLogger(self.__class__.__name__)

    @staticmethod
    def _read_model_from_offered_event(event: TradeOfferedEvent) -> TradeReadModel:
        projection = event.listing_projection
        return TradeReadModel.create_from_trade_and_item(
            trade_id=event.aggregate_id,
            seller_id=event.seller_id,
            seller_name=projection.seller_display_name,
            buyer_id=None,
            buyer_name=None,
            item_instance_id=event.offered_item_id,
            item_name=projection.item_name,
            item_quantity=projection.item_quantity,
            item_type=projection.item_type,
            item_rarity=projection.item_rarity,
            item_description=projection.item_description,
            item_equipment_type=projection.item_equipment_type,
            durability_current=projection.durability_current,
            durability_max=projection.durability_max,
            requested_gold=event.requested_gold,
            status=TradeStatus.ACTIVE,
            created_at=event.trade_created_at,
        )

    @staticmethod
    def _read_model_from_accepted_event(event: TradeAcceptedEvent) -> TradeReadModel:
        projection = event.listing_projection
        return TradeReadModel.create_from_trade_and_item(
            trade_id=event.aggregate_id,
            seller_id=event.seller_id,
            seller_name=projection.seller_display_name,
            buyer_id=event.buyer_id,
            buyer_name=event.buyer_display_name,
            item_instance_id=event.offered_item_id,
            item_name=projection.item_name,
            item_quantity=projection.item_quantity,
            item_type=projection.item_type,
            item_rarity=projection.item_rarity,
            item_description=projection.item_description,
            item_equipment_type=projection.item_equipment_type,
            durability_current=projection.durability_current,
            durability_max=projection.durability_max,
            requested_gold=event.requested_gold,
            status=TradeStatus.COMPLETED,
            created_at=event.trade_created_at,
        )

    def _execute_once(
        self,
        *,
        consumer_id: str,
        event_id: int,
        projection: Callable[[TradeReadModelRepository], None],
        handler_name: str,
        trade_id: int,
    ) -> bool:
        try:
            return self._projection_executor.execute_once(
                consumer_id=consumer_id,
                event_id=event_id,
                projection=projection,
            )
        except (ApplicationException, DomainException):
            raise
        except Exception as error:
            self._logger.exception(
                "Failed to handle event in %s: %s",
                handler_name,
                error,
                extra={"handler": handler_name, "trade_id": trade_id},
            )
            raise SystemErrorException(
                f"Trade event handling failed in {handler_name}: {error}",
                original_exception=error,
            ) from error

    def handle_trade_offered(self, event: TradeOfferedEvent) -> None:
        """取引提案を同じevent_idにつき一度だけ投影する。"""

        def projection(repository: TradeReadModelRepository) -> None:
            repository.save(self._read_model_from_offered_event(event))

        applied = self._execute_once(
            consumer_id=self.OFFERED_CONSUMER_ID,
            event_id=event.event_id,
            projection=projection,
            handler_name="handle_trade_offered",
            trade_id=event.aggregate_id.value,
        )
        if applied:
            self._logger.info(
                "ReadModel updated for trade offered: %s", event.aggregate_id.value
            )

    def handle_trade_accepted(self, event: TradeAcceptedEvent) -> None:
        """取引受諾を同じevent_idにつき一度だけ投影する。"""
        created = False

        def projection(repository: TradeReadModelRepository) -> None:
            nonlocal created
            read_model = repository.find_by_id(event.aggregate_id)
            if read_model is None:
                repository.save(self._read_model_from_accepted_event(event))
                created = True
                return
            repository.save(
                replace(
                    read_model,
                    buyer_id=event.buyer_id.value,
                    buyer_name=event.buyer_display_name,
                    status=TradeStatus.COMPLETED.name,
                )
            )

        applied = self._execute_once(
            consumer_id=self.ACCEPTED_CONSUMER_ID,
            event_id=event.event_id,
            projection=projection,
            handler_name="handle_trade_accepted",
            trade_id=event.aggregate_id.value,
        )
        if applied:
            action = "created" if created else "updated"
            self._logger.info(
                "ReadModel %s for trade accepted: %s",
                action,
                event.aggregate_id.value,
            )

    def handle_trade_cancelled(self, event: TradeCancelledEvent) -> None:
        """取引キャンセルを同じevent_idにつき一度だけ投影する。"""
        updated = False

        def projection(repository: TradeReadModelRepository) -> None:
            nonlocal updated
            read_model = repository.find_by_id(event.aggregate_id)
            if read_model is None:
                self._logger.warning(
                    "ReadModel not found for trade: %s", event.aggregate_id.value
                )
                return
            repository.save(replace(read_model, status=TradeStatus.CANCELLED.name))
            updated = True

        applied = self._execute_once(
            consumer_id=self.CANCELLED_CONSUMER_ID,
            event_id=event.event_id,
            projection=projection,
            handler_name="handle_trade_cancelled",
            trade_id=event.aggregate_id.value,
        )
        if applied and updated:
            self._logger.info(
                "ReadModel updated for trade cancelled: %s", event.aggregate_id.value
            )

    def handle_trade_declined(self, event: TradeDeclinedEvent) -> None:
        """取引拒否を同じevent_idにつき一度だけ投影する。"""
        updated = False

        def projection(repository: TradeReadModelRepository) -> None:
            nonlocal updated
            read_model = repository.find_by_id(event.aggregate_id)
            if read_model is None:
                self._logger.warning(
                    "ReadModel not found for trade: %s", event.aggregate_id.value
                )
                return
            repository.save(replace(read_model, status=TradeStatus.CANCELLED.name))
            updated = True

        applied = self._execute_once(
            consumer_id=self.DECLINED_CONSUMER_ID,
            event_id=event.event_id,
            projection=projection,
            handler_name="handle_trade_declined",
            trade_id=event.aggregate_id.value,
        )
        if applied and updated:
            self._logger.info(
                "ReadModel updated for trade declined: %s", event.aggregate_id.value
            )
