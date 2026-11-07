from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.game_world_exception import InvalidSpotIdException
from ai_rpg_world.game_world.domain.value_object import SpotId


class TestSpotId:
    """SpotId がシナリオの宣言した場所の名前を持ち、空の名前と文字列でない値を断ることを保証する。"""

    def test_declared_name_is_kept_as_is(self) -> None:
        """宣言の名前 "lift_landing" をそのまま持つ。"""
        assert SpotId("lift_landing").value == "lift_landing"

    def test_same_name_means_the_same_spot(self) -> None:
        """同じ名前の SpotId は等しく、辞書のキーとして同じ場所を指す。"""
        assert SpotId("hall") == SpotId("hall")
        assert {SpotId("hall"): 1}[SpotId("hall")] == 1

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_blank_name_raises_domain_exception(self, raw: str) -> None:
        """空の名前や空白だけの名前を渡すと InvalidSpotIdException を投げる。"""
        with pytest.raises(InvalidSpotIdException):
            SpotId(raw)

    @pytest.mark.parametrize("raw", [1, None])
    def test_non_string_raises_domain_exception(self, raw: object) -> None:
        """文字列でない値 (古い世界の連番の int など) を渡すと InvalidSpotIdException を投げる。"""
        with pytest.raises(InvalidSpotIdException):
            SpotId(raw)  # type: ignore[arg-type]
