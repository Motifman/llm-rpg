from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.people import NoVisibleName, PersonHandle, PersonRef, Unidentified
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName


class TestPersonHandle:
    """PersonHandle が、0 以上の整数の印で 1 人を指すことを保証する。"""

    def test_zero_is_accepted(self) -> None:
        """0 の印を受け付ける。"""
        assert PersonHandle(0).value == 0

    def test_same_value_points_to_the_same_person(self) -> None:
        """同じ値の PersonHandle どうしは等しく、辞書の鍵に使える。"""
        assert {PersonHandle(3): "a"}[PersonHandle(3)] == "a"

    @pytest.mark.parametrize("raw", [-1, 1.0, True, "1"])
    def test_non_natural_number_raises_domain_exception(self, raw: object) -> None:
        """負の数、整数でない値 (小数、真偽値、文字列) を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            PersonHandle(raw)  # type: ignore[arg-type]


class TestPersonRef:
    """PersonRef が、見分けられる 1 人を印と見た目と見えている名前で指すことを保証する。"""

    def test_name_is_absent_unless_the_world_shows_it(self) -> None:
        """名前が見えない世界の人は、visible_name に NoVisibleName を持って作れる。"""
        ref = PersonRef(handle=PersonHandle(1), appearance=DescriptionText("背の高い男"), visible_name=NoVisibleName())

        assert ref.visible_name == NoVisibleName()

    def test_visible_name_is_kept_as_given(self) -> None:
        """名札の世界の人は、visible_name に見えている名前を持つ。"""
        ref = PersonRef(
            handle=PersonHandle(1), appearance=DescriptionText("背の高い男"), visible_name=DisplayName("ガレス")
        )

        assert ref.visible_name == DisplayName("ガレス")

    def test_same_handle_with_different_appearance_is_a_different_ref(self) -> None:
        """同じ印でも見た目が違えば別の PersonRef として比べられる (着替えたあとの見え方を区別できる)。"""
        before = PersonRef(handle=PersonHandle(1), appearance=DescriptionText("外套の男"), visible_name=NoVisibleName())
        after = PersonRef(handle=PersonHandle(1), appearance=DescriptionText("鎧の男"), visible_name=NoVisibleName())

        assert before != after


class TestUnidentified:
    """Unidentified が、印を持たない「誰か」を表すことを保証する。"""

    def test_every_unidentified_is_indistinguishable(self) -> None:
        """Unidentified どうしは等しい。誰だか分からない人を区別する手がかりを持たないため。"""
        assert Unidentified() == Unidentified()

    def test_has_no_handle(self) -> None:
        """Unidentified は印を持たないので、誰を指しているかを漏らさない。"""
        assert not hasattr(Unidentified(), "handle")
