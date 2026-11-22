from __future__ import annotations

import pytest

from ai_rpg_world.being.contract import Description, EnvironmentEntry, Introduction, Orientation
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldId
from ai_rpg_world.play_session.domain.cast import BeingCastInWorldEvent, Cast, CastMember
from ai_rpg_world.play_session.domain.play_session_exception import (
    CastValidationException,
    PersonAlreadyBriefedException,
    PersonNotBriefedException,
    PersonNotCastException,
)

_WORLD = WorldId("mine#1")
_GEN, _SAYO, _HARU = PersonId("gen"), PersonId("sayo"), PersonId("haru")
_ORIENTATION = Orientation((Description(heading="この世界について", text="冬が近い廃村。"),))


def _cast() -> Cast:
    return Cast(
        _WORLD,
        "廃坑の山村",
        (
            CastMember(_GEN, BeingId("being_gen"), "ゲン"),
            CastMember(_SAYO, BeingId("being_sayo"), "サヨ"),
            CastMember(_HARU, BeingId("being_haru"), "ハル"),
        ),
    )


class TestCastMembers:
    """Cast が、登場人物と Being を 1 対 1 で結び、重なる配役を断ることを保証する。"""

    @pytest.mark.parametrize(
        ("environment_name", "members"),
        [("廃坑の山村", ()), (" ", (CastMember(_GEN, BeingId("being_gen"), "ゲン"),))],
        ids=["no_members", "blank_environment_name"],
    )
    def test_empty_cast_or_blank_environment_name_is_refused(
        self, environment_name: str, members: tuple[CastMember, ...]
    ) -> None:
        """配役が 1 人もいないか、環境の名前が空白だけなら CastValidationException で断る。"""
        with pytest.raises(CastValidationException):
            Cast(_WORLD, environment_name, members)

    @pytest.mark.parametrize(
        "second",
        [
            CastMember(_GEN, BeingId("being_other"), "ゲンジ"),
            CastMember(PersonId("other"), BeingId("being_gen"), "ゲンジ"),
            CastMember(PersonId("other"), BeingId("being_other"), "ゲン"),
        ],
        ids=["same_person", "same_being", "same_name"],
    )
    def test_repeated_person_being_or_name_is_refused(self, second: CastMember) -> None:
        """同じ登場人物・同じ Being・同じ名前が 2 回出ると CastValidationException で断る。紹介は名前で渡すので、名前の重なりも断る。"""
        with pytest.raises(CastValidationException):
            Cast(_WORLD, "廃坑の山村", (CastMember(_GEN, BeingId("being_gen"), "ゲン"), second))

    def test_being_of_returns_the_being_playing_the_person(self) -> None:
        """ゲンを演じる Being は being_gen になり、配役に無いミオを聞くと PersonNotCastException で断る。"""
        cast = _cast()

        assert cast.being_of(_GEN) == BeingId("being_gen")
        with pytest.raises(PersonNotCastException):
            cast.being_of(PersonId("mio"))

    def test_person_not_cast_is_refused(self) -> None:
        """配役に無い登場人物に渡そうとすると PersonNotCastException で断る。"""
        with pytest.raises(PersonNotCastException):
            _cast().brief(PersonId("mio"), orientation=_ORIENTATION, imposed_goal="外へ出る。", known_people=())


class TestCastBrief:
    """Cast.brief が、知っている人を Being の名前の紹介にした取り決めを持ち、渡したことをドメインイベントで知らせることを保証する。"""

    def test_entry_introduces_known_people_by_their_being_names(self) -> None:
        """ゲンが知っている人をサヨとすると、取り決めは環境の名前・課す目的・サヨの紹介を持ち、ハルは紹介しない。"""
        cast = _cast()

        cast.brief(_GEN, orientation=_ORIENTATION, imposed_goal="外へ出る。", known_people=(_SAYO,))

        assert cast.entry_of(_GEN) == EnvironmentEntry(
            environment_name="廃坑の山村", imposed_goal="外へ出る。", introductions=(Introduction(name="サヨ"),)
        )
        assert cast.orientation_of(_GEN) == _ORIENTATION

    def test_brief_records_event_with_entry_and_orientation(self) -> None:
        """ゲンに渡すと、世界・登場人物・Being・取り決め・案内を持つ BeingCastInWorldEvent が 1 件たまる。"""
        cast = _cast()

        cast.brief(_GEN, orientation=_ORIENTATION, imposed_goal="外へ出る。", known_people=(_SAYO,))

        [event] = cast.get_events()
        assert isinstance(event, BeingCastInWorldEvent)
        assert (event.world, event.person, event.being_id, event.entry, event.orientation) == (
            _WORLD,
            _GEN,
            BeingId("being_gen"),
            cast.entry_of(_GEN),
            _ORIENTATION,
        )

    def test_known_person_not_cast_is_refused_without_briefing(self) -> None:
        """知っている人が配役に無いと PersonNotCastException で断り、ゲンには何も渡さず、イベントもためない。"""
        cast = _cast()

        with pytest.raises(PersonNotCastException):
            cast.brief(_GEN, orientation=_ORIENTATION, imposed_goal="外へ出る。", known_people=(PersonId("mio"),))

        assert cast.get_events() == []
        with pytest.raises(PersonNotBriefedException):
            cast.entry_of(_GEN)

    def test_second_brief_to_the_same_person_is_refused(self) -> None:
        """ゲンに 2 回渡そうとすると PersonAlreadyBriefedException で断り、最初の取り決めのまま、イベントも 1 件のまま。"""
        cast = _cast()
        cast.brief(_GEN, orientation=_ORIENTATION, imposed_goal="外へ出る。", known_people=(_SAYO,))

        with pytest.raises(PersonAlreadyBriefedException):
            cast.brief(_GEN, orientation=_ORIENTATION, imposed_goal="村に残る。", known_people=())

        assert cast.entry_of(_GEN).imposed_goal == "外へ出る。"
        assert len(cast.get_events()) == 1

    def test_entry_before_brief_is_refused(self) -> None:
        """まだ渡していない人の取り決めを聞くと PersonNotBriefedException で断る。"""
        with pytest.raises(PersonNotBriefedException):
            _cast().entry_of(_SAYO)
