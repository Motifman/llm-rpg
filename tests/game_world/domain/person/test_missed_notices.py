from __future__ import annotations

from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople, Unidentified
from ai_rpg_world.game_world.domain.person import MissedNotice, MissedNotices
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick

_ALICE = PersonId("alice")


def _notice(template: str, at: int) -> MissedNotice:
    text = TextWithUnassignedPeople(template).assign({"actor": Unidentified()})
    return MissedNotice(text=text, happened_at=WorldTick(at))


class TestKeepAndClear:
    """MissedNotices が、倒れている間の知らせをためた順に返し、clear で空にすることを保証する。"""

    def test_starts_empty_for_its_person(self) -> None:
        """作ったばかりの MissedNotices は、持ち主の PersonId を持ち、知らせを 1 つも持たない。"""
        notices = MissedNotices(_ALICE)

        assert notices.person == _ALICE
        assert notices.notices() == ()

    def test_returns_notices_in_the_order_they_were_kept(self) -> None:
        """tick 5 の知らせ、tick 3 の知らせの順に keep すると、notices は時刻で並べ替えず keep した順に返す。"""
        notices = MissedNotices(_ALICE)
        door = _notice("{actor}が扉を開けた", 5)
        steps = _notice("{actor}の足音が遠ざかった", 3)

        notices.keep(door)
        notices.keep(steps)

        assert notices.notices() == (door, steps)

    def test_clear_empties_the_notices(self) -> None:
        """知らせを 2 つためてから clear すると、notices は空になる。"""
        notices = MissedNotices(_ALICE)
        notices.keep(_notice("{actor}が扉を開けた", 5))
        notices.keep(_notice("{actor}の足音が遠ざかった", 6))

        notices.clear()

        assert notices.notices() == ()

    def test_keeping_after_clear_starts_over(self) -> None:
        """clear のあとに keep した知らせだけが返り、消した知らせは戻らない。"""
        notices = MissedNotices(_ALICE)
        notices.keep(_notice("{actor}が扉を開けた", 5))
        notices.clear()
        later = _notice("{actor}の足音が遠ざかった", 9)

        notices.keep(later)

        assert notices.notices() == (later,)
