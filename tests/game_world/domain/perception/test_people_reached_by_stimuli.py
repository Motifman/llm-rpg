from __future__ import annotations

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
    NotNoticedLater,
    NotSeenWithoutActor,
    Perceived,
    SightStimulus,
    SightTexts,
)
from ai_rpg_world.game_world.domain.perception.people_reached_by_stimuli import PeopleReachedByStimuli
from ai_rpg_world.game_world.domain.rules.stealth_rule import StealthRule
from ai_rpg_world.game_world.domain.sound import HearingValues, Loudness, SoundReach
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId, WorldTick
from tests.game_world.domain.perception._builders import ALICE, BOB, SQUARE, VIEW, about, awake, fallen
from tests.game_world.support.world_in_memory import FractionsInOrder
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_RULES = world_rules_for_tests()
_AT = WorldTick(4)


class _BrightSenses:
    def lighting_at(self, spot: SpotId) -> Lighting:
        return Lighting.BRIGHT

    def reach_of(self, origin: SpotId, loudness: Loudness) -> SoundReach:
        return SoundReach(levels={})

    def view_for(self, viewer: PersonId) -> PeopleAsSeen:
        return VIEW

    def random(self) -> RandomSource:
        return FractionsInOrder(())

    def stealth(self) -> StealthRule:
        return _RULES.stealth

    def hearing(self) -> HearingValues:
        return _RULES.hearing


class _Recipient:
    def __init__(self) -> None:
        self.perceived_texts: list[tuple[PersonId, str]] = []
        self.notices: list[tuple[PersonId, MissedNotice]] = []

    def perceived(self, perceived: Perceived) -> None:
        self.perceived_texts.append((perceived.perceiver, perceived.text.template))

    def noticed_later(self, perceiver: PersonId, notice: MissedNotice) -> None:
        self.notices.append((perceiver, notice))


def _ache(person: PersonId, text: str) -> BodilyStimulus:
    return BodilyStimulus(person=person, text=about(text), salience=Notable(), at=_AT)


def _call(text: str) -> AnnouncementStimulus:
    return AnnouncementStimulus(audience=frozenset({ALICE, BOB}), text=about(text), salience=Notable(), at=_AT)


def _fall_seen(*, always_delivered: bool) -> SightStimulus:
    return SightStimulus(
        where=SQUARE,
        witness=SightTexts(
            clear=about("{actor}が倒れた", actor=BOB),
            dim=about("{actor}が倒れた", actor=BOB),
            unseen_actor=NotSeenWithoutActor(),
            noticed_later=NotNoticedLater(),
        ),
        target=NoTarget(),
        seen_in_dark=False,
        manner=Openly(),
        actor_departed=False,
        involved=(BOB,),
        salience=Notable(),
        always_delivered=always_delivered,
        at=_AT,
    )


class TestPeopleReachedByStimuli:
    """PeopleReachedByStimuli.deliver が、1 人に届ける刺激を最初の 1 つに絞り、always_delivered の刺激だけは重ねて届けることを保証する。"""

    def test_second_stimulus_does_not_reach_someone_already_reached(self) -> None:
        """アリスに足の痛みが届いたあとの知らせは、アリスには届かない。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_ache(ALICE, "足が痛む"), awake(ALICE), _BrightSenses())
        reached.deliver(_call("鐘が鳴った"), awake(ALICE), _BrightSenses())

        assert recipient.perceived_texts == [(ALICE, "足が痛む")]

    def test_stimulus_not_perceived_leaves_the_person_unreached(self) -> None:
        """ボブの足の痛みはアリスに知覚されないので、アリスは届いていない人のままで、続く知らせは届く。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_ache(BOB, "足が痛む"), awake(ALICE), _BrightSenses())
        reached.deliver(_call("鐘が鳴った"), awake(ALICE), _BrightSenses())

        assert recipient.perceived_texts == [(ALICE, "鐘が鳴った")]

    def test_reaching_one_person_does_not_stop_another(self) -> None:
        """アリスに知らせが届いても、ボブには同じ知らせが届く。届いた記録は人ごと。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_call("鐘が鳴った"), awake(ALICE), _BrightSenses())
        reached.deliver(_call("鐘が鳴った"), awake(BOB), _BrightSenses())

        assert recipient.perceived_texts == [(ALICE, "鐘が鳴った"), (BOB, "鐘が鳴った")]

    def test_always_delivered_stimulus_reaches_someone_already_reached(self) -> None:
        """アリスに知らせが届いたあとでも、always_delivered の「ボブが倒れた」は重ねて届く。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_call("鐘が鳴った"), awake(ALICE), _BrightSenses())
        reached.deliver(_fall_seen(always_delivered=True), awake(ALICE), _BrightSenses())

        assert recipient.perceived_texts == [(ALICE, "鐘が鳴った"), (ALICE, "{actor}が倒れた")]

    def test_ordinary_sight_does_not_reach_someone_already_reached(self) -> None:
        """always_delivered でない同じ「ボブが倒れた」は、知らせが届いたあとのアリスには届かない。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_call("鐘が鳴った"), awake(ALICE), _BrightSenses())
        reached.deliver(_fall_seen(always_delivered=False), awake(ALICE), _BrightSenses())

        assert recipient.perceived_texts == [(ALICE, "鐘が鳴った")]

    def test_notice_kept_for_later_counts_as_reaching(self) -> None:
        """倒れているアリスが最初の知らせを起きてから知る形で受けると、届いた扱いになり、次の知らせは渡さない。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_call("鐘が鳴った"), fallen(ALICE), _BrightSenses())
        reached.deliver(_call("門が開いた"), fallen(ALICE), _BrightSenses())

        assert [(person, notice.text.template) for person, notice in recipient.notices] == [(ALICE, "鐘が鳴った")]
        assert recipient.perceived_texts == []
