from __future__ import annotations

from ai_rpg_world.game_world.domain.action.manner import Openly, Stealthily
from ai_rpg_world.game_world.domain.condition.random_source import RandomSource
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
from ai_rpg_world.game_world.domain.perception import (
    AnnouncementStimulus,
    Background,
    BodilyStimulus,
    MissedNotice,
    Notable,
    NoTarget,
    NotNoticedLater,
    NotSeenInDim,
    NotSeenWithoutActor,
    NotWhispered,
    Perceived,
    SightStimulus,
    SightTexts,
    SoundStimulus,
    Voice,
)
from ai_rpg_world.game_world.domain.perception.delivery_rank import Sense
from ai_rpg_world.game_world.domain.perception.not_perceived_reason import NotPerceivedReason
from ai_rpg_world.game_world.domain.perception.people_reached_by_stimuli import PeopleReachedByStimuli
from ai_rpg_world.game_world.domain.perception.perception_cause import HappeningFiring
from ai_rpg_world.game_world.domain.perception.perception_delivery_report import StimulusDescription
from ai_rpg_world.game_world.domain.rules.stealth_rule import StealthRule
from ai_rpg_world.game_world.domain.sound import HearingValues, Loudness, SoundReach
from ai_rpg_world.game_world.domain.sound.sound_level import SoundLevel
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId, WorldTick
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from tests.game_world.domain.perception._builders import ALICE, BOB, CAROL, SQUARE, VIEW, about, awake, fallen
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
    """PeopleReachedByStimuli.deliver_all が、伝える量の同じ刺激 (出来事どうし) では 1 人に先に並んだ 1 つに絞り、always_delivered の刺激と世界の知らせは重ねて届けることを保証する。"""

    def test_second_stimulus_does_not_reach_someone_already_reached(self) -> None:
        """アリスに足の痛みが届いたあとの「ボブが倒れた」の目撃は、アリスには届かない。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver_all(
            (
                _ache(ALICE, "足が痛む"),
                _fall_seen(),
            ),
            (awake(ALICE),),
            _BrightSenses(),
        )

        assert recipient.perceived_texts == [(ALICE, "足が痛む")]

    def test_stimulus_not_perceived_leaves_the_person_unreached(self) -> None:
        """ボブの足の痛みはアリスに知覚されないので、アリスは届いていない人のままで、続く目撃は届く。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver_all(
            (
                _ache(BOB, "足が痛む"),
                _fall_seen(),
            ),
            (awake(ALICE),),
            _BrightSenses(),
        )

        assert recipient.perceived_texts == [(ALICE, "{actor}が倒れた")]

    def test_reaching_one_person_does_not_stop_another(self) -> None:
        """アリスに目撃が届いても、ボブには同じ目撃が届く。届いた記録は人ごと。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver_all(
            (
                _ache(ALICE, "足が痛む"),
                _fall_seen(),
            ),
            (
                awake(ALICE),
                awake(BOB),
            ),
            _BrightSenses(),
        )

        assert recipient.perceived_texts == [(ALICE, "足が痛む"), (BOB, "{actor}が倒れた")]

    def test_always_delivered_stimulus_reaches_someone_already_reached(self) -> None:
        """アリスに足の痛みが届いたあとでも、always_delivered の「ボブが倒れた」は重ねて届く。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver_all(
            (
                _ache(ALICE, "足が痛む"),
                _fall_seen(always_delivered=True),
            ),
            (awake(ALICE),),
            _BrightSenses(),
        )

        assert recipient.perceived_texts == [(ALICE, "足が痛む"), (ALICE, "{actor}が倒れた")]

    def test_announcement_reaches_someone_already_reached(self) -> None:
        """アリスに足の痛みが届いたあとでも、世界の知らせ「鐘が鳴った」は重ねて届く。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver_all(
            (
                _ache(ALICE, "足が痛む"),
                _call("鐘が鳴った"),
            ),
            (awake(ALICE),),
            _BrightSenses(),
        )

        assert recipient.perceived_texts == [(ALICE, "足が痛む"), (ALICE, "鐘が鳴った")]

    def test_announcement_does_not_count_as_reaching(self) -> None:
        """世界の知らせ「鐘が鳴った」が届いたあとのアリスにも、always_delivered でない「ボブが倒れた」の目撃が届く。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver_all(
            (
                _call("鐘が鳴った"),
                _fall_seen(),
            ),
            (awake(ALICE),),
            _BrightSenses(),
        )

        assert recipient.perceived_texts == [(ALICE, "鐘が鳴った"), (ALICE, "{actor}が倒れた")]

    def test_notice_kept_for_later_counts_as_reaching(self) -> None:
        """倒れているアリスが目撃を起きてから知る形で受けると、届いた扱いになり、次の目撃はためない。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver_all(
            (
                _fall_seen(noticed_later="誰かが倒れる音がした"),
                _fall_seen(noticed_later="何かが崩れる音がした"),
            ),
            (fallen(ALICE),),
            _BrightSenses(),
        )

        assert [(person, notice.text.template) for person, notice in recipient.notices] == [
            (ALICE, "誰かが倒れる音がした")
        ]

    def test_fallen_person_keeps_every_announcement(self) -> None:
        """倒れているアリスには、世界の知らせ「鐘が鳴った」と「門が開いた」が、どちらも起きてから知る形でたまる。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver_all(
            (
                _call("鐘が鳴った"),
                _call("門が開いた"),
            ),
            (fallen(ALICE),),
            _BrightSenses(),
        )

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
        reached.deliver_all((_fall_seen(),), (awake(ALICE),), _BrightSenses())

        report = reached.report(HappeningFiring(HappeningId("door_breaks")), WorldTick(7))

        assert report.cause == HappeningFiring(HappeningId("door_breaks"))
        assert report.at == WorldTick(7)
        assert [result.stimulus for result in report.stimuli] == [
            StimulusDescription(sense=Sense.SIGHT, text="{actor}が倒れた", where=SQUARE, addressed_to=frozenset())
        ]

    def test_report_tells_perceived_kept_and_already_perceived_apart(self) -> None:
        """足の痛みが届いたアリスは目撃で「同じものをもう知った」、倒れて関わっているボブは「ためた」と残る。"""
        reached = PeopleReachedByStimuli(_Recipient())
        reached.deliver_all(
            (
                _ache(ALICE, "足が痛む"),
                _fall_seen(noticed_later="誰かが倒れる音がした"),
            ),
            (
                awake(ALICE),
                fallen(BOB),
            ),
            _BrightSenses(),
        )

        sight = reached.report(HappeningFiring(HappeningId("door_breaks")), _AT).stimuli[1]

        assert sight.perceived_by == ()
        assert sight.kept_for == (BOB,)
        assert dict(sight.missed_by) == {ALICE: NotPerceivedReason.ALREADY_PERCEIVED}

    def test_people_with_no_chance_of_reaching_are_left_out(self) -> None:
        """アリスの足の痛みに対するボブ (本人の体ではない) と、アリス宛ての知らせに対するボブ (宛先でない) は記録に残らない。"""
        reached = PeopleReachedByStimuli(_Recipient())
        reached.deliver_all(
            (
                _ache(ALICE, "足が痛む"),
                AnnouncementStimulus(audience=frozenset({ALICE}), text=about("鐘が鳴った"), salience=Notable(), at=_AT),
            ),
            (awake(ALICE), awake(BOB)),
            _BrightSenses(),
        )

        results = reached.report(HappeningFiring(HappeningId("bell")), _AT).stimuli

        assert [(result.perceived_by, dict(result.missed_by)) for result in results] == [((ALICE,), {}), ((ALICE,), {})]

    def test_an_unconscious_bystander_is_kept_with_the_reason(self) -> None:
        """関わっていない倒れたボブには目撃が届かず、記録に理由「気を失っている」が残る。"""
        reached = PeopleReachedByStimuli(_Recipient())
        reached.deliver_all((_fall_seen(),), (fallen(BOB),), _BrightSenses())

        sight = reached.report(HappeningFiring(HappeningId("door_breaks")), _AT).stimuli[0]

        assert dict(sight.missed_by) == {BOB: NotPerceivedReason.UNCONSCIOUS}


class _VoiceCarries(_BrightSenses):
    def __init__(self, random: FractionsInOrder | None = None) -> None:
        self._random = random if random is not None else FractionsInOrder(())

    def reach_of(self, origin: SpotId, loudness: Loudness) -> SoundReach:
        # 大きい声だけを、くぐもって聞こえる強さ (35 以上 50 未満) にする
        return SoundReach(levels={SQUARE: SoundLevel(40 if loudness is Loudness.LOUD else 75)})

    def random(self) -> RandomSource:
        return self._random


def _talk_seen(*, to: PersonId | None = None, stealthily: bool = False) -> SightStimulus:
    clear = "{actor}が何か話している" if to is None else "{actor}が{target}に何かささやいた"
    people = {"actor": BOB} if to is None else {"actor": BOB, "target": to}
    return SightStimulus(
        where=SQUARE,
        witness=SightTexts(
            clear=about(clear, **people),
            dim=NotSeenInDim(),
            unseen_actor=NotSeenWithoutActor(),
            noticed_later=NotNoticedLater(),
        ),
        target=NoTarget(),
        seen_in_dark=False,
        manner=Stealthily() if stealthily else Openly(),
        actor_departed=False,
        involved=tuple(people.values()),
        salience=Background(),
        always_delivered=False,
        at=_AT,
        withheld_from=frozenset({BOB}),
    )


def _voice(*, to: PersonId | None = None, loudness: Loudness | None = None) -> SoundStimulus:
    return SoundStimulus(
        origin=SQUARE,
        loudness=loudness if loudness is not None else (Loudness.NORMAL if to is None else Loudness.WHISPER),
        clear=about("{actor}が「灯りを点けよう」と言った", actor=BOB),
        muffled=about("誰かの話し声がした"),
        noticed_later=NotNoticedLater(),
        source=Voice(whispered_to=NotWhispered() if to is None else to),
        involved=(BOB,) if to is None else (BOB, to),
        salience=Background(),
        at=_AT,
        withheld_from=frozenset({BOB}),
    )


class TestWhatReachesEachPersonConveysTheMost:
    """PeopleReachedByStimuli.deliver_all が、1 人には知覚できた刺激のうちいちばん多くを伝えるもの (言葉 > 出来事) を 1 つ渡し、伝える量が同じなら先に並んだ刺激を渡すことを保証する。"""

    def test_voice_heard_clearly_replaces_the_sight_of_talking(self) -> None:
        """同じ場所でボブがふつうの声で話すと、アリスには「何か話している」の見える文ではなく「「灯りを点けよう」と言った」の声が届く。"""
        recipient = _Recipient()

        PeopleReachedByStimuli(recipient).deliver_all((_talk_seen(), _voice()), (awake(ALICE),), _VoiceCarries())

        assert recipient.perceived_texts == [(ALICE, "{actor}が「灯りを点けよう」と言った")]

    def test_addressee_of_a_whisper_gets_the_words(self) -> None:
        """ボブがアリスにささやくと、アリスにはささやいた言葉が届く。"""
        recipient = _Recipient()

        PeopleReachedByStimuli(recipient).deliver_all(
            (_talk_seen(to=ALICE), _voice(to=ALICE)), (awake(ALICE),), _VoiceCarries()
        )

        assert recipient.perceived_texts == [(ALICE, "{actor}が「灯りを点けよう」と言った")]

    def test_bystander_of_a_whisper_keeps_the_sight(self) -> None:
        """ボブがアリスにささやくと、そばのキャロルは声がかすかにしか聞こえず言葉が無いので、見える文「ボブがアリスに何かささやいた」が届く。"""
        recipient = _Recipient()

        PeopleReachedByStimuli(recipient).deliver_all(
            (_talk_seen(to=ALICE), _voice(to=ALICE)), (awake(CAROL),), _VoiceCarries()
        )

        assert recipient.perceived_texts == [(CAROL, "{actor}が{target}に何かささやいた")]

    def test_replaced_sight_is_reported_as_already_perceived(self) -> None:
        """声に差し替えた見える刺激は、届けた記録でアリスを「同じものをもう知った」とし、声の記録はアリスに届いたとする。"""
        reached = PeopleReachedByStimuli(_Recipient())
        reached.deliver_all((_talk_seen(), _voice()), (awake(ALICE),), _VoiceCarries())

        sight, voice = reached.report(HappeningFiring(HappeningId("talk")), _AT).stimuli

        assert (sight.perceived_by, dict(sight.missed_by)) == ((), {ALICE: NotPerceivedReason.ALREADY_PERCEIVED})
        assert voice.perceived_by == (ALICE,)

    def test_words_take_the_place_of_the_sight_in_the_order(self) -> None:
        """見える刺激のあとに世界の知らせ「鐘が鳴った」、そのあとに声が並ぶとき、アリスには声が見える文の位置に入り、知らせより先に届く。"""
        recipient = _Recipient()

        PeopleReachedByStimuli(recipient).deliver_all(
            (_talk_seen(), _call("鐘が鳴った"), _voice()), (awake(ALICE),), _VoiceCarries()
        )

        assert recipient.perceived_texts == [(ALICE, "{actor}が「灯りを点けよう」と言った"), (ALICE, "鐘が鳴った")]

    def test_always_delivered_stimulus_is_kept_beside_the_words(self) -> None:
        """always_delivered の「ボブが倒れた」のあとに声が届いても、倒れた知らせは消えずに残り、声も届く。届けた記録も、両方がアリスに届いたとする。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver_all((_fall_seen(always_delivered=True), _voice()), (awake(ALICE),), _VoiceCarries())

        assert recipient.perceived_texts == [(ALICE, "{actor}が倒れた"), (ALICE, "{actor}が「灯りを点けよう」と言った")]
        fall, voice = reached.report(HappeningFiring(HappeningId("fall")), _AT).stimuli
        assert (fall.perceived_by, voice.perceived_by) == ((ALICE,), (ALICE,))

    def test_sights_without_a_voice_draw_no_more_than_before(self) -> None:
        """声の無いまとまりで、こっそりの見える刺激が 2 つ並ぶと、アリスに 1 つ目が届いたあと 2 つ目は試さず、乱数は 1 回しか引かない (同じ seed の結果が変わらない)。"""
        random = FractionsInOrder((0.0, 0.0))
        recipient = _Recipient()

        PeopleReachedByStimuli(recipient).deliver_all(
            (_talk_seen(stealthily=True), _talk_seen(stealthily=True)), (awake(ALICE),), _VoiceCarries(random)
        )

        assert recipient.perceived_texts == [(ALICE, "{actor}が何か話している")]
        assert random.left() == 1

    def test_muffled_voice_is_passed_over_and_the_clear_voice_takes_the_place_of_the_sight(self) -> None:
        """見える文、くぐもった声、はっきりした声の順に並ぶと、くぐもった声は言葉が無いので見送り、アリスにははっきりした声が見える文の位置に 1 つだけ届く。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver_all((_talk_seen(), _voice(loudness=Loudness.LOUD), _voice()), (awake(ALICE),), _VoiceCarries())

        assert recipient.perceived_texts == [(ALICE, "{actor}が「灯りを点けよう」と言った")]
        muffled = reached.report(HappeningFiring(HappeningId("talk")), _AT).stimuli[1]
        assert dict(muffled.missed_by) == {ALICE: NotPerceivedReason.ALREADY_PERCEIVED}

    def test_voice_not_heard_after_a_sight_is_reported_as_already_perceived(self) -> None:
        """見える文が届いたアリスに、声が届かない (聞こえる範囲の外) ときも、声の記録は「同じものをもう知った」とする。"""
        reached = PeopleReachedByStimuli(_Recipient())

        reached.deliver_all((_talk_seen(), _voice()), (awake(ALICE),), _BrightSenses())

        voice = reached.report(HappeningFiring(HappeningId("talk")), _AT).stimuli[1]
        assert dict(voice.missed_by) == {ALICE: NotPerceivedReason.ALREADY_PERCEIVED}

    def test_fallen_person_keeps_only_what_was_noticed_later(self) -> None:
        """倒れていて関わったアリスは、目撃を起きてから知る形で受けたあと、続く声を受けず、声の記録は「同じものをもう知った」になる。"""
        recipient = _Recipient()
        reached = PeopleReachedByStimuli(recipient)

        reached.deliver_all(
            (_fall_seen(noticed_later="誰かが倒れる音がした"), _voice()), (fallen(ALICE),), _VoiceCarries()
        )

        assert [notice.text.template for _, notice in recipient.notices] == ["誰かが倒れる音がした"]
        assert recipient.perceived_texts == []
        voice = reached.report(HappeningFiring(HappeningId("fall")), _AT).stimuli[1]
        assert dict(voice.missed_by) == {ALICE: NotPerceivedReason.ALREADY_PERCEIVED}

    def test_voice_heard_clearly_takes_the_place_of_the_own_body(self) -> None:
        """同じまとまりでアリスの足の痛みのあとにボブの声が届くと、言葉を伝える声のほうが多くを伝えるので、声が足の痛みの位置に入る。"""
        recipient = _Recipient()

        PeopleReachedByStimuli(recipient).deliver_all(
            (_ache(ALICE, "足が痛む"), _voice()), (awake(ALICE),), _VoiceCarries()
        )

        assert recipient.perceived_texts == [(ALICE, "{actor}が「灯りを点けよう」と言った")]
