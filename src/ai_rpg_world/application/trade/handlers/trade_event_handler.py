import logging
from typing import TYPE_CHECKING, Callable, Any, Optional
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.domain.trade.event.trade_event import (
    TradeOfferedEvent,
    TradeAcceptedEvent,
    TradeCancelledEvent
)
from ai_rpg_world.domain.trade.read_model.trade_read_model import TradeReadModel
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId

if TYPE_CHECKING:
    from ai_rpg_world.domain.trade.repository.trade_read_model_repository import TradeReadModelRepository
    from ai_rpg_world.domain.trade.repository.trade_repository import TradeRepository
    from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
    from ai_rpg_world.domain.item.repository.item_instance_repository import ItemInstanceRepository


class TradeEventHandler:
    """取引イベントハンドラ
    
    ドメインイベントを購読し、ReadModelを更新する。
    """

    def __init__(
        self,
        trade_read_model_repository: "TradeReadModelRepository",
        trade_repository: "TradeRepository",
        player_profile_repository: "PlayerProfileRepository",
        item_instance_repository: "ItemInstanceRepository",
        unit_of_work_factory: UnitOfWorkFactory
    ):
        self._trade_read_model_repository = trade_read_model_repository
        self._trade_repository = trade_repository
        self._player_profile_repository = player_profile_repository
        self._item_instance_repository = item_instance_repository
        self._unit_of_work_factory = unit_of_work_factory
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_in_separate_transaction(self, operation: Callable[[], Any], context: dict) -> None:
        """別トランザクションで操作を実行"""
        unit_of_work = self._unit_of_work_factory.create()
        try:
            with unit_of_work:
                operation()
        except Exception as e:
            self._logger.error(f"Failed to handle event in {context.get('handler', 'unknown')}: {str(e)}",
                             extra=context, exc_info=True)

    def handle_trade_offered(self, event: TradeOfferedEvent) -> None:
        """取引出品イベントのハンドリング"""
        def operation():
            # 出品者情報を取得
            seller_profile = self._player_profile_repository.find_by_id(event.seller_id)
            seller_name = seller_profile.name.value if seller_profile else f"Unknown({event.seller_id.value})"

            # アイテム情報を取得
            item_instance = self._item_instance_repository.find_by_id(event.offered_item_id)
            if not item_instance:
                self._logger.error(f"Item instance not found for ReadModel update: {event.offered_item_id.value}")
                return

            item_spec = item_instance.item_spec

            # ReadModel作成
            read_model = TradeReadModel.create_from_trade_and_item(
                trade_id=event.aggregate_id,
                seller_id=event.seller_id,
                seller_name=seller_name,
                buyer_id=None,
                buyer_name=None,
                item_instance_id=event.offered_item_id,
                item_name=item_spec.name,
                item_quantity=item_instance.quantity,
                item_type=item_spec.item_type,
                item_rarity=item_spec.rarity,
                item_description=item_spec.description,
                item_equipment_type=item_spec.equipment_type if hasattr(item_spec, 'equipment_type') else None,
                durability_current=item_instance.durability.current if item_instance.durability else None,
                durability_max=item_instance.durability.max_value if item_instance.durability else None,
                requested_gold=event.requested_gold,
                status=TradeStatus.ACTIVE,
                created_at=event.occurred_at
            )

            # 保存
            self._trade_read_model_repository.save(read_model)
            self._logger.info(f"ReadModel updated for trade offered: {event.aggregate_id.value}")

        self._execute_in_separate_transaction(operation, {
            "handler": "handle_trade_offered",
            "trade_id": event.aggregate_id.value
        })

    def handle_trade_accepted(self, event: TradeAcceptedEvent) -> None:
        """取引受諾イベントのハンドリング"""
        def operation():
            # 既存のReadModelを取得
            read_model = self._trade_read_model_repository.find_by_id(event.aggregate_id)
            if not read_model:
                # 集約から復元を試みる
                trade_aggregate = self._trade_repository.find_by_id(event.aggregate_id)
                if not trade_aggregate:
                    self._logger.error(f"Trade aggregate not found for ReadModel update: {event.aggregate_id.value}")
                    return
                # (本来はここに詳細な復元ロジックが必要だが、Offered時に作られている前提)
                self._logger.warning(f"ReadModel not found for trade: {event.aggregate_id.value}, skip update or implement full reconstruction.")
                return

            # 購入者情報を取得
            buyer_profile = self._player_profile_repository.find_by_id(event.buyer_id)
            buyer_name = buyer_profile.name.value if buyer_profile else f"Unknown({event.buyer_id.value})"

            # 状態更新
            read_model.buyer_id = event.buyer_id.value
            read_model.buyer_name = buyer_name
            read_model.status = TradeStatus.COMPLETED.name

            # 保存
            self._trade_read_model_repository.save(read_model)
            self._logger.info(f"ReadModel updated for trade accepted: {event.aggregate_id.value}")

        self._execute_in_separate_transaction(operation, {
            "handler": "handle_trade_accepted",
            "trade_id": event.aggregate_id.value,
            "buyer_id": event.buyer_id.value
        })

    def handle_trade_cancelled(self, event: TradeCancelledEvent) -> None:
        """取引キャンセルイベントのハンドリング"""
        def operation():
            # 既存のReadModelを取得
            read_model = self._trade_read_model_repository.find_by_id(event.aggregate_id)
            if not read_model:
                self._logger.warning(f"ReadModel not found for trade: {event.aggregate_id.value}")
                return

            # 状態更新
            read_model.status = TradeStatus.CANCELLED.name

            # 保存
            self._trade_read_model_repository.save(read_model)
            self._logger.info(f"ReadModel updated for trade cancelled: {event.aggregate_id.value}")

        self._execute_in_separate_transaction(operation, {
            "handler": "handle_trade_cancelled",
            "trade_id": event.aggregate_id.value
        })
