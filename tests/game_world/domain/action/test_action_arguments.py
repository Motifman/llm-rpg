from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.action.action_arguments import (
    ArgumentsNotChosen,
    ChosenArguments,
    TextArgumentValue,
)
from ai_rpg_world.game_world.domain.exception.action_argument_exception import BlankTextArgumentException
from ai_rpg_world.game_world.domain.exception.action_exception import ArgumentsNotChosenException
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import InteractionId
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from tests.game_world.support.declarations_for_tests import InteractionForTests

_OPEN_SAFE = InteractionForTests(InteractionId("open_safe"))


class TestTextArgumentValue:
    """TextArgumentValue が、エージェントの渡した空でない文だけを持つことを保証する。"""

    def test_keeps_the_text(self) -> None:
        """「開けゴマ」を渡すと text にそのまま持つ。"""
        assert TextArgumentValue("開けゴマ").text == "開けゴマ"

    @pytest.mark.parametrize("raw", ["", "  \n"])
    def test_blank_text_raises_domain_exception(self, raw: str) -> None:
        """空の文や空白だけの文を渡すと BlankTextArgumentException を投げる。"""
        with pytest.raises(BlankTextArgumentException):
            TextArgumentValue(raw)


class TestArgumentsNotChosen:
    """値をまだ選んでいない引数 (ArgumentsNotChosen) が、選んだ引数 (ChosenArguments) と同じ頼み方で、選んでいないなりに答えることを保証する。"""

    def test_require_chosen_raises_when_not_chosen(self) -> None:
        """選んでいない引数に require_chosen を頼むと ArgumentsNotChosenException を投げる。"""
        with pytest.raises(ArgumentsNotChosenException):
            ArgumentsNotChosen().require_chosen(_OPEN_SAFE)

    def test_require_chosen_passes_when_chosen(self) -> None:
        """選んだ引数に require_chosen を頼んでも何も起きない。"""
        ChosenArguments({ArgumentName("code"): TextArgumentValue("1907")}).require_chosen(_OPEN_SAFE)

    def test_items_of_arguments_not_chosen_are_empty(self) -> None:
        """選んでいない引数が扱う品物は無い。"""
        assert ArgumentsNotChosen().items() == ()

    def test_items_of_chosen_arguments_are_the_item_values(self) -> None:
        """選んだ引数が扱う品物は、値のうち品物の印だけ。"""
        pen = ItemInstanceId("pen_1")
        chosen = ChosenArguments({ArgumentName("gift"): pen, ArgumentName("words"): TextArgumentValue("どうぞ")})

        assert chosen.items() == (pen,)
