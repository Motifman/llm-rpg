from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.declaration.verb import AnnouncementTo, SightAt, SoundFrom
from ai_rpg_world.game_world.domain.declaration.verb.sound_declaration import SoundDeclaration
from ai_rpg_world.game_world.domain.exception.verb_declaration_exception import PersonInNoticeTextException
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import Notable
from ai_rpg_world.game_world.domain.sound.loudness import Loudness
from tests.game_world.support.verb_declarations_for_tests import seen_clearly_only
from tests.game_world.support.verb_parts_for_tests import AlwaysHolds
from tests.game_world.support.world_design_for_tests import spot

_WELL = spot("well")


def _sound(clear: str, muffled: str = "どこかで音がした。") -> SoundDeclaration:
    return SoundDeclaration(
        loudness=Loudness.LOUD, clear=TextWithUnassignedPeople(clear), muffled=TextWithUnassignedPeople(muffled)
    )


class TestHappeningNoticeTexts:
    """出来事の知らせ (SightAt / SoundFrom / AnnouncementTo) が、人を当てられない文に人のプレースホルダーを書かせないことを保証する。"""

    def test_sight_notice_naming_a_person_is_refused_naming_the_text(self) -> None:
        """見える知らせの文に {actor} を書くと、文を添えて PersonInNoticeTextException を投げる。"""
        with pytest.raises(PersonInNoticeTextException, match="sight_at"):
            SightAt(spot=_WELL, texts=seen_clearly_only("{actor}が灯を揺らした。"), salience=Notable())

    def test_sound_notice_naming_a_person_in_the_muffled_text_is_refused(self) -> None:
        """聞こえる知らせのくぐもった文に {each_person} を書くと、PersonInNoticeTextException を投げる。"""
        with pytest.raises(PersonInNoticeTextException, match="sound_from"):
            SoundFrom(spot=_WELL, sound=_sound("岩が崩れた。", "{each_person}の近くで音がした。"), salience=Notable())

    def test_announcement_naming_a_person_is_refused(self) -> None:
        """世界の知らせの文に {each_person} を書くと、PersonInNoticeTextException を投げる。"""
        with pytest.raises(PersonInNoticeTextException, match="announcement_to"):
            AnnouncementTo(
                audience=PeopleSelection(where=AlwaysHolds()),
                text=TextWithUnassignedPeople("{each_person}は鐘の音を聞いた。"),
                salience=Notable(),
            )

    def test_notices_without_people_are_kept(self) -> None:
        """人のプレースホルダーの無い文の知らせは、どれも作れる。"""
        SightAt(spot=_WELL, texts=seen_clearly_only("井戸の灯が揺れた。"), salience=Notable())
        SoundFrom(spot=_WELL, sound=_sound("岩が崩れた。"), salience=Notable())
        AnnouncementTo(
            audience=PeopleSelection(where=AlwaysHolds()),
            text=TextWithUnassignedPeople("招集の鐘が鳴った。"),
            salience=Notable(),
        )
