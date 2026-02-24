"""DialogueNodeId のテスト"""
import pytest

from ai_rpg_world.domain.conversation.value_object.dialogue_node_id import (
    DialogueNodeId,
)


class TestDialogueNodeId:
    """DialogueNodeId のテスト"""

    def test_create_from_int(self):
        nid = DialogueNodeId.create(0)
        assert nid.value == 0

    def test_create_from_str(self):
        nid = DialogueNodeId.create("1")
        assert nid.value == 1

    def test_non_negative_only(self):
        with pytest.raises(ValueError, match="non-negative"):
            DialogueNodeId(-1)

    def test_eq_and_hash(self):
        a = DialogueNodeId(0)
        b = DialogueNodeId(0)
        c = DialogueNodeId(1)
        assert a == b
        assert a != c
        assert hash(a) == hash(b)
