"""ショップコマンドサービス"""
import logging
from typing import Callable, Any

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.shop.aggregate.shop_aggregate import ShopAggregate
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.shop.value_object.shop_listing_price import ShopListingPrice
from ai_rpg_world.domain.shop.repository.shop_repository import ShopRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.player.repository.player_inventory_repository import PlayerInventoryRepository
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository

from ai_rpg_world.application.shop.contracts.commands import (
    CreateShopCommand,
    ListShopItemCommand,
    UnlistShopItemCommand,
    PurchaseFromShopCommand,
)
from ai_rpg_world.application.shop.contracts.dtos import ShopCommandResultDto
from ai_rpg_world.application.shop.exceptions.base_exception import (
    ShopApplicationException,
    ShopSystemErrorException,
)
from ai_rpg_world.application.shop.exceptions.command_exception import (
    ShopCommandException,
    ShopNotFoundForCommandException,
    NotAtShopLocationException,
    NotShopOwnerException as AppNotShopOwnerException,
    ListingNotFoundForCommandException,
    InsufficientStockForPurchaseException,
    CannotPartiallyPurchaseException,
    ShopAlreadyExistsAtLocationException,
)


class ShopCommandService:
    """ショップコマンドサービス"""

    def __init__(
        self,
        shop_repository: ShopRepository,
        player_inventory_repository: PlayerInventoryRepository,
        player_status_repository: PlayerStatusRepository,
        item_repository: ItemRepository,
        physical_map_repository: PhysicalMapRepository,
        unit_of_work: UnitOfWork,
    ):
        self._shop_repository = shop_repository
        self._player_inventory_repository = player_inventory_repository
        self._player_status_repository = player_status_repository
        self._item_repository = item_repository
        self._physical_map_repository = physical_map_repository
        self._unit_of_work = unit_of_work
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(
        self,
        operation: Callable[[], Any],
        context: dict,
    ) -> Any:
        """共通の例外処理を実行"""
        try:
            return operation()
        except ShopApplicationException:
            raise
        except DomainException as e:
            raise ShopCommandException(
                str(e),
                user_id=context.get("user_id"),
                shop_id=context.get("shop_id"),
                listing_id=context.get("listing_id"),
            )
        except Exception as e:
            self._logger.error(
                f"Unexpected error in {context.get('action', 'unknown')}: {e}",
                extra=context,
            )
            raise ShopSystemErrorException(
                f"{context.get('action', 'unknown')} failed: {e}",
                original_exception=e,
            )

    def _is_player_at_shop_location(
        self,
        player_id: PlayerId,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
    ) -> bool:
        """プレイヤーが指定ロケーションにいるか判定"""
        status = self._player_status_repository.find_by_id(player_id)
        if status is None:
            return False
        if status.current_spot_id is None or status.current_coordinate is None:
            return False
        if status.current_spot_id != spot_id:
            return False
        physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
        if physical_map is None:
            return False
        areas = physical_map.get_location_areas_at(status.current_coordinate)
        return any(la.location_id == location_area_id for la in areas)

    def create_shop(self, command: CreateShopCommand) -> ShopCommandResultDto:
        """ショップを開設する"""
        return self._execute_with_error_handling(
            operation=lambda: self._create_shop_impl(command),
            context={"action": "create_shop", "user_id": command.owner_id},
        )

    def _create_shop_impl(self, command: CreateShopCommand) -> ShopCommandResultDto:
        with self._unit_of_work:
            spot_id = SpotId.create(command.spot_id)
            location_area_id = LocationAreaId.create(command.location_area_id)
            owner_id = PlayerId(command.owner_id)

            existing = self._shop_repository.find_by_spot_and_location(
                spot_id, location_area_id
            )
            if existing is not None:
                raise ShopAlreadyExistsAtLocationException(
                    command.spot_id, command.location_area_id
                )

            shop_id = self._shop_repository.generate_shop_id()
            shop = ShopAggregate.create(
                shop_id=shop_id,
                spot_id=spot_id,
                location_area_id=location_area_id,
                owner_id=owner_id,
                name=command.name,
                description=command.description,
            )
            self._shop_repository.save(shop)
            self._logger.info(
                f"Shop created: shop_id={shop_id.value}, owner_id={command.owner_id}"
            )
            return ShopCommandResultDto(
                success=True,
                message="ショップを開設しました",
                data={"shop_id": shop_id.value},
            )

    def list_shop_item(self, command: ListShopItemCommand) -> ShopCommandResultDto:
        """ショップにアイテムを出品する（オーナーはロケーションにいなくても可）"""
        return self._execute_with_error_handling(
            operation=lambda: self._list_shop_item_impl(command),
            context={
                "action": "list_shop_item",
                "user_id": command.player_id,
                "shop_id": command.shop_id,
            },
        )

    def _list_shop_item_impl(
        self, command: ListShopItemCommand
    ) -> ShopCommandResultDto:
        with self._unit_of_work:
            shop_id = ShopId.create(command.shop_id)
            player_id = PlayerId(command.player_id)

            shop = self._shop_repository.find_by_id(shop_id)
            if shop is None:
                raise ShopNotFoundForCommandException(command.shop_id, "list_shop_item")
            if not shop.is_owner(player_id):
                raise AppNotShopOwnerException(
                    command.player_id, command.shop_id, "list_shop_item"
                )

            owner_inventory = self._player_inventory_repository.find_by_id(player_id)
            if owner_inventory is None:
                raise ShopCommandException(
                    f"Player inventory not found: {command.player_id}",
                    user_id=command.player_id,
                )

            item_instance_id = owner_inventory.remove_item_for_placement(
                SlotId(command.slot_id)
            )

            listing_id = self._shop_repository.generate_listing_id()
            price = ShopListingPrice.of(command.price_per_unit)
            shop.list_item(
                listing_id=listing_id,
                item_instance_id=item_instance_id,
                price_per_unit=price,
                listed_by=player_id,
            )

            self._shop_repository.save(shop)
            self._player_inventory_repository.save(owner_inventory)

            self._logger.info(
                f"Shop item listed: shop_id={command.shop_id}, listing_id={listing_id.value}"
            )
            return ShopCommandResultDto(
                success=True,
                message="出品しました",
                data={"shop_id": command.shop_id, "listing_id": listing_id.value},
            )

    def unlist_shop_item(self, command: UnlistShopItemCommand) -> ShopCommandResultDto:
        """ショップのリストを取り下げ、アイテムをオーナーインベントリに戻す"""
        return self._execute_with_error_handling(
            operation=lambda: self._unlist_shop_item_impl(command),
            context={
                "action": "unlist_shop_item",
                "user_id": command.player_id,
                "shop_id": command.shop_id,
                "listing_id": command.listing_id,
            },
        )

    def _unlist_shop_item_impl(
        self, command: UnlistShopItemCommand
    ) -> ShopCommandResultDto:
        with self._unit_of_work:
            shop_id = ShopId.create(command.shop_id)
            listing_id = ShopListingId.create(command.listing_id)
            player_id = PlayerId(command.player_id)

            shop = self._shop_repository.find_by_id(shop_id)
            if shop is None:
                raise ShopNotFoundForCommandException(
                    command.shop_id, "unlist_shop_item"
                )
            if not shop.is_owner(player_id):
                raise AppNotShopOwnerException(
                    command.player_id, command.shop_id, "unlist_shop_item"
                )

            listing = shop.get_listing(listing_id)
            if listing is None:
                raise ListingNotFoundForCommandException(
                    command.shop_id, command.listing_id, "unlist_shop_item"
                )

            item_instance_id = listing.item_instance_id
            shop.unlist_item(listing_id, player_id)

            owner_inventory = self._player_inventory_repository.find_by_id(player_id)
            if owner_inventory is None:
                raise ShopCommandException(
                    f"Player inventory not found: {command.player_id}",
                    user_id=command.player_id,
                )
            owner_inventory.acquire_item(item_instance_id)

            self._shop_repository.save(shop)
            self._player_inventory_repository.save(owner_inventory)

            self._logger.info(
                f"Shop item unlisted: shop_id={command.shop_id}, listing_id={command.listing_id}"
            )
            return ShopCommandResultDto(
                success=True,
                message="取り下げました",
                data={"shop_id": command.shop_id, "listing_id": command.listing_id},
            )

    def purchase_from_shop(
        self, command: PurchaseFromShopCommand
    ) -> ShopCommandResultDto:
        """ショップから購入する（購入者はそのロケーションにいる必要あり）"""
        return self._execute_with_error_handling(
            operation=lambda: self._purchase_from_shop_impl(command),
            context={
                "action": "purchase_from_shop",
                "user_id": command.buyer_id,
                "shop_id": command.shop_id,
                "listing_id": command.listing_id,
            },
        )

    def _purchase_from_shop_impl(
        self, command: PurchaseFromShopCommand
    ) -> ShopCommandResultDto:
        with self._unit_of_work:
            shop_id = ShopId.create(command.shop_id)
            listing_id = ShopListingId.create(command.listing_id)
            buyer_id = PlayerId(command.buyer_id)

            if command.quantity <= 0:
                raise ShopCommandException(
                    "購入数は1以上である必要があります",
                    user_id=command.buyer_id,
                    shop_id=command.shop_id,
                )

            shop = self._shop_repository.find_by_id(shop_id)
            if shop is None:
                raise ShopNotFoundForCommandException(
                    command.shop_id, "purchase_from_shop"
                )

            if not self._is_player_at_shop_location(
                buyer_id, shop.spot_id, shop.location_area_id
            ):
                raise NotAtShopLocationException(command.buyer_id, command.shop_id)

            listing = shop.get_listing(listing_id)
            if listing is None:
                raise ListingNotFoundForCommandException(
                    command.shop_id, command.listing_id, "purchase_from_shop"
                )

            item_aggregate = self._item_repository.find_by_id(listing.item_instance_id)
            if item_aggregate is None:
                raise ListingNotFoundForCommandException(
                    command.shop_id, command.listing_id, "purchase_from_shop"
                )

            available = item_aggregate.quantity
            if command.quantity > available:
                raise InsufficientStockForPurchaseException(
                    command.listing_id, command.quantity, available
                )

            total_gold = listing.price_per_unit.value * command.quantity
            buyer_status = self._player_status_repository.find_by_id(buyer_id)
            if buyer_status is None:
                raise ShopCommandException(
                    f"Buyer status not found: {command.buyer_id}",
                    user_id=command.buyer_id,
                )
            seller_id = listing.listed_by
            seller_status = self._player_status_repository.find_by_id(seller_id)
            if seller_status is None:
                raise ShopCommandException(
                    f"Seller status not found: {seller_id.value}",
                )
            buyer_inventory = self._player_inventory_repository.find_by_id(buyer_id)
            if buyer_inventory is None:
                raise ShopCommandException(
                    f"Buyer inventory not found: {command.buyer_id}",
                    user_id=command.buyer_id,
                )

            if command.quantity < available:
                if item_aggregate.durability is not None:
                    raise CannotPartiallyPurchaseException(
                        command.listing_id,
                        "耐久度を持つアイテムは部分購入できません",
                    )
                if item_aggregate.item_spec.max_stack_size.value < 2:
                    raise CannotPartiallyPurchaseException(
                        command.listing_id,
                        "スタック不可アイテムは部分購入できません",
                    )

            shop.record_purchase(
                listing_id=listing_id,
                buyer_id=buyer_id,
                quantity=command.quantity,
                total_gold=total_gold,
            )

            buyer_status.pay_gold(total_gold)
            seller_status.earn_gold(total_gold)

            if command.quantity == available:
                buyer_inventory.acquire_item(listing.item_instance_id)
                shop.remove_listing(listing_id)
                self._shop_repository.save(shop)
                self._player_status_repository.save(buyer_status)
                self._player_status_repository.save(seller_status)
                self._player_inventory_repository.save(buyer_inventory)
            else:
                new_item_id = self._item_repository.generate_item_instance_id()
                from ai_rpg_world.domain.item.aggregate.item_aggregate import (
                    ItemAggregate,
                )

                new_item = ItemAggregate.create(
                    item_instance_id=new_item_id,
                    item_spec=item_aggregate.item_spec,
                    durability=None,
                    quantity=command.quantity,
                )
                self._item_repository.save(new_item)
                buyer_inventory.acquire_item(new_item_id)
                item_aggregate.remove_quantity(command.quantity)
                if item_aggregate.quantity == 0:
                    self._item_repository.delete(listing.item_instance_id)
                    shop.remove_listing(listing_id)
                else:
                    self._item_repository.save(item_aggregate)
                self._player_status_repository.save(buyer_status)
                self._player_status_repository.save(seller_status)
                self._player_inventory_repository.save(buyer_inventory)
                self._shop_repository.save(shop)

            self._logger.info(
                f"Purchase from shop: shop_id={command.shop_id}, listing_id={command.listing_id}, "
                f"buyer_id={command.buyer_id}, quantity={command.quantity}"
            )
            return ShopCommandResultDto(
                success=True,
                message="購入しました",
                data={
                    "shop_id": command.shop_id,
                    "listing_id": command.listing_id,
                    "quantity": command.quantity,
                    "total_gold": total_gold,
                },
            )
