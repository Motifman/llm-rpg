"""TradeObservationFormatter の単体テスト。"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.trade_formatter import (
    TradeObservationFormatter,
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
from ai_rpg_world.domain.world.event.harvest_events import HarvestStartedEvent
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.common.value_object import WorldTick


def _make_context(
    player_profile_repository=None,
    item_repository=None,
) -> ObservationFormatterContext:
    """テスト用の ObservationFormatterContext を生成。"""
    name_resolver = ObservationNameResolver(
        spot_repository=None,
        player_profile_repository=player_profile_repository,
        item_spec_repository=None,
        item_repository=item_repository,
        shop_repository=None,
        guild_repository=None,
        monster_repository=None,
        skill_spec_repository=None,
        sns_user_repository=None,
    )
    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=item_repository,
    )


class TestTradeObservationFormatterCreation:
    """TradeObservationFormatter 生成のテスト"""

    def test_creates_with_context_only(self):
        """context のみで生成できる。"""
        ctx = _make_context()
        formatter = TradeObservationFormatter(ctx)
        assert formatter._context is ctx

    def test_format_method_exists(self):
        """format(event, recipient_player_id) が呼び出し可能。"""
        ctx = _make_context()
        formatter = TradeObservationFormatter(ctx)
        assert hasattr(formatter, "format")
        assert callable(formatter.format)


class TestTradeObservationFormatterTradeOffered:
    """TradeOfferedEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return TradeObservationFormatter(_make_context())

    def test_seller_sees_offered_message(self, formatter):
        """出品者は「出品しました」メッセージを見る。"""
        event = TradeOfferedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            seller_id=PlayerId(1),
            offered_item_id=ItemInstanceId(1),
            requested_gold=TradeRequestedGold.of(100),
            trade_scope=TradeScope.global_trade(),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "出品しました" in out.prose
        assert out.structured.get("type") == "trade_offered"
        assert out.structured.get("role") == "seller"
        assert out.structured.get("trade_id_value") == 1
        assert out.structured.get("requested_gold") == 100
        assert out.observation_category == "self_only"
        assert out.schedules_turn is True

    def test_recipient_sees_offer_proposal(self, formatter):
        """受取人は取引提案メッセージを見る。"""
        profile_repo = MagicMock()
        profile = MagicMock()
        profile.name.value = "Alice"
        profile_repo.find_by_id.return_value = profile
        ctx = _make_context(player_profile_repository=profile_repo)
        formatter = TradeObservationFormatter(ctx)

        event = TradeOfferedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            seller_id=PlayerId(2),
            offered_item_id=ItemInstanceId(1),
            requested_gold=TradeRequestedGold.of(100),
            trade_scope=TradeScope.global_trade(),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "Alice" in out.prose
        assert "取引提案" in out.prose or "届きました" in out.prose
        assert out.structured.get("role") == "recipient"
        assert out.structured.get("seller") == "Alice"


class TestTradeObservationFormatterTradeAccepted:
    """TradeAcceptedEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return TradeObservationFormatter(_make_context())

    def test_buyer_sees_purchase_message(self, formatter):
        """購入者は「購入しました」メッセージを見る。"""
        event = TradeAcceptedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            buyer_id=PlayerId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "購入" in out.prose
        assert out.structured.get("type") == "trade_accepted"
        assert out.structured.get("role") == "buyer"

    def test_seller_sees_accepted_message(self, formatter):
        """出品者は「取引が受諾されました」メッセージを見る。"""
        event = TradeAcceptedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            buyer_id=PlayerId(2),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "受諾" in out.prose
        assert out.structured.get("role") == "seller"
        assert out.structured.get("buyer_player_id") == 2


class TestTradeObservationFormatterTradeCancelled:
    """TradeCancelledEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return TradeObservationFormatter(_make_context())

    def test_returns_cancelled_message(self, formatter):
        """キャンセルメッセージを返す。"""
        event = TradeCancelledEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "キャンセル" in out.prose
        assert out.structured.get("type") == "trade_cancelled"
        assert out.structured.get("trade_id_value") == 1


class TestTradeObservationFormatterTradeDeclined:
    """TradeDeclinedEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return TradeObservationFormatter(_make_context())

    def test_decliner_sees_declined_self_message(self, formatter):
        """断った人は「断りました」メッセージを見る。"""
        event = TradeDeclinedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            decliner_id=PlayerId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "断り" in out.prose
        assert out.structured.get("type") == "trade_declined"
        assert out.structured.get("role") == "decliner"

    def test_seller_sees_decliner_name(self, formatter):
        """出品者は断った人の名前を見る。"""
        profile_repo = MagicMock()
        profile = MagicMock()
        profile.name.value = "Bob"
        profile_repo.find_by_id.return_value = profile
        ctx = _make_context(player_profile_repository=profile_repo)
        formatter = TradeObservationFormatter(ctx)

        event = TradeDeclinedEvent.create(
            aggregate_id=TradeId(1),
            aggregate_type="TradeAggregate",
            decliner_id=PlayerId(2),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "Bob" in out.prose
        assert out.structured.get("role") == "seller"


class TestTradeObservationFormatterUnknownEvent:
    """対象外イベントのテスト"""

    @pytest.fixture
    def formatter(self):
        return TradeObservationFormatter(_make_context())

    def test_returns_none_for_unknown_event(self, formatter):
        """対象外イベントは None。"""
        class UnknownEvent:
            pass
        out = formatter.format(UnknownEvent(), PlayerId(1))
        assert out is None

    def test_returns_none_for_harvest_event(self, formatter):
        """Harvest イベントは None。"""
        event = HarvestStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Harvest",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            finish_tick=WorldTick(10),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None
