"""DialogueTreeId のテスト"""
import pytest

from ai_rpg_world.domain.conversation.value_object.dialogue_tree_id import (
    DialogueTreeId,
)


class TestDialogueTreeId:
    """DialogueTreeId のテスト"""

    def test_create_from_int(self):
        tid = DialogueTreeId.create(1)
        assert tid.value == 1

    def test_create_from_str(self):
        tid = DialogueTreeId.create("2")
        assert tid.value == 2

    def test_positive_only(self):
        with pytest.raises(ValueError, match="must be positive"):
            DialogueTreeId(0)
        with pytest.raises(ValueError, match="must be positive"):
            DialogueTreeId(-1)

    def test_eq_and_hash(self):
        a = DialogueTreeId(1)
        b = DialogueTreeId(1)
        c = DialogueTreeId(2)
        assert a == b
        assert a != c
        assert hash(a) == hash(b)

    def test_int_and_str(self):
        tid = DialogueTreeId(5)
        assert int(tid) == 5
        assert str(tid) == "5"
