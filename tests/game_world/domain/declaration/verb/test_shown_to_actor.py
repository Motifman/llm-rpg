from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    FlagStateKind,
    FlagValue,
    NothingWritten,
    ObjectStateKeyDeclaration,
    WrittenTextStateKind,
)
from ai_rpg_world.game_world.domain.declaration.verb import WrittenTextOf
from ai_rpg_world.game_world.domain.exception.verb_declaration_exception import (
    ShownKeyHoldsNoWrittenTextException,
)
from ai_rpg_world.game_world.domain.value_object import ObjectId, StateKeyId


class TestWrittenTextOfKey:
    """WrittenTextOf が、成功したとき本人に見せる文を持つ鍵だけを指すことを保証する。"""

    def test_key_without_written_text_raises(self) -> None:
        """文を持たない鍵 (レバーの上がり下がりの旗) を指すと ShownKeyHoldsNoWrittenTextException を投げる。"""
        lever_raised = ObjectStateKeyDeclaration(
            object_id=ObjectId("lift_lever"),
            key=StateKeyId("raised"),
            kind=FlagStateKind(),
            initial=FlagValue(raised=False),
        )

        with pytest.raises(ShownKeyHoldsNoWrittenTextException):
            WrittenTextOf(key=lever_raised)

    def test_key_with_written_text_is_kept(self) -> None:
        """書いた文を持つ鍵 (掲示板の貼り紙) を指すと、断らずにその鍵を持つ。"""
        notice = ObjectStateKeyDeclaration(
            object_id=ObjectId("notice_board"),
            key=StateKeyId("notice"),
            kind=WrittenTextStateKind(),
            initial=NothingWritten(),
        )

        assert WrittenTextOf(key=notice).key == notice
