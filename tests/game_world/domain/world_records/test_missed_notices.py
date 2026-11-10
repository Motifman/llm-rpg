from __future__ import annotations

from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick
from ai_rpg_world.game_world.domain.world_records import MissedNotices
from tests.game_world.support.memento_for_tests import rebuilt_from_memento

_BOB = PersonId("bob")


def _notice(text: str, at: int) -> MissedNotice:
    return MissedNotice(text=TextWithAssignedPeople(template=text, people={}), happened_at=WorldTick(at))


class TestMissedNotices:
    """MissedNotices が、倒れている間に届いた知らせを、起きるまで届いた順にためておくことを保証する。"""

    def test_holds_nothing_at_first(self) -> None:
        """作った直後は、その人の知らせを 1 つも持たない。"""
        notices = MissedNotices.start(_BOB)

        assert notices.person == _BOB
        assert notices.notices() == ()

    def test_returns_notices_in_the_order_they_were_kept(self) -> None:
        """tick 3 に「荷が軽くなっている」、tick 5 に「遠くで鐘が鳴った」をためると、その順で返す。"""
        notices = MissedNotices.start(_BOB)
        lighter = _notice("荷が軽くなっている。", 3)
        bell = _notice("遠くで鐘が鳴った。", 5)

        notices.keep(lighter)
        notices.keep(bell)

        assert notices.notices() == (lighter, bell)

    def test_clear_empties_the_notices(self) -> None:
        """起きて届け終えたあと clear すると、ためていた知らせは無くなる。"""
        notices = MissedNotices.start(_BOB)
        notices.keep(_notice("荷が軽くなっている。", 3))

        notices.clear()

        assert notices.notices() == ()


class TestMissedNoticesMemento:
    """MissedNotices を memento から作り直すと、ためていた知らせが届いた順のまま元と同じになることを保証する。"""

    def test_rebuilt_notices_keep_the_order(self) -> None:
        """tick 3 と tick 5 の知らせをためたあと作り直すと、同じ人の、同じ知らせを同じ順で返す。"""
        notices = MissedNotices.start(_BOB)
        lighter = _notice("荷が軽くなっている。", 3)
        bell = _notice("遠くで鐘が鳴った。", 5)
        notices.keep(lighter)
        notices.keep(bell)

        rebuilt = rebuilt_from_memento(notices)

        assert rebuilt.memento() == notices.memento()
        assert rebuilt.notices() == (lighter, bell)
        assert rebuilt.person == _BOB
