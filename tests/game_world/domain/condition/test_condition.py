from __future__ import annotations

from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.value_object import PersonId


def _never_read(placeholder: str, template: str) -> str:
    raise AssertionError(f"{placeholder} in {template} must not be read")


def _no_person_asked(placeholder: str, template: str) -> PersonId:
    raise AssertionError(f"{placeholder} in {template} must not be asked")


class TestNoText:
    """NoText が、文が無いことを、文のある側と同じ名前の問い合わせで答えることを保証する。"""

    def test_explains_is_false(self) -> None:
        """NoText の explains は、失敗を説明する文が無いので False を返す。"""
        assert NoText().explains() is False

    def test_about_each_stays_no_text_without_asking_for_people(self) -> None:
        """NoText の about_each は人を一度も問い合わせず、NoText を返す。"""
        assert NoText().about_each(_no_person_asked) == NoText()

    def test_placeholders_read_as_is_empty_without_reading_any(self) -> None:
        """NoText の placeholders_read_as は読み方を一度も呼ばず、空の集合を返す。"""
        assert NoText().placeholders_read_as(_never_read) == frozenset()
