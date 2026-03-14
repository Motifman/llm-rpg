"""ObservedEventRegistry のテスト（正常・境界・例外）"""

import pytest

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.event.status_events import (
    PlayerGoldEarnedEvent,
    PlayerLevelUpEvent,
)
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.conversation.event.conversation_event import (
    ConversationStartedEvent,
    ConversationEndedEvent,
)
from ai_rpg_world.domain.world.event.map_events import LocationEnteredEvent
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestObservedEventRegistryIsObserved:
    """is_observed のテスト（正常・境界）"""

    @pytest.fixture
    def registry(self):
        return ObservedEventRegistry()

    def test_returns_true_for_default_strategy_event(self, registry):
        """default 戦略のイベント（PlayerGoldEarnedEvent）は観測対象（正常）"""
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=100,
            total_gold=1100,
        )
        assert registry.is_observed(event) is True

    def test_returns_true_for_conversation_event(self, registry):
        """conversation 戦略のイベントは観測対象（正常）"""
        event = ConversationStartedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            npc_id_value=10,
            dialogue_tree_id_value=1,
            entry_node_id_value=1,
        )
        assert registry.is_observed(event) is True

    def test_returns_true_for_player_level_up_event(self, registry):
        """PlayerLevelUpEvent は観測対象（正常）"""
        event = PlayerLevelUpEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_level=1,
            new_level=2,
            stat_growth=BaseStats(0, 0, 0, 0, 0, 0.0, 0.0),
        )
        assert registry.is_observed(event) is True

    def test_returns_false_for_none(self, registry):
        """None は観測対象外（境界）"""
        assert registry.is_observed(None) is False

    def test_returns_false_for_non_event_object(self, registry):
        """イベントでないオブジェクトは観測対象外（境界）"""
        assert registry.is_observed("not an event") is False
        assert registry.is_observed(123) is False
        assert registry.is_observed([]) is False


class TestObservedEventRegistryGetStrategyForEvent:
    """get_strategy_for_event のテスト（正常・境界）"""

    @pytest.fixture
    def registry(self):
        return ObservedEventRegistry()

    def test_returns_default_for_player_gold_earned(self, registry):
        """PlayerGoldEarnedEvent は default 戦略が担当（正常）"""
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=100,
            total_gold=1100,
        )
        assert registry.get_strategy_for_event(event) == "default"

    def test_returns_conversation_for_conversation_started(self, registry):
        """ConversationStartedEvent は conversation 戦略が担当（正常）"""
        event = ConversationStartedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            npc_id_value=10,
            dialogue_tree_id_value=1,
            entry_node_id_value=1,
        )
        assert registry.get_strategy_for_event(event) == "conversation"

    def test_returns_conversation_for_conversation_ended(self, registry):
        """ConversationEndedEvent は conversation 戦略が担当（正常）"""
        event = ConversationEndedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            npc_id_value=10,
            end_node_id_value=1,
        )
        assert registry.get_strategy_for_event(event) == "conversation"

    def test_returns_none_for_none(self, registry):
        """None の場合は None を返す（境界）"""
        assert registry.get_strategy_for_event(None) is None

    def test_returns_none_for_non_event_object(self, registry):
        """イベントでないオブジェクトは None（境界）"""
        assert registry.get_strategy_for_event("string") is None
        assert registry.get_strategy_for_event(42) is None


class TestObservedEventRegistryGetEventTypesForStrategy:
    """get_event_types_for_strategy のテスト（正常・境界）"""

    @pytest.fixture
    def registry(self):
        return ObservedEventRegistry()

    def test_returns_event_types_for_default_strategy(self, registry):
        """default 戦略のイベント型一覧を取得（正常）"""
        types = registry.get_event_types_for_strategy("default")
        assert len(types) > 0
        assert PlayerGoldEarnedEvent in types
        assert PlayerLevelUpEvent in types
        assert ConversationStartedEvent not in types

    def test_returns_event_types_for_conversation_strategy(self, registry):
        """conversation 戦略のイベント型一覧を取得（正常）"""
        types = registry.get_event_types_for_strategy("conversation")
        assert len(types) == 2
        assert ConversationStartedEvent in types
        assert ConversationEndedEvent in types

    def test_returns_empty_tuple_for_unknown_strategy(self, registry):
        """未知の戦略キーは空タプル（境界）"""
        types = registry.get_event_types_for_strategy("unknown_strategy_xyz")
        assert types == ()


class TestObservedEventRegistryCustomMapping:
    """カスタムマッピングのテスト（正常）"""

    def test_custom_mapping_overrides_default(self):
        """カスタム event_to_strategy でデフォルトを上書きできる"""
        custom = {PlayerGoldEarnedEvent: "custom_strategy"}
        registry = ObservedEventRegistry(event_to_strategy=custom)
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=100,
            total_gold=1100,
        )
        assert registry.get_strategy_for_event(event) == "custom_strategy"
        assert registry.is_observed(event) is True

    def test_custom_mapping_excludes_unregistered_events(self):
        """カスタムマッピングに含まれないイベントは観測対象外"""
        custom = {PlayerGoldEarnedEvent: "custom"}
        registry = ObservedEventRegistry(event_to_strategy=custom)
        event = ConversationStartedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            npc_id_value=10,
            dialogue_tree_id_value=1,
            entry_node_id_value=1,
        )
        assert registry.is_observed(event) is False
        assert registry.get_strategy_for_event(event) is None

    def test_empty_custom_mapping(self):
        """空のカスタムマッピングではすべて観測対象外"""
        registry = ObservedEventRegistry(event_to_strategy={})
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=100,
            total_gold=1100,
        )
        assert registry.is_observed(event) is False
        assert registry.get_strategy_for_event(event) is None
