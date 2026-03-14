"""ConversationRecipientStrategy のテスト（正常系・境界・例外）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies.conversation_recipient_strategy import (
    ConversationRecipientStrategy,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.conversation.event.conversation_event import (
    ConversationEndedEvent,
    ConversationStartedEvent,
)


class TestConversationRecipientStrategyNormal:
    """ConversationRecipientStrategy 正常系テスト"""

    @pytest.fixture
    def strategy(self):
        return ConversationRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
        )

    def test_conversation_started_returns_aggregate_id(self, strategy):
        """ConversationStartedEvent: aggregate_id（話し手 PlayerId）が配信先"""
        event = ConversationStartedEvent.create(
            aggregate_id=PlayerId(5),
            aggregate_type="PlayerStatusAggregate",
            npc_id_value=10,
            dialogue_tree_id_value=1,
            entry_node_id_value=1,
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 5

    def test_conversation_ended_returns_aggregate_id(self, strategy):
        """ConversationEndedEvent: aggregate_id（話し手 PlayerId）が配信先"""
        event = ConversationEndedEvent.create(
            aggregate_id=PlayerId(7),
            aggregate_type="PlayerStatusAggregate",
            npc_id_value=10,
            end_node_id_value=5,
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 7


class TestConversationRecipientStrategyExceptions:
    """ConversationRecipientStrategy 例外・境界テスト"""

    @pytest.fixture
    def strategy(self):
        return ConversationRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
        )

    def test_resolve_returns_empty_for_non_conversation_event(self, strategy):
        """会話イベント以外では空リスト"""
        class UnknownEvent:
            aggregate_id = PlayerId(1)
        result = strategy.resolve(UnknownEvent())
        assert result == []


class TestConversationRecipientStrategySupports:
    """ConversationRecipientStrategy supports テスト"""

    @pytest.fixture
    def strategy(self):
        return ConversationRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
        )

    def test_supports_conversation_started_event(self, strategy):
        """ConversationStartedEvent を supports"""
        event = ConversationStartedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            npc_id_value=10,
            dialogue_tree_id_value=1,
            entry_node_id_value=1,
        )
        assert strategy.supports(event) is True

    def test_supports_conversation_ended_event(self, strategy):
        """ConversationEndedEvent を supports"""
        event = ConversationEndedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            npc_id_value=10,
            end_node_id_value=1,
        )
        assert strategy.supports(event) is True

    def test_supports_returns_false_for_unknown_event(self, strategy):
        """未知のイベントでは False"""
        class UnknownEvent:
            pass
        assert strategy.supports(UnknownEvent()) is False
