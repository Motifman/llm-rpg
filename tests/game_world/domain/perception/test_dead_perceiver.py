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
    DeadPerceiver,
    Notable,
    NoTarget,
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
from ai_rpg_world.game_world.domain.perception.not_perceived_reason import NotPerceivedReason
from ai_rpg_world.game_world.domain.perception.nothing_in_view import NothingInView
from ai_rpg_world.game_world.domain.perception.scene_conditions import SceneConditions
from ai_rpg_world.game_world.domain.perception.sound_stimulus import NotWhispered
from ai_rpg_world.game_world.domain.perception.surroundings import SpotContents, VisibleSurroundings
from ai_rpg_world.game_world.domain.rules.stealth_rule import StealthRule
from ai_rpg_world.game_world.domain.sound import HearingValues, Loudness, SoundLevel, SoundReach
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId, WorldTick
from tests.game_world.domain.perception._builders import ALICE, BOB, SQUARE, VIEW, about, awake
from tests.game_world.support.world_in_memory import FractionsInOrder
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_RULES = world_rules_for_tests()
_AT = WorldTick(4)
_NATSU = DeadPerceiver(person=ALICE)


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

    def conditions_at(self, spot: SpotId) -> SceneConditions:
        raise AssertionError(f"looked at the conditions of {spot.value}")


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


def _whisper_to_natsu() -> SoundStimulus:
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


_STIMULI_THAT_REACH_THE_LIVING = {
    "扉が壊れるのが見える": _door_broken_in_the_square,
    "扉が壊れる音が聞こえる": _door_crashing_in_the_square,
    "本人にささやかれる": _whisper_to_natsu,
    "本人の体が殴られる": _struck,
    "本人に知らせが届く": _told_to_gather,
}


class TestDeadPerceiverPerceivesNothing:
    """DeadPerceiver が、どの刺激も知覚せず、見渡しても何も見えないことを保証する。"""

    @pytest.mark.parametrize("stimulus", _STIMULI_THAT_REACH_THE_LIVING.values(), ids=_STIMULI_THAT_REACH_THE_LIVING)
    def test_living_person_in_the_same_place_perceives_the_stimulus(self, stimulus: Callable[[], Stimulus]) -> None:
        """明るい広場で、生きているナツなら、見える・聞こえる・本人の体・知らせの刺激をどれも Perceived で受ける。"""
        outcome = stimulus().perceived_in(awake(ALICE, SQUARE), _BrightSquareWhereEverySoundCarries())

        assert isinstance(outcome, Perceived)

    @pytest.mark.parametrize(
        ("stimulus", "reason"),
        [
            (_door_broken_in_the_square, NotPerceivedReason.ELSEWHERE),
            (_door_crashing_in_the_square, NotPerceivedReason.ELSEWHERE),
            (_whisper_to_natsu, NotPerceivedReason.ELSEWHERE),
            (_struck, NotPerceivedReason.NOT_OWN_BODY),
            (_told_to_gather, NotPerceivedReason.DEAD),
        ],
        ids=list(_STIMULI_THAT_REACH_THE_LIVING),
    )
    def test_dead_person_who_does_not_act_perceives_no_stimulus(
        self, stimulus: Callable[[], Stimulus], reason: NotPerceivedReason
    ) -> None:
        """死者が行動しない世界で死んだナツには、生きていれば届く刺激がどれも NotPerceived になる。

        居場所が無いので、見える・聞こえる刺激は「その場にいない」、体の刺激は「本人の体ではない」になる。
        「死んでいる」になるのは、宛先に入っていた知らせだけ。
        """
        outcome = stimulus().perceived_in(_NATSU, _BrightSquareWhereEverySoundCarries())

        assert outcome == NotPerceived(reason)

    def test_dead_person_who_does_not_act_has_nothing_in_view(self) -> None:
        """死者が行動しない世界で死んだナツが見渡すと、どの場所の明るさも中身も見ずに NothingInView になる。"""
        perceiver: Perceiver = _NATSU

        assert VisibleSurroundings.seen_by(perceiver, _SurroundingsNotToBeLookedAt()) == NothingInView()
