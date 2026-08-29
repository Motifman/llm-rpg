import logging
from typing import Any, Callable
from datetime import datetime, timezone

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactoryPort
from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.trade.trade_command_repository_provider import (
    TradeCommandRepositoryProviderPort,
)
from ai_rpg_world.domain.trade.aggregate.trade_aggregate import TradeAggregate
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from ai_rpg_world.domain.trade.value_object.trade_scope import TradeScope
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.trade.value_object.trade_listing_projection import TradeListingProjection

from ai_rpg_world.application.trade.contracts.commands import (
    OfferItemCommand,
    AcceptTradeCommand,
    CancelTradeCommand,
    DeclineTradeCommand,
)
from ai_rpg_world.application.trade.contracts.dtos import TradeCommandResultDto
from ai_rpg_world.application.trade.exceptions.base_exception import TradeApplicationException, TradeSystemErrorException
from ai_rpg_world.application.trade.exceptions.command.trade_command_exception import (
    TradeCommandException,
    TradeCreationException,
    TradeNotFoundForCommandException,
    TradeAccessDeniedException
)
from ai_rpg_world.domain.common.exception import DomainException


class TradeCommandService:
    """取引コマンドサービス"""

    def __init__(
        self,
        command_scope_factory: CommandScopeFactoryPort[
            TradeCommandRepositoryProviderPort
        ],
    ) -> None:
        self._command_scope_factory = command_scope_factory
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(self, operation: Callable[[], Any], context: dict) -> Any:
        """共通の例外処理を実行"""
        try:
            return operation()
        except CommandPostCommitException:
            raise
        except TradeApplicationException as e:
            raise e
        except DomainException as e:
            # ドメイン例外をアプリケーション例外に変換
            raise TradeCommandException(str(e), user_id=context.get('user_id'), trade_id=context.get('trade_id'))
        except Exception as e:
            self._logger.error(f"Unexpected error in {context.get('action', 'unknown')}: {str(e)}",
                             extra=context)
            raise TradeSystemErrorException(f"{context.get('action', 'unknown')} failed: {str(e)}",
                                         original_exception=e)

    def offer_item(self, command: OfferItemCommand) -> TradeCommandResultDto:
        """アイテムを出品"""
        return self._execute_with_error_handling(
            operation=lambda: self._offer_item_impl(command),
            context={
                "action": "offer_item",
                "user_id": command.seller_id,
                "item_instance_id": command.item_instance_id
            }
        )

    def _offer_item_impl(self, command: OfferItemCommand) -> TradeCommandResultDto:
        """アイテム出品の実装"""
        with self._command_scope_factory.create() as context:
            repositories = context.repositories
            seller_id = PlayerId(command.seller_id)
            
            # 出品者のインベントリを取得
            inventory = repositories.player_inventories.find_by_id(seller_id)
            if inventory is None:
                raise TradeCreationException(f"Seller inventory not found: {command.seller_id}", command.seller_id)

            # アイテムを予約（ロック）
            item_id = inventory.reserve_item(SlotId(command.slot_id))
            if item_id.value != command.item_instance_id:
                raise TradeCreationException(f"Item ID mismatch in slot: expected {command.item_instance_id}, found {item_id.value}", command.seller_id)

            # 取引範囲の設定
            if command.is_direct:
                if command.target_player_id is None:
                    raise TradeCreationException("Target player ID is required for direct trade", command.seller_id)
                trade_scope = TradeScope.direct_trade(PlayerId(command.target_player_id))
            else:
                trade_scope = TradeScope.global_trade()

            seller_profile = repositories.player_profiles.find_by_id(seller_id)
            if seller_profile is None:
                raise TradeCreationException(f"Seller profile not found: {command.seller_id}", command.seller_id)

            item_aggregate = repositories.items.find_by_id(item_id)
            if item_aggregate is None:
                raise TradeCreationException(f"Item instance not found: {command.item_instance_id}", command.seller_id)

            listing_projection = TradeListingProjection.from_seller_and_item(
                seller_display_name=seller_profile.name.value,
                item=item_aggregate.item_instance,
            )

            # 取引集約の作成
            trade_id = repositories.trades.generate_trade_id()
            created_at = datetime.now(timezone.utc)
            trade = TradeAggregate.create_new_trade(
                trade_id=trade_id,
                seller_id=seller_id,
                offered_item_id=item_id,
                requested_gold=TradeRequestedGold.of(command.requested_gold),
                created_at=created_at,
                trade_scope=trade_scope,
                listing_projection=listing_projection,
            )

            # 保存
            repositories.trades.save(trade)
            repositories.player_inventories.save(inventory)

            result = TradeCommandResultDto(
                success=True,
                message="アイテムを出品しました",
                data={"trade_id": trade_id.value}
            )
        self._logger.info(f"Trade offered: trade_id={trade_id.value}, seller_id={command.seller_id}")
        return result

    def accept_trade(self, command: AcceptTradeCommand) -> TradeCommandResultDto:
        """取引を受諾"""
        return self._execute_with_error_handling(
            operation=lambda: self._accept_trade_impl(command),
            context={
                "action": "accept_trade",
                "user_id": command.buyer_id,
                "trade_id": command.trade_id
            }
        )

    def _accept_trade_impl(self, command: AcceptTradeCommand) -> TradeCommandResultDto:
        """取引受諾の実装"""
        with self._command_scope_factory.create() as context:
            repositories = context.repositories
            trade_id = TradeId(command.trade_id)
            buyer_id = PlayerId(command.buyer_id)

            # 取引を取得
            trade = repositories.trades.find_by_id(trade_id)
            if trade is None:
                raise TradeNotFoundForCommandException(command.trade_id, "accept_trade")

            if trade.seller_id == buyer_id:
                raise TradeAccessDeniedException(command.trade_id, command.buyer_id, "accept_trade (self-trade not allowed)")

            if not trade.can_be_accepted_by(buyer_id):
                raise TradeAccessDeniedException(command.trade_id, command.buyer_id, "accept_trade")

            # 出品者のステータスを取得（ゴールド受取のため）
            seller_status = repositories.player_statuses.find_by_id(trade.seller_id)
            if seller_status is None:
                raise TradeCommandException(f"Seller status not found: {trade.seller_id.value}", trade_id=command.trade_id)

            # 購入者のステータス（ゴールド支払）とインベントリ（アイテム受取）を取得
            buyer_status = repositories.player_statuses.find_by_id(buyer_id)
            if buyer_status is None:
                raise TradeCommandException(f"Buyer status not found: {command.buyer_id}", user_id=command.buyer_id)

            buyer_inventory = repositories.player_inventories.find_by_id(buyer_id)
            if buyer_inventory is None:
                raise TradeCommandException(f"Buyer inventory not found: {command.buyer_id}", user_id=command.buyer_id)

            # 出品者のインベントリを取得（予約アイテム削除のため）
            seller_inventory = repositories.player_inventories.find_by_id(trade.seller_id)
            if seller_inventory is None:
                raise TradeCommandException(f"Seller inventory not found: {trade.seller_id.value}", trade_id=command.trade_id)

            # 購入者のインベントリ空き容量をチェック
            if buyer_inventory.is_inventory_full():
                raise TradeCommandException(f"Buyer inventory is full: {command.buyer_id}", user_id=command.buyer_id)

            # --- 取引の実行 ---
            
            # 1. 購入者がゴールドを支払う
            buyer_status.pay_gold(trade.requested_gold.value)
            
            # 2. 出品者がゴールドを受け取る
            seller_status.earn_gold(trade.requested_gold.value)
            
            # 3. 出品者のインベントリから予約アイテムを削除
            seller_inventory.remove_reserved_item(trade.offered_item_id)
            
            item_aggregate = repositories.items.find_by_id(trade.offered_item_id)
            if item_aggregate is None:
                raise TradeCommandException(
                    f"Offered item not found: {trade.offered_item_id.value}",
                    trade_id=command.trade_id,
                )

            # 4. 購入者のインベントリにアイテムを追加
            buyer_inventory.acquire_item(
                trade.offered_item_id,
                item_spec_id_value=item_aggregate.item_spec.item_spec_id.value,
            )
            
            seller_profile = repositories.player_profiles.find_by_id(trade.seller_id)
            if seller_profile is None:
                raise TradeCommandException(f"Seller profile not found: {trade.seller_id.value}", trade_id=command.trade_id)

            buyer_profile = repositories.player_profiles.find_by_id(buyer_id)
            if buyer_profile is None:
                raise TradeCommandException(f"Buyer profile not found: {command.buyer_id}", user_id=command.buyer_id)

            listing_projection = TradeListingProjection.from_seller_and_item(
                seller_display_name=seller_profile.name.value,
                item=item_aggregate.item_instance,
            )

            # 5. 取引を完了状態にする
            trade.accept_by(
                buyer_id,
                buyer_display_name=buyer_profile.name.value,
                listing_projection=listing_projection,
            )

            # 保存
            repositories.trades.save(trade)
            repositories.player_statuses.save(seller_status)
            repositories.player_statuses.save(buyer_status)
            repositories.player_inventories.save(seller_inventory)
            repositories.player_inventories.save(buyer_inventory)

            result = TradeCommandResultDto(
                success=True,
                message="取引を受諾しました",
                data={"trade_id": command.trade_id}
            )
        self._logger.info(f"Trade accepted: trade_id={command.trade_id}, buyer_id={command.buyer_id}")
        return result

    def cancel_trade(self, command: CancelTradeCommand) -> TradeCommandResultDto:
        """取引をキャンセル"""
        return self._execute_with_error_handling(
            operation=lambda: self._cancel_trade_impl(command),
            context={
                "action": "cancel_trade",
                "user_id": command.player_id,
                "trade_id": command.trade_id
            }
        )

    def _cancel_trade_impl(self, command: CancelTradeCommand) -> TradeCommandResultDto:
        """取引キャンセルの実装"""
        with self._command_scope_factory.create() as context:
            repositories = context.repositories
            trade_id = TradeId(command.trade_id)
            player_id = PlayerId(command.player_id)

            trade = repositories.trades.find_by_id(trade_id)
            if trade is None:
                raise TradeNotFoundForCommandException(command.trade_id, "cancel_trade")

            if trade.seller_id != player_id:
                raise TradeAccessDeniedException(command.trade_id, command.player_id, "cancel_trade")

            # 出品者のインベントリを取得（予約解除のため）
            inventory = repositories.player_inventories.find_by_id(player_id)
            if inventory is None:
                raise TradeCommandException(f"Seller inventory not found: {command.player_id}", user_id=command.player_id)

            # アイテムの予約を解除
            inventory.unreserve_item(trade.offered_item_id)

            # 取引をキャンセル状態にする
            trade.cancel_by(player_id)

            # 保存
            repositories.trades.save(trade)
            repositories.player_inventories.save(inventory)

            result = TradeCommandResultDto(
                success=True,
                message="取引をキャンセルしました",
                data={"trade_id": command.trade_id}
            )
        self._logger.info(f"Trade cancelled: trade_id={command.trade_id}, player_id={command.player_id}")
        return result

    def decline_trade(self, command: DeclineTradeCommand) -> TradeCommandResultDto:
        """取引を断る"""
        return self._execute_with_error_handling(
            operation=lambda: self._decline_trade_impl(command),
            context={
                "action": "decline_trade",
                "user_id": command.decliner_id,
                "trade_id": command.trade_id
            }
        )

    def _decline_trade_impl(self, command: DeclineTradeCommand) -> TradeCommandResultDto:
        """取引拒否の実装"""
        with self._command_scope_factory.create() as context:
            repositories = context.repositories
            trade_id = TradeId(command.trade_id)
            decliner_id = PlayerId(command.decliner_id)

            trade = repositories.trades.find_by_id(trade_id)
            if trade is None:
                raise TradeNotFoundForCommandException(command.trade_id, "decline_trade")

            # ドメインで検証（直接取引の宛先のみ decline 可能）
            trade.decline_by(decliner_id)

            # 出品者のインベントリを取得（予約解除のため）
            inventory = repositories.player_inventories.find_by_id(trade.seller_id)
            if inventory is None:
                raise TradeCommandException(
                    f"Seller inventory not found: {trade.seller_id.value}",
                    trade_id=command.trade_id
                )

            # アイテムの予約を解除
            inventory.unreserve_item(trade.offered_item_id)

            # 保存
            repositories.trades.save(trade)
            repositories.player_inventories.save(inventory)

            result = TradeCommandResultDto(
                success=True,
                message="取引を断りました",
                data={"trade_id": command.trade_id}
            )
        self._logger.info(f"Trade declined: trade_id={command.trade_id}, decliner_id={command.decliner_id}")
        return result
