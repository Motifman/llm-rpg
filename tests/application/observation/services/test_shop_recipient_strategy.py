"""ShopRecipientStrategy のテスト（正常系・境界・例外）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.player_audience_query_service import (
    PlayerAudienceQueryService,
)
from ai_rpg_world.application.observation.services.recipient_strategies.shop_recipient_strategy import (
    ShopRecipientStrategy,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.shop.event.shop_event import (
    ShopClosedEvent,
    ShopCreatedEvent,
    ShopItemListedEvent,
    ShopItemPurchasedEvent,
    ShopItemUnlistedEvent,
)
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.shop.value_object.shop_listing_price import ShopListingPrice
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)


def _make_audience_query(status_repo: PlayerStatusRepository) -> PlayerAudienceQueryService:
    """テスト用 PlayerAudienceQueryService"""
    return PlayerAudienceQueryService(player_status_repository=status_repo)


class TestShopRecipientStrategyNormal:
    """ShopRecipientStrategy 正常系テスト"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def status_repo(self, data_store):
        return InMemoryPlayerStatusRepository(data_store=data_store)

    @pytest.fixture
    def audience_query(self, status_repo):
        return _make_audience_query(status_repo)

    def test_shop_created_returns_owner_and_players_at_spot(self, audience_query):
        """ShopCreatedEvent: オーナーと同一スポットのプレイヤーが配信先"""
        audience_query = MagicMock()
        audience_query.players_at_spot.return_value = [PlayerId(2), PlayerId(3)]
        strategy = ShopRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
        )
        event = ShopCreatedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(1),
            owner_id=PlayerId(1),
        )
        result = strategy.resolve(event)
        assert len(result) == 3
        assert result[0].value == 1
        assert {p.value for p in result} == {1, 2, 3}
        audience_query.players_at_spot.assert_called_once_with(SpotId(10))

    def test_shop_item_purchased_returns_buyer_and_seller(self, audience_query):
        """ShopItemPurchasedEvent: 購入者と売り手が配信先"""
        strategy = ShopRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
        )
        event = ShopItemPurchasedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            listing_id=ShopListingId(1),
            item_instance_id=ItemInstanceId(1),
            buyer_id=PlayerId(5),
            quantity=2,
            total_gold=200,
            seller_id=PlayerId(3),
        )
        result = strategy.resolve(event)
        assert len(result) == 2
        assert result[0].value == 5
        assert result[1].value == 3
        assert {p.value for p in result} == {3, 5}

    def test_shop_item_listed_returns_players_at_spot_when_shop_found(self, audience_query):
        """ShopItemListedEvent: ショップが見つかるとそのスポットのプレイヤーが配信先"""
        shop_repo = MagicMock()
        shop = MagicMock()
        shop.spot_id = SpotId(7)
        shop_repo.find_by_id.return_value = shop
        audience_query = MagicMock()
        audience_query.players_at_spot.return_value = [PlayerId(1), PlayerId(2), PlayerId(4)]
        strategy = ShopRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            shop_repository=shop_repo,
        )
        event = ShopItemListedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            listing_id=ShopListingId(1),
            item_instance_id=ItemInstanceId(1),
            price_per_unit=ShopListingPrice.of(100),
            listed_by=PlayerId(1),
        )
        result = strategy.resolve(event)
        assert len(result) == 3
        assert {p.value for p in result} == {1, 2, 4}
        audience_query.players_at_spot.assert_called_once_with(SpotId(7))

    def test_shop_item_unlisted_returns_listed_by_when_shop_not_found(self, audience_query):
        """ShopItemUnlistedEvent: ショップが見つからないときは unlisted_by のみ"""
        shop_repo = MagicMock()
        shop_repo.find_by_id.return_value = None
        strategy = ShopRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            shop_repository=shop_repo,
        )
        event = ShopItemUnlistedEvent.create(
            aggregate_id=ShopId(99),
            aggregate_type="ShopAggregate",
            listing_id=ShopListingId(1),
            unlisted_by=PlayerId(3),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 3

    def test_shop_closed_returns_closed_by_when_shop_not_found(self, audience_query):
        """ShopClosedEvent: ショップが見つからないときは closed_by のみ"""
        shop_repo = MagicMock()
        shop_repo.find_by_id.return_value = None
        strategy = ShopRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            shop_repository=shop_repo,
        )
        event = ShopClosedEvent.create(
            aggregate_id=ShopId(99),
            aggregate_type="ShopAggregate",
            closed_by=PlayerId(5),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 5


class TestShopRecipientStrategyExceptions:
    """ShopRecipientStrategy 例外・境界テスト"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def status_repo(self, data_store):
        return InMemoryPlayerStatusRepository(data_store=data_store)

    @pytest.fixture
    def audience_query(self, status_repo):
        return _make_audience_query(status_repo)

    def test_spot_id_from_shop_returns_none_when_repository_none(self, audience_query):
        """_spot_id_from_shop: リポジトリが None のとき None"""
        strategy = ShopRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            shop_repository=None,
        )
        event = ShopItemListedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            listing_id=ShopListingId(1),
            item_instance_id=ItemInstanceId(1),
            price_per_unit=ShopListingPrice.of(100),
            listed_by=PlayerId(1),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 1

    def test_resolve_propagates_repository_exception(self, audience_query):
        """resolve: リポジトリが例外を投げた場合、その例外が伝播する"""
        shop_repo = MagicMock()
        shop_repo.find_by_id.side_effect = RuntimeError("Shop find failed")
        audience_query = MagicMock()
        audience_query.players_at_spot.return_value = []
        strategy = ShopRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            shop_repository=shop_repo,
        )
        event = ShopItemListedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            listing_id=ShopListingId(1),
            item_instance_id=ItemInstanceId(1),
            price_per_unit=ShopListingPrice.of(100),
            listed_by=PlayerId(1),
        )
        with pytest.raises(RuntimeError, match="Shop find failed"):
            strategy.resolve(event)

    def test_shop_created_with_empty_players_at_spot_returns_owner_only(self, audience_query):
        """ShopCreatedEvent: 同一スポットに他プレイヤーがいないときオーナーのみ"""
        audience_query = MagicMock()
        audience_query.players_at_spot.return_value = []
        strategy = ShopRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
        )
        event = ShopCreatedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(1),
            owner_id=PlayerId(1),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 1


class TestShopRecipientStrategySupports:
    """ShopRecipientStrategy supports テスト"""

    @pytest.fixture
    def strategy(self):
        return ShopRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=MagicMock(),
        )

    def test_supports_shop_created_event(self, strategy):
        """ShopCreatedEvent を supports"""
        event = ShopCreatedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            spot_id=SpotId(1),
            location_area_id=LocationAreaId(1),
            owner_id=PlayerId(1),
        )
        assert strategy.supports(event) is True

    def test_supports_shop_item_purchased_event(self, strategy):
        """ShopItemPurchasedEvent を supports"""
        event = ShopItemPurchasedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            listing_id=ShopListingId(1),
            item_instance_id=ItemInstanceId(1),
            buyer_id=PlayerId(1),
            quantity=1,
            total_gold=100,
            seller_id=PlayerId(2),
        )
        assert strategy.supports(event) is True

    def test_supports_returns_false_for_unknown_event(self, strategy):
        """未知のイベントでは False"""
        class UnknownEvent:
            pass
        assert strategy.supports(UnknownEvent()) is False
