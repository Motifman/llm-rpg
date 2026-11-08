from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.action.action_arguments import TextArgumentValue
from ai_rpg_world.game_world.domain.exception.action_argument_exception import BlankTextArgumentException


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
