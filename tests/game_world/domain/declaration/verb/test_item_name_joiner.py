from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.verb.item_name_joiner import ItemNameJoiner
from ai_rpg_world.game_world.domain.exception.verb_declaration_exception import BlankItemNameJoinerException
from ai_rpg_world.game_world.domain.value_object import DisplayName

_PICKAXE = DisplayName("つるはし")
_ROPE = DisplayName("ロープ")
_FLASK = DisplayName("水筒")


class TestItemNameJoiner:
    """ItemNameJoiner が、品物の呼び名を、シナリオの宣言したつなぐ言葉でつなぐことを保証する。"""

    def test_single_name_is_used_without_the_joiner(self) -> None:
        """品物が 1 つのときは、つなぐ言葉を使わずにその呼び名だけになる。"""
        assert ItemNameJoiner("と").join((_PICKAXE,)) == _PICKAXE

    def test_two_names_are_joined_with_the_joiner(self) -> None:
        """つるはしとロープは、「と」でつながって「つるはしとロープ」になる。"""
        assert ItemNameJoiner("と").join((_PICKAXE, _ROPE)) == DisplayName("つるはしとロープ")

    def test_three_names_are_joined_in_the_order_given(self) -> None:
        """3 つの呼び名は、渡した順に「、」でつながる。"""
        assert ItemNameJoiner("、").join((_ROPE, _PICKAXE, _FLASK)) == DisplayName("ロープ、つるはし、水筒")

    @pytest.mark.parametrize("text", ["", "と\nと"])
    def test_blank_or_multiline_joiner_is_refused(self, text: str) -> None:
        """つなぐ言葉が空か、複数行なら BlankItemNameJoinerException を投げる。"""
        with pytest.raises(BlankItemNameJoinerException):
            ItemNameJoiner(text)
