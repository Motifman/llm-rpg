import pytest
from datetime import datetime
from unittest.mock import Mock

from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.trade.aggregate.trade_aggregate import TradeAggregate
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus
from ai_rpg_world.domain.trade.exception.trade_exception import (
    InvalidTradeStatusException,
    CannotAcceptOwnTradeException,
    CannotAcceptTradeWithOtherPlayerException,
    CannotCancelTradeWithOtherPlayerException,
)
from ai_rpg_world.domain.trade.event.trade_event import (
    TradeOfferedEvent,
    TradeAcceptedEvent,
    TradeCancelledEvent,
)
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from ai_rpg_world.domain.trade.value_object.trade_scope import TradeScope
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId


class TestTradeAggregate:
    """TradeAggregateのテスト"""

    @pytest.fixture
    def trade_id(self) -> TradeId:
        """テスト用取引ID"""
        return TradeId(1)

    @pytest.fixture
    def seller_id(self) -> PlayerId:
        """テスト用出品者ID"""
        return PlayerId(1)

    @pytest.fixture
    def buyer_id(self) -> PlayerId:
        """テスト用購入者ID"""
        return PlayerId(2)

    @pytest.fixture
    def other_player_id(self) -> PlayerId:
        """テスト用他のプレイヤーID"""
        return PlayerId(3)

    @pytest.fixture
    def offered_item_id(self) -> ItemInstanceId:
        """テスト用提供アイテムID"""
        return ItemInstanceId(1)

    @pytest.fixture
    def requested_gold(self) -> TradeRequestedGold:
        """テスト用要求金額"""
        return TradeRequestedGold.of(100)

    @pytest.fixture
    def created_at(self) -> datetime:
        """テスト用作成日時"""
        return datetime(2024, 1, 1, 12, 0, 0)

    @pytest.fixture
    def global_trade_scope(self) -> TradeScope:
        """テスト用グローバル取引範囲"""
        return TradeScope.global_trade()

    @pytest.fixture
    def direct_trade_scope(self, buyer_id: PlayerId) -> TradeScope:
        """テスト用直接取引範囲"""
        return TradeScope.direct_trade(buyer_id)

    @pytest.fixture
    def active_global_trade(
        self,
        trade_id: TradeId,
        seller_id: PlayerId,
        offered_item_id: ItemInstanceId,
        requested_gold: TradeRequestedGold,
        created_at: datetime,
        global_trade_scope: TradeScope,
    ) -> TradeAggregate:
        """アクティブなグローバル取引"""
        return TradeAggregate(
            trade_id=trade_id,
            seller_id=seller_id,
            offered_item_id=offered_item_id,
            requested_gold=requested_gold,
            created_at=created_at,
            trade_scope=global_trade_scope,
            status=TradeStatus.ACTIVE,
            version=0,
            buyer_id=None,
        )

    @pytest.fixture
    def active_direct_trade(
        self,
        trade_id: TradeId,
        seller_id: PlayerId,
        offered_item_id: ItemInstanceId,
        requested_gold: TradeRequestedGold,
        created_at: datetime,
        direct_trade_scope: TradeScope,
    ) -> TradeAggregate:
        """アクティブな直接取引"""
        return TradeAggregate(
            trade_id=trade_id,
            seller_id=seller_id,
            offered_item_id=offered_item_id,
            requested_gold=requested_gold,
            created_at=created_at,
            trade_scope=direct_trade_scope,
            status=TradeStatus.ACTIVE,
            version=0,
            buyer_id=None,
        )

    @pytest.fixture
    def completed_trade(
        self,
        trade_id: TradeId,
        seller_id: PlayerId,
        offered_item_id: ItemInstanceId,
        requested_gold: TradeRequestedGold,
        created_at: datetime,
        global_trade_scope: TradeScope,
        buyer_id: PlayerId,
    ) -> TradeAggregate:
        """完了した取引"""
        return TradeAggregate(
            trade_id=trade_id,
            seller_id=seller_id,
            offered_item_id=offered_item_id,
            requested_gold=requested_gold,
            created_at=created_at,
            trade_scope=global_trade_scope,
            status=TradeStatus.COMPLETED,
            version=1,
            buyer_id=buyer_id,
        )

    @pytest.fixture
    def cancelled_trade(
        self,
        trade_id: TradeId,
        seller_id: PlayerId,
        offered_item_id: ItemInstanceId,
        requested_gold: TradeRequestedGold,
        created_at: datetime,
        global_trade_scope: TradeScope,
    ) -> TradeAggregate:
        """キャンセルされた取引"""
        return TradeAggregate(
            trade_id=trade_id,
            seller_id=seller_id,
            offered_item_id=offered_item_id,
            requested_gold=requested_gold,
            created_at=created_at,
            trade_scope=global_trade_scope,
            status=TradeStatus.CANCELLED,
            version=1,
            buyer_id=None,
        )

    class TestCreateNewTrade:
        """create_new_tradeメソッドのテスト"""

        def test_create_global_trade_success(
            self,
            trade_id: TradeId,
            seller_id: PlayerId,
            offered_item_id: ItemInstanceId,
            requested_gold: TradeRequestedGold,
            created_at: datetime,
            global_trade_scope: TradeScope,
        ):
            """グローバル取引の新規作成が成功する"""
            # When
            trade = TradeAggregate.create_new_trade(
                trade_id=trade_id,
                seller_id=seller_id,
                offered_item_id=offered_item_id,
                requested_gold=requested_gold,
                created_at=created_at,
                trade_scope=global_trade_scope,
            )

            # Then
            assert trade.trade_id == trade_id
            assert trade.seller_id == seller_id
            assert trade.offered_item_id == offered_item_id
            assert trade.requested_gold == requested_gold
            assert trade.created_at == created_at
            assert trade.trade_scope == global_trade_scope
            assert trade.status == TradeStatus.ACTIVE
            assert trade.buyer_id is None
            assert trade.version == 0

        def test_create_direct_trade_success(
            self,
            trade_id: TradeId,
            seller_id: PlayerId,
            offered_item_id: ItemInstanceId,
            requested_gold: TradeRequestedGold,
            created_at: datetime,
            direct_trade_scope: TradeScope,
        ):
            """直接取引の新規作成が成功する"""
            # When
            trade = TradeAggregate.create_new_trade(
                trade_id=trade_id,
                seller_id=seller_id,
                offered_item_id=offered_item_id,
                requested_gold=requested_gold,
                created_at=created_at,
                trade_scope=direct_trade_scope,
            )

            # Then
            assert trade.trade_id == trade_id
            assert trade.seller_id == seller_id
            assert trade.offered_item_id == offered_item_id
            assert trade.requested_gold == requested_gold
            assert trade.created_at == created_at
            assert trade.trade_scope == direct_trade_scope
            assert trade.status == TradeStatus.ACTIVE
            assert trade.buyer_id is None
            assert trade.version == 0

        def test_create_trade_adds_trade_offered_event(
            self,
            trade_id: TradeId,
            seller_id: PlayerId,
            offered_item_id: ItemInstanceId,
            requested_gold: TradeRequestedGold,
            created_at: datetime,
            global_trade_scope: TradeScope,
        ):
            """新規取引作成時にTradeOfferedEventが発行される"""
            # When
            trade = TradeAggregate.create_new_trade(
                trade_id=trade_id,
                seller_id=seller_id,
                offered_item_id=offered_item_id,
                requested_gold=requested_gold,
                created_at=created_at,
                trade_scope=global_trade_scope,
            )

            # Then
            events = trade.get_events()
            assert len(events) == 1
            assert isinstance(events[0], TradeOfferedEvent)
            assert events[0].aggregate_id == trade_id
            assert events[0].aggregate_type == "TradeAggregate"
            assert events[0].seller_id == seller_id
            assert events[0].offered_item_id == offered_item_id
            assert events[0].requested_gold == requested_gold
            assert events[0].trade_scope == global_trade_scope

    class TestIsActive:
        """is_activeメソッドのテスト"""

        def test_active_trade_returns_true(self, active_global_trade: TradeAggregate):
            """アクティブな取引はTrueを返す"""
            # When & Then
            assert active_global_trade.is_active() is True

        def test_completed_trade_returns_false(self, completed_trade: TradeAggregate):
            """完了した取引はFalseを返す"""
            # When & Then
            assert completed_trade.is_active() is False

        def test_cancelled_trade_returns_false(self, cancelled_trade: TradeAggregate):
            """キャンセルされた取引はFalseを返す"""
            # When & Then
            assert cancelled_trade.is_active() is False

    class TestIsDirectTrade:
        """is_direct_tradeメソッドのテスト"""

        def test_global_trade_returns_false(self, active_global_trade: TradeAggregate):
            """グローバル取引はFalseを返す"""
            # When & Then
            assert active_global_trade.is_direct_trade() is False

        def test_direct_trade_returns_true(self, active_direct_trade: TradeAggregate):
            """直接取引はTrueを返す"""
            # When & Then
            assert active_direct_trade.is_direct_trade() is True

    class TestIsForPlayer:
        """is_for_playerメソッドのテスト"""

        def test_global_trade_always_returns_false(
            self, active_global_trade: TradeAggregate, buyer_id: PlayerId
        ):
            """グローバル取引は常にFalseを返す"""
            # When & Then
            assert active_global_trade.is_for_player(buyer_id) is False

        def test_direct_trade_with_target_player_returns_true(self, active_direct_trade: TradeAggregate):
            """対象プレイヤーへの直接取引はTrueを返す"""
            # Given
            target_player_id = active_direct_trade.trade_scope.target_player_id

            # When & Then
            assert active_direct_trade.is_for_player(target_player_id) is True

        def test_direct_trade_with_other_player_returns_false(
            self, active_direct_trade: TradeAggregate, other_player_id: PlayerId
        ):
            """対象外プレイヤーへの直接取引はFalseを返す"""
            # When & Then
            assert active_direct_trade.is_for_player(other_player_id) is False

    class TestCanBeAcceptedBy:
        """can_be_accepted_byメソッドのテスト"""

        def test_inactive_trade_returns_false(self, completed_trade: TradeAggregate, buyer_id: PlayerId):
            """非アクティブな取引はFalseを返す"""
            # When & Then
            assert completed_trade.can_be_accepted_by(buyer_id) is False

        def test_seller_cannot_accept_own_trade(self, active_global_trade: TradeAggregate):
            """出品者は自分の取引を受け入れられない"""
            # Given
            seller_id = active_global_trade.seller_id

            # When & Then
            assert active_global_trade.can_be_accepted_by(seller_id) is False

        def test_direct_trade_wrong_player_returns_false(
            self, active_direct_trade: TradeAggregate, other_player_id: PlayerId
        ):
            """直接取引で対象外プレイヤーは受け入れられない"""
            # When & Then
            assert active_direct_trade.can_be_accepted_by(other_player_id) is False

        def test_global_trade_other_player_can_accept(
            self, active_global_trade: TradeAggregate, buyer_id: PlayerId
        ):
            """グローバル取引は他のプレイヤーが受け入れられる"""
            # When & Then
            assert active_global_trade.can_be_accepted_by(buyer_id) is True

        def test_direct_trade_target_player_can_accept(self, active_direct_trade: TradeAggregate):
            """直接取引は対象プレイヤーが受け入れられる"""
            # Given
            target_player_id = active_direct_trade.trade_scope.target_player_id

            # When & Then
            assert active_direct_trade.can_be_accepted_by(target_player_id) is True

    class TestAcceptBy:
        """accept_byメソッドのテスト"""

        def test_successful_acceptance_of_global_trade(
            self, active_global_trade: TradeAggregate, buyer_id: PlayerId
        ):
            """グローバル取引の受託が成功する"""
            # When
            active_global_trade.accept_by(buyer_id)

            # Then
            assert active_global_trade.buyer_id == buyer_id
            assert active_global_trade.status == TradeStatus.COMPLETED

        def test_successful_acceptance_of_direct_trade(self, active_direct_trade: TradeAggregate):
            """直接取引の受託が成功する"""
            # Given
            target_player_id = active_direct_trade.trade_scope.target_player_id

            # When
            active_direct_trade.accept_by(target_player_id)

            # Then
            assert active_direct_trade.buyer_id == target_player_id
            assert active_direct_trade.status == TradeStatus.COMPLETED

        def test_accept_inactive_trade_raises_exception(self, completed_trade: TradeAggregate, buyer_id: PlayerId):
            """非アクティブな取引を受託しようとすると例外が発生する"""
            # When & Then
            with pytest.raises(InvalidTradeStatusException):
                completed_trade.accept_by(buyer_id)

        def test_seller_accept_own_trade_raises_exception(self, active_global_trade: TradeAggregate):
            """出品者が自分の取引を受託しようとすると例外が発生する"""
            # Given
            seller_id = active_global_trade.seller_id

            # When & Then
            with pytest.raises(CannotAcceptOwnTradeException):
                active_global_trade.accept_by(seller_id)

        def test_wrong_player_accept_direct_trade_raises_exception(
            self, active_direct_trade: TradeAggregate, other_player_id: PlayerId
        ):
            """直接取引で対象外プレイヤーが受託しようとすると例外が発生する"""
            # When & Then
            with pytest.raises(CannotAcceptTradeWithOtherPlayerException):
                active_direct_trade.accept_by(other_player_id)

        def test_accept_adds_trade_accepted_event(self, active_global_trade: TradeAggregate, buyer_id: PlayerId):
            """取引受託時にTradeAcceptedEventが発行される"""
            # When
            active_global_trade.accept_by(buyer_id)

            # Then
            events = active_global_trade.get_events()
            assert len(events) == 1
            assert isinstance(events[0], TradeAcceptedEvent)
            assert events[0].aggregate_id == active_global_trade.trade_id
            assert events[0].aggregate_type == "TradeAggregate"
            assert events[0].buyer_id == buyer_id

        def test_accept_cancelled_trade_raises_exception(self, cancelled_trade: TradeAggregate, buyer_id: PlayerId):
            """キャンセル済み取引を受託しようとすると例外が発生する"""
            # When & Then
            with pytest.raises(InvalidTradeStatusException):
                cancelled_trade.accept_by(buyer_id)

    class TestCancelBy:
        """cancel_byメソッドのテスト"""

        def test_successful_cancellation(self, active_global_trade: TradeAggregate):
            """取引のキャンセルが成功する"""
            # Given
            seller_id = active_global_trade.seller_id

            # When
            active_global_trade.cancel_by(seller_id)

            # Then
            assert active_global_trade.status == TradeStatus.CANCELLED

        def test_cancel_inactive_trade_raises_exception(self, completed_trade: TradeAggregate):
            """非アクティブな取引をキャンセルしようとすると例外が発生する"""
            # Given
            seller_id = completed_trade.seller_id

            # When & Then
            with pytest.raises(InvalidTradeStatusException):
                completed_trade.cancel_by(seller_id)

        def test_non_seller_cancel_trade_raises_exception(
            self, active_global_trade: TradeAggregate, buyer_id: PlayerId
        ):
            """出品者以外が取引をキャンセルしようとすると例外が発生する"""
            # When & Then
            with pytest.raises(CannotCancelTradeWithOtherPlayerException):
                active_global_trade.cancel_by(buyer_id)

        def test_cancel_adds_trade_cancelled_event(self, active_global_trade: TradeAggregate):
            """取引キャンセル時にTradeCancelledEventが発行される"""
            # Given
            seller_id = active_global_trade.seller_id

            # When
            active_global_trade.cancel_by(seller_id)

            # Then
            events = active_global_trade.get_events()
            assert len(events) == 1
            assert isinstance(events[0], TradeCancelledEvent)
            assert events[0].aggregate_id == active_global_trade.trade_id
            assert events[0].aggregate_type == "TradeAggregate"

        def test_cancel_cancelled_trade_raises_exception(self, cancelled_trade: TradeAggregate):
            """キャンセル済み取引を再度キャンセルしようとすると例外が発生する"""
            # Given
            seller_id = cancelled_trade.seller_id

            # When & Then
            with pytest.raises(InvalidTradeStatusException):
                cancelled_trade.cancel_by(seller_id)

    class TestDomainEvents:
        """ドメインイベント関連のテスト"""

        def test_events_are_accumulated(
            self,
            trade_id: TradeId,
            seller_id: PlayerId,
            offered_item_id: ItemInstanceId,
            requested_gold: TradeRequestedGold,
            created_at: datetime,
            global_trade_scope: TradeScope,
            buyer_id: PlayerId,
        ):
            """イベントが正しく溜められる"""
            # Given - 新規取引作成
            trade = TradeAggregate.create_new_trade(
                trade_id=trade_id,
                seller_id=seller_id,
                offered_item_id=offered_item_id,
                requested_gold=requested_gold,
                created_at=created_at,
                trade_scope=global_trade_scope,
            )

            # When - 受託
            trade.accept_by(buyer_id)

            # Then - 2つのイベントが溜まっている
            events = trade.get_events()
            assert len(events) == 2
            assert isinstance(events[0], TradeOfferedEvent)
            assert isinstance(events[1], TradeAcceptedEvent)

        def test_clear_events_removes_all_events(
            self,
            trade_id: TradeId,
            seller_id: PlayerId,
            offered_item_id: ItemInstanceId,
            requested_gold: TradeRequestedGold,
            created_at: datetime,
            global_trade_scope: TradeScope,
        ):
            """clear_eventsでイベントがクリアされる"""
            # Given - 新規取引作成
            trade = TradeAggregate.create_new_trade(
                trade_id=trade_id,
                seller_id=seller_id,
                offered_item_id=offered_item_id,
                requested_gold=requested_gold,
                created_at=created_at,
                trade_scope=global_trade_scope,
            )

            # When - イベントクリア
            trade.clear_events()

            # Then - イベントが空
            events = trade.get_events()
            assert len(events) == 0

        def test_get_events_returns_copy_not_reference(self, active_global_trade: TradeAggregate):
            """get_eventsが参照ではなくコピーを返す"""
            # Given
            active_global_trade.add_event(Mock())  # モックイベントを追加

            # When
            events1 = active_global_trade.get_events()
            events2 = active_global_trade.get_events()

            # Then - 別々のオブジェクト
            assert events1 is not events2
            assert events1 == events2

        def test_trade_offered_event_contains_all_fields(
            self,
            trade_id: TradeId,
            seller_id: PlayerId,
            offered_item_id: ItemInstanceId,
            requested_gold: TradeRequestedGold,
            created_at: datetime,
            global_trade_scope: TradeScope,
        ):
            """TradeOfferedEventが全てのフィールドを含む"""
            # When
            trade = TradeAggregate.create_new_trade(
                trade_id=trade_id,
                seller_id=seller_id,
                offered_item_id=offered_item_id,
                requested_gold=requested_gold,
                created_at=created_at,
                trade_scope=global_trade_scope,
            )

            # Then
            events = trade.get_events()
            event = events[0]
            assert isinstance(event, TradeOfferedEvent)
            assert event.aggregate_id == trade_id
            assert event.aggregate_type == "TradeAggregate"
            assert event.seller_id == seller_id
            assert event.offered_item_id == offered_item_id
            assert event.requested_gold == requested_gold
            assert event.trade_scope == global_trade_scope
            # 基底クラスのフィールドも確認
            assert hasattr(event, 'occurred_at')
            assert hasattr(event, 'event_id')

        def test_trade_accepted_event_contains_all_fields(
            self,
            active_global_trade: TradeAggregate,
            buyer_id: PlayerId,
        ):
            """TradeAcceptedEventが全てのフィールドを含む"""
            # When
            active_global_trade.accept_by(buyer_id)

            # Then
            events = active_global_trade.get_events()
            event = events[0]
            assert isinstance(event, TradeAcceptedEvent)
            assert event.aggregate_id == active_global_trade.trade_id
            assert event.aggregate_type == "TradeAggregate"
            assert event.buyer_id == buyer_id
            # 基底クラスのフィールドも確認
            assert hasattr(event, 'occurred_at')
            assert hasattr(event, 'event_id')

        def test_trade_cancelled_event_contains_all_fields(self, active_global_trade: TradeAggregate):
            """TradeCancelledEventが全てのフィールドを含む"""
            # Given
            seller_id = active_global_trade.seller_id

            # When
            active_global_trade.cancel_by(seller_id)

            # Then
            events = active_global_trade.get_events()
            event = events[0]
            assert isinstance(event, TradeCancelledEvent)
            assert event.aggregate_id == active_global_trade.trade_id
            assert event.aggregate_type == "TradeAggregate"
            # 基底クラスのフィールドも確認
            assert hasattr(event, 'occurred_at')
            assert hasattr(event, 'event_id')

