"""ShopCommandServiceのテスト"""
import pytest
from ai_rpg_world.application.shop.services.shop_command_service import ShopCommandService
from ai_rpg_world.application.shop.contracts.commands import (
    CreateShopCommand,
    ListShopItemCommand,
    UnlistShopItemCommand,
    PurchaseFromShopCommand,
)
from ai_rpg_world.application.shop.contracts.dtos import ShopCommandResultDto
from ai_rpg_world.application.shop.exceptions.command_exception import (
    ShopCommandException,
    ShopNotFoundForCommandException,
    NotAtShopLocationException,
    NotShopOwnerException,
    ListingNotFoundForCommandException,
    InsufficientStockForPurchaseException,
    CannotPartiallyPurchaseException,
    ShopAlreadyExistsAtLocationException,
)

from ai_rpg_world.domain.shop.aggregate.shop_aggregate import ShopAggregate
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.location_area import LocationArea
from ai_rpg_world.domain.world.value_object.area import PointArea
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.shop.value_object.shop_listing_price import ShopListingPrice

from ai_rpg_world.infrastructure.repository.in_memory_shop_repository import InMemoryShopRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


def _create_player_status(player_id: int, gold: int = 1000, spot_id: int = None, coord: Coordinate = None):
    """プレイヤーステータスを作成（任意で位置指定）"""
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(gold),
        hp=Hp.create(100, 100),
        mp=Mp.create(50, 50),
        stamina=Stamina.create(100, 100),
        current_spot_id=SpotId(spot_id) if spot_id is not None else None,
        current_coordinate=coord,
    )


def _create_stackable_item_spec():
    """スタック可能なアイテム仕様（部分購入用）"""
    return ItemSpec(
        item_spec_id=ItemSpecId(500),
        name="Test Material",
        item_type=ItemType.MATERIAL,
        rarity=Rarity.COMMON,
        description="Stackable material",
        max_stack_size=MaxStackSize(99),
    )


def _create_physical_map_with_location(spot_id_val: int, location_area_id_val: int, coord: Coordinate):
    """指定座標を含むLocationAreaを持つPhysicalMapを作成"""
    spot_id = SpotId(spot_id_val)
    tile = Tile(coord, TerrainType.road())
    location_area = LocationArea(
        location_id=LocationAreaId.create(location_area_id_val),
        area=PointArea(coord),
        name="Test Area",
        description="For shop test",
    )
    return PhysicalMapAggregate.create(
        spot_id=spot_id,
        tiles=[tile],
        location_areas=[location_area],
    )


class TestShopCommandService:
    """ShopCommandServiceのテスト"""

    @pytest.fixture
    def setup_service(self):
        """サービスとリポジトリのセットアップ"""
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow)

        unit_of_work, _ = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow
        )
        data_store = InMemoryDataStore()

        shop_repository = InMemoryShopRepository(data_store, unit_of_work)
        inventory_repository = InMemoryPlayerInventoryRepository(data_store, unit_of_work)
        status_repository = InMemoryPlayerStatusRepository(data_store, unit_of_work)
        item_repository = InMemoryItemRepository(data_store, unit_of_work)
        physical_map_repository = InMemoryPhysicalMapRepository(data_store, unit_of_work)

        service = ShopCommandService(
            shop_repository=shop_repository,
            player_inventory_repository=inventory_repository,
            player_status_repository=status_repository,
            item_repository=item_repository,
            physical_map_repository=physical_map_repository,
            unit_of_work=unit_of_work,
        )
        return {
            "service": service,
            "shop_repo": shop_repository,
            "inv_repo": inventory_repository,
            "status_repo": status_repository,
            "item_repo": item_repository,
            "map_repo": physical_map_repository,
            "uow": unit_of_work,
        }

    # ----- CreateShop -----

    def test_create_shop_success(self, setup_service):
        """ショップ開設が成功する"""
        s = setup_service
        cmd = CreateShopCommand(
            spot_id=1,
            location_area_id=1,
            owner_id=1,
            name="テスト店",
            description="説明",
        )
        result = s["service"].create_shop(cmd)
        assert result.success is True
        assert "shop_id" in result.data
        shop = s["shop_repo"].find_by_id(ShopId(result.data["shop_id"]))
        assert shop is not None
        assert shop.name == "テスト店"
        assert shop.is_owner(PlayerId(1)) is True

    def test_create_shop_duplicate_location_raises(self, setup_service):
        """同一ロケーションに2店舗目を作ると例外"""
        s = setup_service
        cmd = CreateShopCommand(spot_id=1, location_area_id=1, owner_id=1)
        s["service"].create_shop(cmd)
        with pytest.raises(ShopAlreadyExistsAtLocationException):
            s["service"].create_shop(
                CreateShopCommand(spot_id=1, location_area_id=1, owner_id=2)
            )

    def test_create_shop_invalid_spot_id_raises(self, setup_service):
        """無効なspot_idでショップ作成すると例外（ドメイン例外がラップされる）"""
        s = setup_service
        cmd = CreateShopCommand(
            spot_id=0,
            location_area_id=1,
            owner_id=1,
        )
        with pytest.raises(ShopCommandException):
            s["service"].create_shop(cmd)

    def test_create_shop_invalid_location_area_id_raises(self, setup_service):
        """無効なlocation_area_idでショップ作成すると例外（ドメイン例外がラップされる）"""
        s = setup_service
        cmd = CreateShopCommand(
            spot_id=1,
            location_area_id=0,
            owner_id=1,
        )
        with pytest.raises(ShopCommandException):
            s["service"].create_shop(cmd)

    # ----- ListShopItem -----

    def test_list_shop_item_success(self, setup_service):
        """出品が成功する"""
        s = setup_service
        owner_id = 1
        shop_id = s["shop_repo"].generate_shop_id()
        shop = ShopAggregate.create(
            shop_id=shop_id,
            spot_id=SpotId(1),
            location_area_id=LocationAreaId.create(1),
            owner_id=PlayerId(owner_id),
        )
        s["shop_repo"].save(shop)

        item_spec = _create_stackable_item_spec()
        item_id = s["item_repo"].generate_item_instance_id()
        item = ItemAggregate.create(item_instance_id=item_id, item_spec=item_spec, quantity=5)
        s["item_repo"].save(item)

        inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(owner_id))
        inv.acquire_item(item_id)
        s["inv_repo"].save(inv)

        cmd = ListShopItemCommand(
            shop_id=shop_id.value,
            player_id=owner_id,
            slot_id=0,
            price_per_unit=10,
        )
        result = s["service"].list_shop_item(cmd)
        assert result.success is True
        assert "listing_id" in result.data

        shop = s["shop_repo"].find_by_id(shop_id)
        assert len(shop.listings) == 1
        inv = s["inv_repo"].find_by_id(PlayerId(owner_id))
        assert inv.get_item_instance_id_by_slot(SlotId(0)) is None

    def test_list_shop_item_shop_not_found_raises(self, setup_service):
        """存在しないショップに出品すると例外"""
        s = setup_service
        cmd = ListShopItemCommand(shop_id=999, player_id=1, slot_id=0, price_per_unit=10)
        with pytest.raises(ShopNotFoundForCommandException):
            s["service"].list_shop_item(cmd)

    def test_list_shop_item_not_owner_raises(self, setup_service):
        """オーナー以外が出品すると例外"""
        s = setup_service
        shop_id = s["shop_repo"].generate_shop_id()
        shop = ShopAggregate.create(
            shop_id=shop_id,
            spot_id=SpotId(1),
            location_area_id=LocationAreaId.create(1),
            owner_id=PlayerId(1),
        )
        s["shop_repo"].save(shop)
        cmd = ListShopItemCommand(
            shop_id=shop_id.value,
            player_id=2,
            slot_id=0,
            price_per_unit=10,
        )
        with pytest.raises(NotShopOwnerException):
            s["service"].list_shop_item(cmd)

    def test_list_shop_item_player_inventory_not_found_raises(self, setup_service):
        """出品者インベントリが存在しないと例外"""
        s = setup_service
        shop_id = s["shop_repo"].generate_shop_id()
        shop = ShopAggregate.create(
            shop_id=shop_id,
            spot_id=SpotId(1),
            location_area_id=LocationAreaId.create(1),
            owner_id=PlayerId(1),
        )
        s["shop_repo"].save(shop)
        cmd = ListShopItemCommand(
            shop_id=shop_id.value,
            player_id=999,
            slot_id=0,
            price_per_unit=10,
        )
        with pytest.raises(ShopCommandException) as exc_info:
            s["service"].list_shop_item(cmd)
        assert "inventory" in str(exc_info.value).lower() or "999" in str(exc_info.value)

    def test_list_shop_item_slot_empty_raises(self, setup_service):
        """指定スロットにアイテムがないと例外（ドメイン例外がラップされる）"""
        s = setup_service
        owner_id = 1
        shop_id = s["shop_repo"].generate_shop_id()
        shop = ShopAggregate.create(
            shop_id=shop_id,
            spot_id=SpotId(1),
            location_area_id=LocationAreaId.create(1),
            owner_id=PlayerId(owner_id),
        )
        s["shop_repo"].save(shop)
        inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(owner_id))
        s["inv_repo"].save(inv)
        cmd = ListShopItemCommand(
            shop_id=shop_id.value,
            player_id=owner_id,
            slot_id=0,
            price_per_unit=10,
        )
        with pytest.raises(ShopCommandException):
            s["service"].list_shop_item(cmd)

    # ----- UnlistShopItem -----

    def test_unlist_shop_item_success(self, setup_service):
        """取り下げが成功し、アイテムがオーナーに戻る"""
        s = setup_service
        owner_id = 1
        shop_id = s["shop_repo"].generate_shop_id()
        listing_id = s["shop_repo"].generate_listing_id()
        shop = ShopAggregate.create(
            shop_id=shop_id,
            spot_id=SpotId(1),
            location_area_id=LocationAreaId.create(1),
            owner_id=PlayerId(owner_id),
        )
        item_spec = _create_stackable_item_spec()
        item_id = ItemInstanceId(100)
        item = ItemAggregate.create(item_instance_id=item_id, item_spec=item_spec, quantity=3)
        s["item_repo"].save(item)
        shop.list_item(
            listing_id=listing_id,
            item_instance_id=item_id,
            price_per_unit=ShopListingPrice.of(20),
            listed_by=PlayerId(owner_id),
        )
        s["shop_repo"].save(shop)

        inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(owner_id))
        s["inv_repo"].save(inv)

        cmd = UnlistShopItemCommand(
            shop_id=shop_id.value,
            listing_id=listing_id.value,
            player_id=owner_id,
        )
        result = s["service"].unlist_shop_item(cmd)
        assert result.success is True
        shop = s["shop_repo"].find_by_id(shop_id)
        assert shop.get_listing(listing_id) is None
        inv = s["inv_repo"].find_by_id(PlayerId(owner_id))
        assert inv.get_item_instance_id_by_slot(SlotId(0)) == item_id

    def test_unlist_shop_item_listing_not_found_raises(self, setup_service):
        """存在しないリストを取り下げると例外"""
        s = setup_service
        shop_id = s["shop_repo"].generate_shop_id()
        shop = ShopAggregate.create(
            shop_id=shop_id,
            spot_id=SpotId(1),
            location_area_id=LocationAreaId.create(1),
            owner_id=PlayerId(1),
        )
        s["shop_repo"].save(shop)
        cmd = UnlistShopItemCommand(shop_id=shop_id.value, listing_id=999, player_id=1)
        with pytest.raises(ListingNotFoundForCommandException):
            s["service"].unlist_shop_item(cmd)

    def test_unlist_shop_item_shop_not_found_raises(self, setup_service):
        """存在しないショップのリストを取り下げると例外"""
        s = setup_service
        cmd = UnlistShopItemCommand(
            shop_id=999,
            listing_id=1,
            player_id=1,
        )
        with pytest.raises(ShopNotFoundForCommandException):
            s["service"].unlist_shop_item(cmd)

    def test_unlist_shop_item_not_owner_raises(self, setup_service):
        """オーナー以外が取り下げると例外"""
        s = setup_service
        shop_id = s["shop_repo"].generate_shop_id()
        listing_id = s["shop_repo"].generate_listing_id()
        shop = ShopAggregate.create(
            shop_id=shop_id,
            spot_id=SpotId(1),
            location_area_id=LocationAreaId.create(1),
            owner_id=PlayerId(1),
        )
        shop.list_item(
            listing_id=listing_id,
            item_instance_id=ItemInstanceId(100),
            price_per_unit=ShopListingPrice.of(20),
            listed_by=PlayerId(1),
        )
        s["shop_repo"].save(shop)
        cmd = UnlistShopItemCommand(
            shop_id=shop_id.value,
            listing_id=listing_id.value,
            player_id=2,
        )
        with pytest.raises(NotShopOwnerException):
            s["service"].unlist_shop_item(cmd)

    # ----- PurchaseFromShop -----

    def test_purchase_from_shop_success_full_quantity(self, setup_service):
        """購入が成功する（全量購入・購入者はロケーションにいる）"""
        s = setup_service
        spot_id_val, loc_id_val = 1, 1
        coord = Coordinate(0, 0, 0)
        s["map_repo"].save(_create_physical_map_with_location(spot_id_val, loc_id_val, coord))

        owner_id, buyer_id = 1, 2
        shop_id = s["shop_repo"].generate_shop_id()
        shop = ShopAggregate.create(
            shop_id=shop_id,
            spot_id=SpotId(spot_id_val),
            location_area_id=LocationAreaId.create(loc_id_val),
            owner_id=PlayerId(owner_id),
        )
        item_spec = _create_stackable_item_spec()
        item_id = s["item_repo"].generate_item_instance_id()
        item = ItemAggregate.create(item_instance_id=item_id, item_spec=item_spec, quantity=2)
        s["item_repo"].save(item)
        listing_id = s["shop_repo"].generate_listing_id()
        shop.list_item(
            listing_id=listing_id,
            item_instance_id=item_id,
            price_per_unit=ShopListingPrice.of(50),
            listed_by=PlayerId(owner_id),
        )
        s["shop_repo"].save(shop)

        s["status_repo"].save(_create_player_status(owner_id, 0))
        s["status_repo"].save(_create_player_status(buyer_id, 1000, spot_id_val, coord))
        buyer_inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(buyer_id))
        s["inv_repo"].save(buyer_inv)

        cmd = PurchaseFromShopCommand(
            shop_id=shop_id.value,
            listing_id=listing_id.value,
            buyer_id=buyer_id,
            quantity=2,
        )
        result = s["service"].purchase_from_shop(cmd)
        assert result.success is True
        assert result.data["total_gold"] == 100
        assert s["status_repo"].find_by_id(PlayerId(buyer_id)).gold.value == 900
        assert s["status_repo"].find_by_id(PlayerId(owner_id)).gold.value == 100
        assert s["inv_repo"].find_by_id(PlayerId(buyer_id)).get_item_instance_id_by_slot(SlotId(0)) == item_id
        shop = s["shop_repo"].find_by_id(shop_id)
        assert shop.get_listing(listing_id) is None

    def test_purchase_from_shop_not_at_location_raises(self, setup_service):
        """購入者がショップのロケーションにいないと例外"""
        s = setup_service
        spot_id_val, loc_id_val = 1, 1
        coord = Coordinate(0, 0, 0)
        s["map_repo"].save(_create_physical_map_with_location(spot_id_val, loc_id_val, coord))

        owner_id, buyer_id = 1, 2
        shop_id = s["shop_repo"].generate_shop_id()
        shop = ShopAggregate.create(
            shop_id=shop_id,
            spot_id=SpotId(spot_id_val),
            location_area_id=LocationAreaId.create(loc_id_val),
            owner_id=PlayerId(owner_id),
        )
        item_spec = _create_stackable_item_spec()
        item_id = s["item_repo"].generate_item_instance_id()
        item = ItemAggregate.create(item_instance_id=item_id, item_spec=item_spec, quantity=1)
        s["item_repo"].save(item)
        listing_id = s["shop_repo"].generate_listing_id()
        shop.list_item(
            listing_id=listing_id,
            item_instance_id=item_id,
            price_per_unit=ShopListingPrice.of(50),
            listed_by=PlayerId(owner_id),
        )
        s["shop_repo"].save(shop)
        s["status_repo"].save(_create_player_status(owner_id, 0))
        s["status_repo"].save(_create_player_status(buyer_id, 1000))
        buyer_inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(buyer_id))
        s["inv_repo"].save(buyer_inv)

        cmd = PurchaseFromShopCommand(
            shop_id=shop_id.value,
            listing_id=listing_id.value,
            buyer_id=buyer_id,
            quantity=1,
        )
        with pytest.raises(NotAtShopLocationException):
            s["service"].purchase_from_shop(cmd)

    def test_purchase_from_shop_insufficient_stock_raises(self, setup_service):
        """在庫不足で購入すると例外"""
        s = setup_service
        spot_id_val, loc_id_val = 1, 1
        coord = Coordinate(0, 0, 0)
        s["map_repo"].save(_create_physical_map_with_location(spot_id_val, loc_id_val, coord))
        owner_id, buyer_id = 1, 2
        shop_id = s["shop_repo"].generate_shop_id()
        shop = ShopAggregate.create(
            shop_id=shop_id,
            spot_id=SpotId(spot_id_val),
            location_area_id=LocationAreaId.create(loc_id_val),
            owner_id=PlayerId(owner_id),
        )
        item_spec = _create_stackable_item_spec()
        item_id = s["item_repo"].generate_item_instance_id()
        item = ItemAggregate.create(item_instance_id=item_id, item_spec=item_spec, quantity=2)
        s["item_repo"].save(item)
        listing_id = s["shop_repo"].generate_listing_id()
        shop.list_item(
            listing_id=listing_id,
            item_instance_id=item_id,
            price_per_unit=ShopListingPrice.of(50),
            listed_by=PlayerId(owner_id),
        )
        s["shop_repo"].save(shop)
        s["status_repo"].save(_create_player_status(owner_id, 0))
        s["status_repo"].save(_create_player_status(buyer_id, 1000, spot_id_val, coord))
        buyer_inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(buyer_id))
        s["inv_repo"].save(buyer_inv)

        cmd = PurchaseFromShopCommand(
            shop_id=shop_id.value,
            listing_id=listing_id.value,
            buyer_id=buyer_id,
            quantity=5,
        )
        with pytest.raises(InsufficientStockForPurchaseException):
            s["service"].purchase_from_shop(cmd)

    def test_purchase_from_shop_partial_quantity_success(self, setup_service):
        """部分購入が成功する（スタック可能・耐久度なし）"""
        s = setup_service
        spot_id_val, loc_id_val = 1, 1
        coord = Coordinate(0, 0, 0)
        s["map_repo"].save(_create_physical_map_with_location(spot_id_val, loc_id_val, coord))
        owner_id, buyer_id = 1, 2
        shop_id = s["shop_repo"].generate_shop_id()
        shop = ShopAggregate.create(
            shop_id=shop_id,
            spot_id=SpotId(spot_id_val),
            location_area_id=LocationAreaId.create(loc_id_val),
            owner_id=PlayerId(owner_id),
        )
        item_spec = _create_stackable_item_spec()
        item_id = s["item_repo"].generate_item_instance_id()
        item = ItemAggregate.create(item_instance_id=item_id, item_spec=item_spec, quantity=10)
        s["item_repo"].save(item)
        listing_id = s["shop_repo"].generate_listing_id()
        shop.list_item(
            listing_id=listing_id,
            item_instance_id=item_id,
            price_per_unit=ShopListingPrice.of(10),
            listed_by=PlayerId(owner_id),
        )
        s["shop_repo"].save(shop)
        s["status_repo"].save(_create_player_status(owner_id, 0))
        s["status_repo"].save(_create_player_status(buyer_id, 500, spot_id_val, coord))
        buyer_inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(buyer_id))
        s["inv_repo"].save(buyer_inv)

        cmd = PurchaseFromShopCommand(
            shop_id=shop_id.value,
            listing_id=listing_id.value,
            buyer_id=buyer_id,
            quantity=3,
        )
        result = s["service"].purchase_from_shop(cmd)
        assert result.success is True
        assert result.data["total_gold"] == 30
        remaining = s["item_repo"].find_by_id(item_id)
        assert remaining is not None
        assert remaining.quantity == 7
        buyer_inv = s["inv_repo"].find_by_id(PlayerId(buyer_id))
        new_slot_item = buyer_inv.get_item_instance_id_by_slot(SlotId(0))
        assert new_slot_item is not None
        assert new_slot_item != item_id
        new_item = s["item_repo"].find_by_id(new_slot_item)
        assert new_item.quantity == 3

    def test_purchase_quantity_zero_raises(self, setup_service):
        """購入数0で例外"""
        s = setup_service
        shop_id = s["shop_repo"].generate_shop_id()
        shop = ShopAggregate.create(
            shop_id=shop_id,
            spot_id=SpotId(1),
            location_area_id=LocationAreaId.create(1),
            owner_id=PlayerId(1),
        )
        s["shop_repo"].save(shop)
        listing_id = s["shop_repo"].generate_listing_id()
        shop.list_item(
            listing_id=listing_id,
            item_instance_id=ItemInstanceId(1),
            price_per_unit=ShopListingPrice.of(10),
            listed_by=PlayerId(1),
        )
        s["shop_repo"].save(shop)
        cmd = PurchaseFromShopCommand(
            shop_id=shop_id.value,
            listing_id=listing_id.value,
            buyer_id=2,
            quantity=0,
        )
        with pytest.raises(ShopCommandException):
            s["service"].purchase_from_shop(cmd)

    def test_purchase_from_shop_shop_not_found_raises(self, setup_service):
        """存在しないショップから購入すると例外"""
        s = setup_service
        spot_id_val, loc_id_val = 1, 1
        coord = Coordinate(0, 0, 0)
        s["map_repo"].save(_create_physical_map_with_location(spot_id_val, loc_id_val, coord))
        s["status_repo"].save(_create_player_status(2, 1000, spot_id_val, coord))
        buyer_inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(2))
        s["inv_repo"].save(buyer_inv)
        cmd = PurchaseFromShopCommand(
            shop_id=999,
            listing_id=1,
            buyer_id=2,
            quantity=1,
        )
        with pytest.raises(ShopNotFoundForCommandException):
            s["service"].purchase_from_shop(cmd)

    def test_purchase_from_shop_listing_not_found_raises(self, setup_service):
        """存在しないリストを購入すると例外"""
        s = setup_service
        spot_id_val, loc_id_val = 1, 1
        coord = Coordinate(0, 0, 0)
        s["map_repo"].save(_create_physical_map_with_location(spot_id_val, loc_id_val, coord))
        owner_id, buyer_id = 1, 2
        shop_id = s["shop_repo"].generate_shop_id()
        shop = ShopAggregate.create(
            shop_id=shop_id,
            spot_id=SpotId(spot_id_val),
            location_area_id=LocationAreaId.create(loc_id_val),
            owner_id=PlayerId(owner_id),
        )
        s["shop_repo"].save(shop)
        s["status_repo"].save(_create_player_status(owner_id, 0))
        s["status_repo"].save(_create_player_status(buyer_id, 1000, spot_id_val, coord))
        buyer_inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(buyer_id))
        s["inv_repo"].save(buyer_inv)
        cmd = PurchaseFromShopCommand(
            shop_id=shop_id.value,
            listing_id=999,
            buyer_id=buyer_id,
            quantity=1,
        )
        with pytest.raises(ListingNotFoundForCommandException):
            s["service"].purchase_from_shop(cmd)

    def test_purchase_from_shop_insufficient_gold_raises(self, setup_service):
        """購入者ゴールド不足で例外（ドメイン例外がラップされる）"""
        s = setup_service
        spot_id_val, loc_id_val = 1, 1
        coord = Coordinate(0, 0, 0)
        s["map_repo"].save(_create_physical_map_with_location(spot_id_val, loc_id_val, coord))
        owner_id, buyer_id = 1, 2
        shop_id = s["shop_repo"].generate_shop_id()
        shop = ShopAggregate.create(
            shop_id=shop_id,
            spot_id=SpotId(spot_id_val),
            location_area_id=LocationAreaId.create(loc_id_val),
            owner_id=PlayerId(owner_id),
        )
        item_spec = _create_stackable_item_spec()
        item_id = s["item_repo"].generate_item_instance_id()
        item = ItemAggregate.create(item_instance_id=item_id, item_spec=item_spec, quantity=1)
        s["item_repo"].save(item)
        listing_id = s["shop_repo"].generate_listing_id()
        shop.list_item(
            listing_id=listing_id,
            item_instance_id=item_id,
            price_per_unit=ShopListingPrice.of(500),
            listed_by=PlayerId(owner_id),
        )
        s["shop_repo"].save(shop)
        s["status_repo"].save(_create_player_status(owner_id, 0))
        s["status_repo"].save(_create_player_status(buyer_id, 100, spot_id_val, coord))
        buyer_inv = PlayerInventoryAggregate.create_new_inventory(PlayerId(buyer_id))
        s["inv_repo"].save(buyer_inv)
        cmd = PurchaseFromShopCommand(
            shop_id=shop_id.value,
            listing_id=listing_id.value,
            buyer_id=buyer_id,
            quantity=1,
        )
        with pytest.raises(ShopCommandException) as exc_info:
            s["service"].purchase_from_shop(cmd)
        assert "ゴールド" in str(exc_info.value) or "gold" in str(exc_info.value).lower()

