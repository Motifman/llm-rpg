"""DialogueNode のテスト"""
import pytest

from ai_rpg_world.domain.conversation.value_object.dialogue_node import (
    DialogueNode,
)


class TestDialogueNode:
    """DialogueNode のテスト"""

    def test_minimal_node(self):
        node = DialogueNode(
            node_id=0,
            text="Hello.",
            choices=(),
            next_node_id=1,
            is_terminal=False,
        )
        assert node.node_id == 0
        assert node.text == "Hello."
        assert node.choices == ()
        assert node.next_node_id == 1
        assert node.is_terminal is False
        assert node.reward_gold == 0
        assert node.reward_items == ()
        assert node.quest_unlock_ids == ()
        assert node.quest_complete_quest_ids == ()

    def test_terminal_node_with_rewards(self):
        node = DialogueNode(
            node_id=2,
            text="Thanks!",
            choices=(),
            next_node_id=None,
            is_terminal=True,
            reward_gold=100,
            reward_items=((10, 1),),
            quest_unlock_ids=(1,),
            quest_complete_quest_ids=(2,),
        )
        assert node.is_terminal is True
        assert node.reward_gold == 100
        assert node.reward_items == ((10, 1),)
        assert node.quest_unlock_ids == (1,)
        assert node.quest_complete_quest_ids == (2,)

    def test_choices(self):
        node = DialogueNode(
            node_id=0,
            text="Choose.",
            choices=(("Option A", 1), ("Option B", 2)),
            next_node_id=None,
            is_terminal=False,
        )
        assert node.choices == (("Option A", 1), ("Option B", 2))

    def test_reward_gold_non_negative(self):
        with pytest.raises(ValueError, match="reward_gold"):
            DialogueNode(
                node_id=0,
                text="x",
                choices=(),
                next_node_id=None,
                is_terminal=False,
                reward_gold=-1,
            )

    def test_node_id_non_negative(self):
        with pytest.raises(ValueError, match="node_id"):
            DialogueNode(
                node_id=-1,
                text="x",
                choices=(),
                next_node_id=None,
                is_terminal=False,
            )
