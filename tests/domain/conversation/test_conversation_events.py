"""ConversationStartedEvent / ConversationEndedEvent のテスト"""
import pytest

from ai_rpg_world.domain.conversation.event.conversation_event import (
    ConversationStartedEvent,
    ConversationEndedEvent,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestConversationStartedEvent:
    """ConversationStartedEvent のテスト"""

    def test_create_sets_aggregate_id_as_player_id(self):
        player_id = PlayerId.create(1)
        event = ConversationStartedEvent.create(
            aggregate_id=player_id,
            aggregate_type="Conversation",
            npc_id_value=100,
            dialogue_tree_id_value=1,
            entry_node_id_value=0,
        )
        assert event.aggregate_id == player_id
        assert event.aggregate_type == "Conversation"
        assert event.npc_id_value == 100
        assert event.dialogue_tree_id_value == 1
        assert event.entry_node_id_value == 0


class TestConversationEndedEvent:
    """ConversationEndedEvent のテスト"""

    def test_create_minimal(self):
        player_id = PlayerId.create(1)
        event = ConversationEndedEvent.create(
            aggregate_id=player_id,
            aggregate_type="Conversation",
            npc_id_value=100,
            end_node_id_value=2,
        )
        assert event.aggregate_id == player_id
        assert event.npc_id_value == 100
        assert event.end_node_id_value == 2
        assert event.outcome is None
        assert event.rewards_claimed_gold == 0
        assert event.rewards_claimed_items == ()
        assert event.quest_unlocked_ids == ()
        assert event.quest_completed_quest_ids == ()

    def test_create_with_rewards_and_quests(self):
        player_id = PlayerId.create(2)
        event = ConversationEndedEvent.create(
            aggregate_id=player_id,
            aggregate_type="Conversation",
            npc_id_value=200,
            end_node_id_value=3,
            outcome="thanks",
            rewards_claimed_gold=50,
            rewards_claimed_items=((10, 1), (20, 2)),
            quest_unlocked_ids=(1, 2),
            quest_completed_quest_ids=(5,),
        )
        assert event.rewards_claimed_gold == 50
        assert event.rewards_claimed_items == ((10, 1), (20, 2))
        assert event.quest_unlocked_ids == (1, 2)
        assert event.quest_completed_quest_ids == (5,)
