"""TradeRecipientStrategy のテスト（正常系・境界・例外）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies.trade_recipient_strategy import (
    TradeRecipientStrategy,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.event.trade_event import (
    TradeAcceptedEvent,
    TradeCancelledEvent,
    TradeDeclinedEvent,
    TradeOfferedEvent,
)
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from ai_rpg_world.domain.trade.value_object.trade_scope import TradeScope
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId


class TestTradeRecipientStrategyNormal:
    """TradeRecipientStrategy 正常系テスト"""

    @pytest.fixture
    def strategy(self):
        return TradeRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            trade_repository=None,
        )

    def test_trade_offered_global_returns_seller_only(self, strategy):
        """TradeOfferedEvent (グローバル): 出品者のみが配信先"""
        event = TradeOfferedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            seller_id=PlayerId(1),
            offered_item_id=ItemInstanceId(1),
            requested_gold=TradeRequestedGold.of(100),
            trade_scope=TradeScope.global_trade(),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 1

    def test_trade_offered_direct_returns_seller_and_target(self, strategy):
        """TradeOfferedEvent (直接): 出品者と対象プレイヤーが配信先"""
        event = TradeOfferedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            seller_id=PlayerId(1),
            offered_item_id=ItemInstanceId(1),
            requested_gold=TradeRequestedGold.of(100),
            trade_scope=TradeScope.direct_trade(PlayerId(2)),
        )
        result = strategy.resolve(event)
        assert len(result) == 2
        assert {p.value for p in result} == {1, 2}

    def test_trade_offered_direct_seller_equals_target_returns_seller_only(self, strategy):
        """TradeOfferedEvent (直接・出品者=対象): 出品者のみ（重複なし）"""
        event = TradeOfferedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            seller_id=PlayerId(1),
            offered_item_id=ItemInstanceId(1),
            requested_gold=TradeRequestedGold.of(100),
            trade_scope=TradeScope.direct_trade(PlayerId(1)),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 1

    def test_trade_accepted_returns_buyer_only_when_no_repo(self, strategy):
        """TradeAcceptedEvent: リポジトリが None のとき購入者のみ"""
        event = TradeAcceptedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            buyer_id=PlayerId(2),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 2

    def test_trade_accepted_returns_buyer_and_seller_when_different(self):
        """TradeAcceptedEvent: リポジトリあり・出品者≠購入者なら両方が配信先"""
        trade_repo = MagicMock()
        trade = MagicMock()
        trade.seller_id = PlayerId(1)
        trade_repo.find_by_id.return_value = trade
        strategy = TradeRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            trade_repository=trade_repo,
        )
        event = TradeAcceptedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            buyer_id=PlayerId(2),
        )
        result = strategy.resolve(event)
        assert len(result) == 2
        assert {p.value for p in result} == {1, 2}

    def test_trade_accepted_returns_buyer_only_when_seller_equals_buyer(self):
        """TradeAcceptedEvent: 出品者=購入者（不正想定）のとき購入者のみ"""
        trade_repo = MagicMock()
        trade = MagicMock()
        trade.seller_id = PlayerId(2)
        trade_repo.find_by_id.return_value = trade
        strategy = TradeRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            trade_repository=trade_repo,
        )
        event = TradeAcceptedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            buyer_id=PlayerId(2),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 2


class TestTradeRecipientStrategyExceptions:
    """TradeRecipientStrategy 例外・境界テスト"""

    def test_trade_cancelled_returns_empty_when_repository_none(self):
        """TradeCancelledEvent: リポジトリが None のとき空リスト"""
        strategy = TradeRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            trade_repository=None,
        )
        event = TradeCancelledEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
        )
        result = strategy.resolve(event)
        assert result == []

    def test_trade_cancelled_returns_empty_when_trade_not_found(self):
        """TradeCancelledEvent: 取引が find_by_id で見つからないとき空リスト"""
        trade_repo = MagicMock()
        trade_repo.find_by_id.return_value = None
        strategy = TradeRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            trade_repository=trade_repo,
        )
        event = TradeCancelledEvent.create(
            aggregate_id=TradeId(99),
            aggregate_type="TradeAggregate",
        )
        result = strategy.resolve(event)
        assert result == []

    def test_trade_cancelled_returns_seller_and_target_when_direct(self):
        """TradeCancelledEvent: 直接取引なら出品者と対象が配信先"""
        trade_repo = MagicMock()
        trade = MagicMock()
        trade.seller_id = PlayerId(1)
        trade.trade_scope = TradeScope.direct_trade(PlayerId(2))
        trade_repo.find_by_id.return_value = trade
        strategy = TradeRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            trade_repository=trade_repo,
        )
        event = TradeCancelledEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
        )
        result = strategy.resolve(event)
        assert len(result) == 2
        assert {p.value for p in result} == {1, 2}

    def test_trade_cancelled_returns_seller_only_when_global(self):
        """TradeCancelledEvent: グローバル取引なら出品者のみ"""
        trade_repo = MagicMock()
        trade = MagicMock()
        trade.seller_id = PlayerId(1)
        trade.trade_scope = TradeScope.global_trade()
        trade_repo.find_by_id.return_value = trade
        strategy = TradeRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            trade_repository=trade_repo,
        )
        event = TradeCancelledEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 1

    def test_trade_declined_returns_empty_when_repository_none(self):
        """TradeDeclinedEvent: リポジトリが None のとき空リスト"""
        strategy = TradeRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            trade_repository=None,
        )
        event = TradeDeclinedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            decliner_id=PlayerId(2),
        )
        result = strategy.resolve(event)
        assert result == []

    def test_trade_declined_returns_empty_when_trade_not_found(self):
        """TradeDeclinedEvent: 取引が find_by_id で見つからないとき空リスト"""
        trade_repo = MagicMock()
        trade_repo.find_by_id.return_value = None
        strategy = TradeRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            trade_repository=trade_repo,
        )
        event = TradeDeclinedEvent.create(
            aggregate_id=TradeId(99),
            aggregate_type="TradeAggregate",
            decliner_id=PlayerId(2),
        )
        result = strategy.resolve(event)
        assert result == []

    def test_trade_declined_returns_decliner_and_seller_when_different(self):
        """TradeDeclinedEvent: 断った人と出品者が異なるとき両方が配信先"""
        trade_repo = MagicMock()
        trade = MagicMock()
        trade.seller_id = PlayerId(1)
        trade_repo.find_by_id.return_value = trade
        strategy = TradeRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            trade_repository=trade_repo,
        )
        event = TradeDeclinedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            decliner_id=PlayerId(2),
        )
        result = strategy.resolve(event)
        assert len(result) == 2
        assert {p.value for p in result} == {1, 2}

    def test_trade_declined_returns_decliner_only_when_decliner_is_seller(self):
        """TradeDeclinedEvent: 断った人が出品者のとき出品者のみ"""
        trade_repo = MagicMock()
        trade = MagicMock()
        trade.seller_id = PlayerId(1)
        trade_repo.find_by_id.return_value = trade
        strategy = TradeRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            trade_repository=trade_repo,
        )
        event = TradeDeclinedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            decliner_id=PlayerId(1),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 1

    def test_resolve_propagates_repository_exception(self):
        """resolve: リポジトリが例外を投げた場合、その例外が伝播する"""
        trade_repo = MagicMock()
        trade_repo.find_by_id.side_effect = RuntimeError("DB connection failed")
        strategy = TradeRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            trade_repository=trade_repo,
        )
        event = TradeCancelledEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
        )
        with pytest.raises(RuntimeError, match="DB connection failed"):
            strategy.resolve(event)


class TestTradeRecipientStrategySupports:
    """TradeRecipientStrategy supports テスト"""

    @pytest.fixture
    def strategy(self):
        return TradeRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            trade_repository=None,
        )

    def test_supports_trade_offered_event(self, strategy):
        """TradeOfferedEvent を supports"""
        event = TradeOfferedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            seller_id=PlayerId(1),
            offered_item_id=ItemInstanceId(1),
            requested_gold=TradeRequestedGold.of(100),
            trade_scope=TradeScope.global_trade(),
        )
        assert strategy.supports(event) is True

    def test_supports_trade_accepted_event(self, strategy):
        """TradeAcceptedEvent を supports"""
        event = TradeAcceptedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            buyer_id=PlayerId(1),
        )
        assert strategy.supports(event) is True

    def test_supports_returns_false_for_unknown_event(self, strategy):
        """未知のイベントでは False"""
        class UnknownEvent:
            pass
        assert strategy.supports(UnknownEvent()) is False
