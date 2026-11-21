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
from ai_rpg_world.game_world.domain.perception.delivery_rank import Sense
from ai_rpg_world.game_world.domain.perception.not_perceived_reason import NotPerceivedReason
from ai_rpg_world.game_world.domain.perception.people_reached_by_stimuli import PeopleReachedByStimuli
from ai_rpg_world.game_world.domain.perception.perception_cause import HappeningFiring
from ai_rpg_world.game_world.domain.perception.perception_delivery_report import StimulusDescription
from ai_rpg_world.game_world.domain.rules.stealth_rule import StealthRule
from ai_rpg_world.game_world.domain.sound import HearingValues, Loudness, SoundReach
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId, WorldTick
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
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

        reached.deliver(_ache(ALICE, "足が痛む"), (awake(ALICE),), _BrightSenses())
        reached.deliver(_fall_seen(), (awake(ALICE),), _BrightSenses())

        assert recipient.perceived_texts == [(ALICE, "足が痛む")]

    def test_stimulus_not_perceived_leaves_the_person_unreached(self) -> None:
        """ボブの足の痛みはアリスに知覚されないので、アリスは届いていない人のままで、続く目撃は届く。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_ache(BOB, "足が痛む"), (awake(ALICE),), _BrightSenses())
        reached.deliver(_fall_seen(), (awake(ALICE),), _BrightSenses())

        assert recipient.perceived_texts == [(ALICE, "{actor}が倒れた")]

    def test_reaching_one_person_does_not_stop_another(self) -> None:
        """アリスに目撃が届いても、ボブには同じ目撃が届く。届いた記録は人ごと。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_ache(ALICE, "足が痛む"), (awake(ALICE),), _BrightSenses())
        reached.deliver(_fall_seen(), (awake(BOB),), _BrightSenses())

        assert recipient.perceived_texts == [(ALICE, "足が痛む"), (BOB, "{actor}が倒れた")]

    def test_always_delivered_stimulus_reaches_someone_already_reached(self) -> None:
        """アリスに足の痛みが届いたあとでも、always_delivered の「ボブが倒れた」は重ねて届く。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_ache(ALICE, "足が痛む"), (awake(ALICE),), _BrightSenses())
        reached.deliver(_fall_seen(always_delivered=True), (awake(ALICE),), _BrightSenses())

        assert recipient.perceived_texts == [(ALICE, "足が痛む"), (ALICE, "{actor}が倒れた")]

    def test_announcement_reaches_someone_already_reached(self) -> None:
        """アリスに足の痛みが届いたあとでも、世界の知らせ「鐘が鳴った」は重ねて届く。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_ache(ALICE, "足が痛む"), (awake(ALICE),), _BrightSenses())
        reached.deliver(_call("鐘が鳴った"), (awake(ALICE),), _BrightSenses())

        assert recipient.perceived_texts == [(ALICE, "足が痛む"), (ALICE, "鐘が鳴った")]

    def test_announcement_does_not_count_as_reaching(self) -> None:
        """世界の知らせ「鐘が鳴った」が届いたあとのアリスにも、always_delivered でない「ボブが倒れた」の目撃が届く。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_call("鐘が鳴った"), (awake(ALICE),), _BrightSenses())
        reached.deliver(_fall_seen(), (awake(ALICE),), _BrightSenses())

        assert recipient.perceived_texts == [(ALICE, "鐘が鳴った"), (ALICE, "{actor}が倒れた")]

    def test_notice_kept_for_later_counts_as_reaching(self) -> None:
        """倒れているアリスが目撃を起きてから知る形で受けると、届いた扱いになり、次の目撃はためない。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_fall_seen(noticed_later="誰かが倒れる音がした"), (fallen(ALICE),), _BrightSenses())
        reached.deliver(_fall_seen(noticed_later="何かが崩れる音がした"), (fallen(ALICE),), _BrightSenses())

        assert [(person, notice.text.template) for person, notice in recipient.notices] == [
            (ALICE, "誰かが倒れる音がした")
        ]

    def test_fallen_person_keeps_every_announcement(self) -> None:
        """倒れているアリスには、世界の知らせ「鐘が鳴った」と「門が開いた」が、どちらも起きてから知る形でたまる。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver(_call("鐘が鳴った"), (fallen(ALICE),), _BrightSenses())
        reached.deliver(_call("門が開いた"), (fallen(ALICE),), _BrightSenses())

        assert [(person, notice.text.template) for person, notice in recipient.notices] == [
            (ALICE, "鐘が鳴った"),
            (ALICE, "門が開いた"),
        ]
        assert recipient.perceived_texts == []


class TestPerceptionDeliveryReport:
    """PeopleReachedByStimuli.report が、刺激ごとに、届いた人・ためた人・届く見込みがあって届かなかった人と理由を残すことを保証する。"""

    def test_report_carries_cause_tick_and_the_stimulus(self) -> None:
        """出来事「扉が壊れる」の発火で届けた目撃の記録には、原因・tick・刺激の種類と文と場所が残る。"""
        reached = PeopleReachedByStimuli(_Recipient())
        reached.deliver(_fall_seen(), (awake(ALICE),), _BrightSenses())

        report = reached.report(HappeningFiring(HappeningId("door_breaks")), WorldTick(7))

        assert report.cause == HappeningFiring(HappeningId("door_breaks"))
        assert report.at == WorldTick(7)
        assert [result.stimulus for result in report.stimuli] == [
            StimulusDescription(sense=Sense.SIGHT, text="{actor}が倒れた", where=SQUARE, addressed_to=frozenset())
        ]

    def test_report_tells_perceived_kept_and_already_perceived_apart(self) -> None:
        """足の痛みが届いたアリスは目撃で「同じものをもう知った」、倒れて関わっているボブは「ためた」と残る。"""
        reached = PeopleReachedByStimuli(_Recipient())
        reached.deliver(_ache(ALICE, "足が痛む"), (awake(ALICE),), _BrightSenses())
        reached.deliver(_fall_seen(noticed_later="誰かが倒れる音がした"), (awake(ALICE), fallen(BOB)), _BrightSenses())

        sight = reached.report(HappeningFiring(HappeningId("door_breaks")), _AT).stimuli[1]

        assert sight.perceived_by == ()
        assert sight.kept_for == (BOB,)
        assert dict(sight.missed_by) == {ALICE: NotPerceivedReason.ALREADY_PERCEIVED}

    def test_people_with_no_chance_of_reaching_are_left_out(self) -> None:
        """アリスの足の痛みに対するボブ (本人の体ではない) と、アリス宛ての知らせに対するボブ (宛先でない) は記録に残らない。"""
        reached = PeopleReachedByStimuli(_Recipient())
        reached.deliver(_ache(ALICE, "足が痛む"), (awake(ALICE), awake(BOB)), _BrightSenses())
        reached.deliver(
            AnnouncementStimulus(audience=frozenset({ALICE}), text=about("鐘が鳴った"), salience=Notable(), at=_AT),
            (awake(ALICE), awake(BOB)),
            _BrightSenses(),
        )

        results = reached.report(HappeningFiring(HappeningId("bell")), _AT).stimuli

        assert [(result.perceived_by, dict(result.missed_by)) for result in results] == [((ALICE,), {}), ((ALICE,), {})]

    def test_an_unconscious_bystander_is_kept_with_the_reason(self) -> None:
        """関わっていない倒れたボブには目撃が届かず、記録に理由「気を失っている」が残る。"""
        reached = PeopleReachedByStimuli(_Recipient())
        reached.deliver(_fall_seen(), (fallen(BOB),), _BrightSenses())

        sight = reached.report(HappeningFiring(HappeningId("door_breaks")), _AT).stimuli[0]

        assert dict(sight.missed_by) == {BOB: NotPerceivedReason.UNCONSCIOUS}
