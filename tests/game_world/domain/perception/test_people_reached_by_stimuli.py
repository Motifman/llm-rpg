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
from ai_rpg_world.game_world.domain.perception.not_perceived_reason import NotPerceivedReason
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

    def not_perceived(self, perceiver: PersonId, reason: NotPerceivedReason) -> None:
        pass


def _ache(person: PersonId, text: str) -> BodilyStimulus:
    return BodilyStimulus(person=person, text=about(text), salience=Notable(), at=_AT)


def _call(text: str) -> AnnouncementStimulus:
    return AnnouncementStimulus(audience=frozenset({ALICE, BOB}), text=about(text), salience=Notable(), at=_AT)


def _fall_seen(
    *, always_delivered: bool = False, noticed_later: NotNoticedLater | str = NotNoticedLater()
) -> SightStimulus:
    return SightStimulus(
        where=SQUARE,
        witness=SightTexts(
            clear=about("{actor}が倒れた", actor=BOB),
            dim=about("{actor}が倒れた", actor=BOB),
            unseen_actor=NotSeenWithoutActor(),
            noticed_later=noticed_later if isinstance(noticed_later, NotNoticedLater) else about(noticed_later),
        ),
        target=NoTarget(),
        seen_in_dark=False,
        manner=Openly(),
        actor_departed=False,
        involved=(ALICE, BOB),
        salience=Notable(),
        always_delivered=always_delivered,
        at=_AT,
    )


class TestPeopleReachedByStimuli:
    """PeopleReachedByStimuli.deliver が、同じものを別の感覚で知る刺激を 1 人に最初の 1 つに絞り、always_delivered の刺激と世界の知らせは重ねて届けることを保証する。"""

    def test_second_stimulus_does_not_reach_someone_already_reached(self) -> None:
        """アリスに足の痛みが届いたあとの「ボブが倒れた」の目撃は、アリスには届かない。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_ache(ALICE, "足が痛む"), awake(ALICE), _BrightSenses())
        reached.deliver(_fall_seen(), awake(ALICE), _BrightSenses())

        assert recipient.perceived_texts == [(ALICE, "足が痛む")]

    def test_stimulus_not_perceived_leaves_the_person_unreached(self) -> None:
        """ボブの足の痛みはアリスに知覚されないので、アリスは届いていない人のままで、続く目撃は届く。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_ache(BOB, "足が痛む"), awake(ALICE), _BrightSenses())
        reached.deliver(_fall_seen(), awake(ALICE), _BrightSenses())

        assert recipient.perceived_texts == [(ALICE, "{actor}が倒れた")]

    def test_reaching_one_person_does_not_stop_another(self) -> None:
        """アリスに目撃が届いても、ボブには同じ目撃が届く。届いた記録は人ごと。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_ache(ALICE, "足が痛む"), awake(ALICE), _BrightSenses())
        reached.deliver(_fall_seen(), awake(BOB), _BrightSenses())

        assert recipient.perceived_texts == [(ALICE, "足が痛む"), (BOB, "{actor}が倒れた")]

    def test_always_delivered_stimulus_reaches_someone_already_reached(self) -> None:
        """アリスに足の痛みが届いたあとでも、always_delivered の「ボブが倒れた」は重ねて届く。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_ache(ALICE, "足が痛む"), awake(ALICE), _BrightSenses())
        reached.deliver(_fall_seen(always_delivered=True), awake(ALICE), _BrightSenses())

        assert recipient.perceived_texts == [(ALICE, "足が痛む"), (ALICE, "{actor}が倒れた")]

    def test_announcement_reaches_someone_already_reached(self) -> None:
        """アリスに足の痛みが届いたあとでも、世界の知らせ「鐘が鳴った」は重ねて届く。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_ache(ALICE, "足が痛む"), awake(ALICE), _BrightSenses())
        reached.deliver(_call("鐘が鳴った"), awake(ALICE), _BrightSenses())

        assert recipient.perceived_texts == [(ALICE, "足が痛む"), (ALICE, "鐘が鳴った")]

    def test_announcement_does_not_count_as_reaching(self) -> None:
        """世界の知らせ「鐘が鳴った」が届いたあとのアリスにも、always_delivered でない「ボブが倒れた」の目撃が届く。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_call("鐘が鳴った"), awake(ALICE), _BrightSenses())
        reached.deliver(_fall_seen(), awake(ALICE), _BrightSenses())

        assert recipient.perceived_texts == [(ALICE, "鐘が鳴った"), (ALICE, "{actor}が倒れた")]

    def test_notice_kept_for_later_counts_as_reaching(self) -> None:
        """倒れているアリスが目撃を起きてから知る形で受けると、届いた扱いになり、次の目撃はためない。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_fall_seen(noticed_later="誰かが倒れる音がした"), fallen(ALICE), _BrightSenses())
        reached.deliver(_fall_seen(noticed_later="何かが崩れる音がした"), fallen(ALICE), _BrightSenses())

        assert [(person, notice.text.template) for person, notice in recipient.notices] == [
            (ALICE, "誰かが倒れる音がした")
        ]

    def test_fallen_person_keeps_every_announcement(self) -> None:
        """倒れているアリスには、世界の知らせ「鐘が鳴った」と「門が開いた」が、どちらも起きてから知る形でたまる。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_call("鐘が鳴った"), fallen(ALICE), _BrightSenses())
        reached.deliver(_call("門が開いた"), fallen(ALICE), _BrightSenses())

        assert [(person, notice.text.template) for person, notice in recipient.notices] == [
            (ALICE, "鐘が鳴った"),
            (ALICE, "門が開いた"),
        ]
        assert recipient.perceived_texts == []
