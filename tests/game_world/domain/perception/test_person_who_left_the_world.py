from __future__ import annotations

from collections.abc import Callable

import pytest

from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.condition.random_source import RandomSource
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
from ai_rpg_world.game_world.domain.perception import (
    AnnouncementStimulus,
    BodilyStimulus,
    MissedNotice,
    Notable,
    NoTarget,
    NoticedLater,
    NotNoticedLater,
    NotPerceived,
    NotSeenWithoutActor,
    Perceived,
    Perceiver,
    SightStimulus,
    SightTexts,
    SoundStimulus,
    Stimulus,
    Voice,
)
from ai_rpg_world.game_world.domain.perception.nothing_in_view import NothingInView
from ai_rpg_world.game_world.domain.perception.perceiver import PersonWhoLeftTheWorld
from ai_rpg_world.game_world.domain.perception.sound_stimulus import NotWhispered
from ai_rpg_world.game_world.domain.perception.surroundings import SpotContents, VisibleSurroundings
from ai_rpg_world.game_world.domain.person.life_state import Alive, Down, Starvation
from ai_rpg_world.game_world.domain.rules.stealth_rule import StealthRule
from ai_rpg_world.game_world.domain.sound import HearingValues, Loudness, SoundLevel, SoundReach
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId, WorldTick
from tests.game_world.domain.perception._builders import ALICE, BOB, SQUARE, VIEW, about
from tests.game_world.support.world_in_memory import FractionsInOrder
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_RULES = world_rules_for_tests()
_AT = WorldTick(4)
_HAL = PersonWhoLeftTheWorld(person=ALICE, life=Alive())
_FAINTED_HAL = PersonWhoLeftTheWorld(person=ALICE, life=Down(fell_at=WorldTick(0), cause=Starvation()))


class _BrightSquareWhereEverySoundCarries:
    def lighting_at(self, spot: SpotId) -> Lighting:
        return Lighting.BRIGHT

    def reach_of(self, origin: SpotId, loudness: Loudness) -> SoundReach:
        return SoundReach(levels={SQUARE: SoundLevel(90)})

    def view_for(self, viewer: PersonId) -> PeopleAsSeen:
        return VIEW

    def random(self) -> RandomSource:
        return FractionsInOrder(())

    def stealth(self) -> StealthRule:
        return _RULES.stealth

    def hearing(self) -> HearingValues:
        return _RULES.hearing


class _SurroundingsNotToBeLookedAt:
    def lighting_at(self, spot: SpotId) -> Lighting:
        raise AssertionError(f"looked at the lighting of {spot.value}")

    def contents_at(self, spot: SpotId) -> SpotContents:
        raise AssertionError(f"looked at the contents of {spot.value}")


def _door_broken_in_the_square() -> SightStimulus:
    return SightStimulus(
        where=SQUARE,
        witness=SightTexts(
            clear=about("{actor}が扉を壊した", actor=BOB),
            dim=about("{actor}が扉のあたりで何かしている", actor=BOB),
            unseen_actor=NotSeenWithoutActor(),
            noticed_later=NotNoticedLater(),
        ),
        target=NoTarget(),
        seen_in_dark=True,
        manner=Openly(),
        actor_departed=False,
        involved=(BOB, ALICE),
        salience=Notable(),
        always_delivered=True,
        at=_AT,
    )


def _door_crashing_in_the_square() -> SoundStimulus:
    return SoundStimulus(
        origin=SQUARE,
        loudness=Loudness.VERY_LOUD,
        clear=about("{actor}が扉を壊す音がした", actor=BOB),
        muffled=about("何かが壊れる音がした"),
        noticed_later=NotNoticedLater(),
        source=Voice(whispered_to=NotWhispered()),
        involved=(BOB, ALICE),
        salience=Notable(),
        at=_AT,
    )


def _whisper_to_hal() -> SoundStimulus:
    return SoundStimulus(
        origin=SQUARE,
        loudness=Loudness.WHISPER,
        clear=about("{speaker}が「起きて」とささやいた", speaker=BOB),
        muffled=about("{speaker}が何かささやいた", speaker=BOB),
        noticed_later=NotNoticedLater(),
        source=Voice(whispered_to=ALICE),
        involved=(BOB, ALICE),
        salience=Notable(),
        at=_AT,
    )


def _struck() -> BodilyStimulus:
    return BodilyStimulus(person=ALICE, text=about("{striker}に殴られた", striker=BOB), salience=Notable(), at=_AT)


def _told_to_gather() -> AnnouncementStimulus:
    return AnnouncementStimulus(
        audience=frozenset({ALICE}), text=about("{caller}が皆を呼んでいる", caller=BOB), salience=Notable(), at=_AT
    )


def _hal_rescued() -> AnnouncementStimulus:
    return AnnouncementStimulus(
        audience=frozenset({ALICE}),
        text=about("{each_person}は昇降機で外へ出た", each_person=ALICE),
        salience=Notable(),
        at=_AT,
        reaches_who_left_the_world=True,
    )


_STIMULI_IN_THE_WORLD = {
    "扉が壊れるのが見える": _door_broken_in_the_square,
    "扉が壊れる音が聞こえる": _door_crashing_in_the_square,
    "本人にささやかれる": _whisper_to_hal,
    "本人の体が殴られる": _struck,
    "本人に世界の知らせが届く": _told_to_gather,
}


class TestPersonWhoLeftTheWorld:
    """PersonWhoLeftTheWorld が、世界から外れた人にも宛てた知らせだけを受け、世界の中の刺激は知覚しないことを保証する。"""

    def test_person_who_left_receives_the_outcome_announcement(self) -> None:
        """昇降機で外へ出たハルは、居場所が無くても、自分に宛てた結末の知らせ「ハルは昇降機で外へ出た」を目立つ知らせとして受ける。"""
        outcome = _hal_rescued().perceived_in(_HAL, _BrightSquareWhereEverySoundCarries())

        assert isinstance(outcome, Perceived)
        assert (outcome.text.template, outcome.calls_attention) == ("{each_person}は昇降機で外へ出た", True)

    def test_fainted_person_who_left_keeps_the_outcome_announcement_for_later(self) -> None:
        """気を失ったまま外れたハルは、結末の知らせを起きてから知る形 (NoticedLater) で受ける。"""
        outcome = _hal_rescued().perceived_in(_FAINTED_HAL, _BrightSquareWhereEverySoundCarries())

        assert isinstance(outcome, NoticedLater)
        assert isinstance(outcome.notice, MissedNotice)
        assert outcome.notice.text.template == "{each_person}は昇降機で外へ出た"

    @pytest.mark.parametrize("stimulus", _STIMULI_IN_THE_WORLD.values(), ids=_STIMULI_IN_THE_WORLD)
    def test_person_who_left_perceives_nothing_in_the_world(self, stimulus: Callable[[], Stimulus]) -> None:
        """外れたハルには、もといた広場の目撃・物音・ささやき・体の刺激も、宛先に入った世界の知らせ「皆を呼んでいる」も NotPerceived になる。"""
        outcome = stimulus().perceived_in(_HAL, _BrightSquareWhereEverySoundCarries())

        assert outcome == NotPerceived()

    def test_person_who_left_has_nothing_in_view(self) -> None:
        """外れたハルが見渡すと、どの場所の明るさも中身も見ずに NothingInView になる。"""
        perceiver: Perceiver = _HAL

        assert VisibleSurroundings.seen_by(perceiver, _SurroundingsNotToBeLookedAt()) == NothingInView()
