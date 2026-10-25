"""消耗品・ショップ・SNSの登録対応と、確定前後の配送を守る。"""

from dataclasses import fields
from unittest.mock import Mock, call

import pytest
from tests.support.command_scope_stack import CommandScopeTestStack

from ai_rpg_world.domain.item.event.item_event import ConsumableUsedEvent
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.shop.event.shop_event import (
    ShopCreatedEvent,
    ShopItemListedEvent,
    ShopItemPurchasedEvent,
    ShopItemUnlistedEvent,
)
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.shop.value_object.shop_listing_price import ShopListingPrice
from ai_rpg_world.domain.shop.value_object.shop_listing_projection import ShopListingProjection
from ai_rpg_world.domain.sns.event import (
    SnsContentLikedEvent,
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
    SnsUserBlockedEvent,
    SnsUserFollowedEvent,
    SnsUserSubscribedEvent,
)
from ai_rpg_world.domain.sns.value_object import PostContent, PostId, ReplyId, UserId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.events.consumable_effect_event_handler_registry import (
    ConsumableEffectEventHandlerRegistry,
)
from ai_rpg_world.infrastructure.events.shop_event_handler_registry import ShopEventHandlerRegistry
from ai_rpg_world.infrastructure.events.sns_event_handler_registry import SnsEventHandlerRegistry
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore

_CASES = [
    (ConsumableUsedEvent, "consumable", "handle", True),
    (ShopCreatedEvent, "shop", "handle_shop_created", False),
    (ShopItemListedEvent, "shop", "handle_shop_item_listed", False),
    (ShopItemUnlistedEvent, "shop", "handle_shop_item_unlisted", False),
    (ShopItemPurchasedEvent, "shop", "handle_shop_item_purchased", False),
    (SnsUserSubscribedEvent, "notification", "handle_user_subscribed", False),
    (SnsUserFollowedEvent, "notification", "handle_user_followed", False),
    (SnsPostCreatedEvent, "notification", "handle_post_created", False),
    (SnsReplyCreatedEvent, "notification", "handle_reply_created", False),
    (SnsContentLikedEvent, "notification", "handle_content_liked", False),
    (SnsUserBlockedEvent, "relationship", "handle_user_blocked", False),
]


def _stack():
    store = InMemoryDataStore()
    scope = publisher = CommandScopeTestStack(store)
    handlers = {name: Mock() for name in ("consumable", "shop", "notification", "relationship")}
    ConsumableEffectEventHandlerRegistry(handlers["consumable"]).register_command_handlers(scope.dispatcher)
    ShopEventHandlerRegistry(handlers["shop"]).register_command_handlers(scope.dispatcher)
    SnsEventHandlerRegistry(handlers["notification"], handlers["relationship"]).register_command_handlers(scope.dispatcher)
    return store, scope, publisher, handlers


def _event(event_type, number=1):
    values = dict(
        item_spec_id=ItemSpecId(1), spot_id=SpotId(1), location_area_id=LocationAreaId(1),
        owner_id=PlayerId(1), owner_ids=(PlayerId(1),), name="店", description="説明",
        listing_id=ShopListingId(1), item_instance_id=ItemInstanceId(1), price_per_unit=ShopListingPrice(1),
        listed_by=PlayerId(1), unlisted_by=PlayerId(1), buyer_id=PlayerId(2), seller_id=PlayerId(1),
        listing_projection=ShopListingProjection("品", 1, 1), quantity=1, total_gold=1,
        subscriber_user_id=UserId(1), subscribed_user_id=UserId(2), follower_user_id=UserId(1), followee_user_id=UserId(2),
        blocker_user_id=UserId(1), blocked_user_id=UserId(2), post_id=PostId(1), reply_id=ReplyId(1),
        author_user_id=UserId(1), content=PostContent("本文"), target_id=PostId(1), user_id=UserId(2), content_author_id=UserId(1),
    )
    if event_type is ConsumableUsedEvent:
        aggregate_id, aggregate_type = PlayerId(number), "PlayerStatusAggregate"
    elif event_type.__name__.startswith("Shop"):
        aggregate_id, aggregate_type = ShopId(number), "ShopAggregate"
    elif event_type is SnsReplyCreatedEvent:
        aggregate_id, aggregate_type = ReplyId(number), "ReplyAggregate"
    elif event_type in (SnsPostCreatedEvent, SnsContentLikedEvent):
        aggregate_id, aggregate_type = PostId(number), "PostAggregate"
    else:
        aggregate_id, aggregate_type = UserId(number), "UserAggregate"
    kwargs = {field.name: values[field.name] for field in fields(event_type) if field.name in values}
    return event_type.create(aggregate_id=aggregate_id, aggregate_type=aggregate_type, **kwargs)


@pytest.mark.parametrize("event_type,owner,method,before", _CASES)
def test_each_event_calls_its_original_method_in_the_original_phase(event_type, owner, method, before) -> None:
    """既存11件のイベントは同じメソッドへ渡り、消耗品だけが確定前、残りは確定後に動く。"""
    _, scope, publisher, handlers = _stack()
    event = _event(event_type)
    received = []
    getattr(handlers[owner], method).side_effect = lambda event: received.append(scope.is_in_transaction())
    with scope:
        publisher.publish(event)
        assert received == []
    assert received == [before]
    assert handlers[owner].mock_calls == [getattr(call, method)(event)]
    assert all(not handler.mock_calls for name, handler in handlers.items() if name != owner)


def test_same_batch_runs_required_effect_before_after_commit_events() -> None:
    """ショップ・SNS・消耗品の順に集めても消耗品を先に処理し、確定後は収集順に呼ぶ。"""
    _, scope, publisher, handlers = _stack()
    order = []
    handlers["consumable"].handle.side_effect = lambda event: order.append("effect")
    handlers["shop"].handle_shop_created.side_effect = lambda event: order.append("shop")
    handlers["notification"].handle_user_followed.side_effect = lambda event: order.append("sns")
    with scope:
        publisher.publish_all([_event(ShopCreatedEvent, 1), _event(SnsUserFollowedEvent, 2), _event(ConsumableUsedEvent, 3)])
    assert order == ["effect", "shop", "sns"]


def test_effect_failure_rolls_back_and_skips_after_commit() -> None:
    """消耗品効果が失敗すると状態を元に戻し、同じ区切りのショップとSNSは呼ばない。"""
    store, scope, publisher, handlers = _stack()
    original = store.next_world_object_id
    handlers["consumable"].handle.side_effect = RuntimeError("効果の失敗")
    event = ConsumableUsedEvent.create(aggregate_id=PlayerId(1), aggregate_type="PlayerStatusAggregate", item_spec_id=ItemSpecId(1))
    with pytest.raises(RuntimeError, match="効果の失敗"):
        with scope:
            store.next_world_object_id = original + 1
            publisher.publish_all([event, _event(ShopCreatedEvent, 2), _event(SnsUserFollowedEvent, 3)])
    assert store.next_world_object_id == original
    assert not handlers["shop"].mock_calls and not handlers["notification"].mock_calls


@pytest.mark.parametrize("event_type,owner,method,before", _CASES[1:])
def test_after_commit_failure_is_traced_and_other_deliveries_continue(event_type, owner, method, before) -> None:
    """確定後の10件の各受け手が失敗しても後続を試し、traceに残して例外を返し、保存は戻さない。"""
    from ai_rpg_world.application.common.exceptions import CommandPostCommitException
    from ai_rpg_world.domain.common.domain_event import BaseDomainEvent, DomainEvent
    from ai_rpg_world.eventing import DeliveryChannel, DeliveryGuarantee

    store, scope, publisher, handlers = _stack()
    failure = RuntimeError("受け手の失敗")
    getattr(handlers[owner], method).side_effect = failure
    delivered = []
    scope.dispatcher.register_after_commit(DomainEvent, delivered.append, channel=DeliveryChannel.AUXILIARY, guarantee=DeliveryGuarantee.BEST_EFFORT)
    events = [_event(event_type), BaseDomainEvent.create(aggregate_id=1, aggregate_type="Unrelated")]
    changed = store.next_world_object_id + 1
    with pytest.raises(CommandPostCommitException) as caught:
        with scope:
            store.next_world_object_id = changed
            publisher.publish_all(events)
    assert store.next_world_object_id == changed
    assert delivered == events
    assert caught.value.handoff_error is failure
    failures = scope.trace.of_kind("world_tick_unit_failed")
    assert len(failures) == 1
    assert failures[0].payload["target_id"] == event_type.__name__
    assert failures[0].payload["error_message"] == "受け手の失敗"
    assert failures[0].payload["continued"] is True


def test_real_shop_handler_updates_the_read_model_after_commit() -> None:
    """実際のショップの受け手を新登録で呼ぶと、確定後に表示用の情報が保存される。"""
    from ai_rpg_world.application.shop.handlers.shop_event_handler import ShopEventHandler
    from ai_rpg_world.infrastructure.repository.in_memory_shop_listing_read_model_repository import (
        InMemoryShopListingReadModelRepository,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_shop_summary_read_model_repository import (
        InMemoryShopSummaryReadModelRepository,
    )
    from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork

    store = InMemoryDataStore()
    stack = CommandScopeTestStack(store)
    summary = InMemoryShopSummaryReadModelRepository()
    factory = Mock()
    factory.create.side_effect = lambda: InMemoryUnitOfWork(data_store=store)
    handler = ShopEventHandler(summary, InMemoryShopListingReadModelRepository(), factory)
    ShopEventHandlerRegistry(handler).register_command_handlers(stack.dispatcher)
    event = _event(ShopCreatedEvent, 777)
    with stack:
        stack.publish(event)
        assert summary.find_by_id(event.aggregate_id) is None
    assert summary.find_by_id(event.aggregate_id).name == "店"
