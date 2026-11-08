from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.world_design_exception import BlankDeclaredNameException
from ai_rpg_world.game_world.domain.value_object.discoverable_id import DiscoverableId


class TestDiscoverableIdHoldsName:
    """DiscoverableId が、見つかる物の宣言した名前を持ち、空の名前を断ることを保証する。"""

    def test_declared_name_is_kept_as_is(self) -> None:
        """宣言の名前 "rusty_key_under_rock" を渡すと、value にそのまま持つ。"""
        assert DiscoverableId("rusty_key_under_rock").value == "rusty_key_under_rock"

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_blank_name_raises_domain_exception(self, raw: str) -> None:
        """空の名前や空白だけの名前を渡すと BlankDeclaredNameException を投げる。"""
        with pytest.raises(BlankDeclaredNameException):
            DiscoverableId(raw)
