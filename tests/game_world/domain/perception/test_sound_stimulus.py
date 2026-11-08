from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.perception import Notable, NotNoticedLater
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.perception_outcome import NoticedLater, NotPerceived, Perceived
from ai_rpg_world.game_world.domain.perception.sound_stimulus import Noise, NotWhispered, SoundStimulus, Voice
from ai_rpg_world.game_world.domain.sound import (
    HearingValues,
    HearsClearly,
    HearsFaintly,
    HearsMuffled,
    Loudness,
    SoundLevel,
    SoundLoss,
    SoundReach,
)
from ai_rpg_world.game_world.domain.value_object import WorldTick
from tests.game_world.domain.perception._builders import (
    ALICE,
    BOB,
    CAROL,
    CELLAR,
    HALL,
    SQUARE,
    VIEW,
    about,
    awake,
    departed,
    fallen,
    setting_out,
    travelling,
)
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_VALUES = world_rules_for_tests().hearing
_CLEAR = about("{speaker}が「集まれ」と言った", speaker=ALICE)
_MUFFLED = about("{speaker}の声が何か言っている", speaker=ALICE)


def _speech(
    loudness: Loudness = Loudness.NORMAL,
    *,
    origin=SQUARE,
    source=None,
    noticed_later=NotNoticedLater(),
    involved=(ALICE,),
) -> SoundStimulus:
    return SoundStimulus(
        origin=origin,
        loudness=loudness,
        clear=_CLEAR,
        muffled=_MUFFLED,
        noticed_later=noticed_later,
        source=source if source is not None else Voice(whispered_to=NotWhispered()),
        involved=involved,
        salience=Notable(),
        at=WorldTick(9),
    )


def _reach(level: int) -> SoundReach:
    return SoundReach(levels={SQUARE: SoundLevel(60), HALL: SoundLevel(level)})


class TestSoundStimulusHearingQuality:
    """SoundStimulus.perceived_by が、聞く人の場所に届いた大きさと HearingValues の境目で聞こえ方を決めることを保証する。"""

    def test_a_loud_enough_voice_is_heard_clearly_with_the_speaker_named(self) -> None:
        """届いた大きさが clear_from 以上なら、clear の文に view で呼び方を当てて HearsClearly で届く。"""
        outcome = _speech().perceived_by(awake(BOB, HALL), _reach(50), _VALUES, VIEW)

        assert outcome == Perceived(
            perceiver=BOB,
            text=_CLEAR.seen_by(VIEW),
            quality=HearsClearly(),
            happened_at=WorldTick(9),
            calls_attention=True,
        )

    def test_a_muffled_voice_arrives_with_nobody_identified(self) -> None:
        """muffled_from 以上 clear_from 未満なら、muffled の文に Unidentified を当てて HearsMuffled で届く。"""
        outcome = _speech().perceived_by(awake(BOB, HALL), _reach(40), _VALUES, VIEW)

        assert outcome == Perceived(
            perceiver=BOB,
            text=_MUFFLED.unidentified(),
            quality=HearsMuffled(),
            happened_at=WorldTick(9),
            calls_attention=True,
        )

    def test_a_sound_below_faint_is_not_heard(self) -> None:
        """faint_from 未満なら NotPerceived を返す。"""
        outcome = _speech().perceived_by(awake(BOB, HALL), _reach(19), _VALUES, VIEW)

        assert outcome == NotPerceived()

    def test_a_sound_that_does_not_reach_the_spot_is_not_heard(self) -> None:
        """聞く人の場所に届いていなければ NotPerceived を返す。"""
        outcome = _speech().perceived_by(awake(BOB, HALL), SoundReach(levels={SQUARE: SoundLevel(60)}), _VALUES, VIEW)

        assert outcome == NotPerceived()

    def test_listening_closely_lowers_the_boundaries(self) -> None:
        """耳を澄ましている人は境目が attentive_allowance 15 だけ下がり、40 の声もはっきり聞こえる。"""
        outcome = _speech().perceived_by(awake(BOB, HALL, attentive=True), _reach(40), _VALUES, VIEW)

        assert isinstance(outcome, Perceived)
        assert outcome.quality == HearsClearly()

    def test_a_faint_sound_arrives_as_the_muffled_text_with_nobody_identified(self) -> None:
        """faint_from 以上 muffled_from 未満なら、muffled の文に Unidentified を当てて HearsFaintly で届き、calls_attention は偽。"""
        outcome = _speech().perceived_by(awake(BOB, HALL), _reach(25), _VALUES, VIEW)

        assert outcome == Perceived(
            perceiver=BOB,
            text=_MUFFLED.unidentified(),
            quality=HearsFaintly(),
            happened_at=WorldTick(9),
            calls_attention=False,
        )


class TestSoundStimulusNoise:
    """SoundStimulus.perceived_by が、物音の人をはっきり聞こえても見分けないことを保証する。"""

    def test_a_noise_heard_clearly_leaves_the_person_unidentified(self) -> None:
        """Noise の刺激は、HearsClearly でも clear の文に Unidentified を当てて届く。"""
        outcome = _speech(source=Noise()).perceived_by(awake(BOB, HALL), _reach(55), _VALUES, VIEW)

        assert outcome == Perceived(
            perceiver=BOB,
            text=_CLEAR.unidentified(),
            quality=HearsClearly(),
            happened_at=WorldTick(9),
            calls_attention=True,
        )


class TestSoundStimulusWhisper:
    """SoundStimulus.perceived_by が、ささやきを宛先にははっきり、同じ場所のほかの人にはかすかに届けることを保証する。"""

    def _whisper(self) -> SoundStimulus:
        return _speech(Loudness.WHISPER, source=Voice(whispered_to=BOB), involved=(ALICE, BOB))

    def _reach(self) -> SoundReach:
        return SoundReach(levels={SQUARE: SoundLevel(30), HALL: SoundLevel(15)})

    def test_the_addressee_hears_it_clearly(self) -> None:
        """宛先の人には、clear の文に view で呼び方を当てて HearsClearly で届く。"""
        outcome = self._whisper().perceived_by(awake(BOB), self._reach(), _VALUES, VIEW)

        assert outcome == Perceived(
            perceiver=BOB,
            text=_CLEAR.seen_by(VIEW),
            quality=HearsClearly(),
            happened_at=WorldTick(9),
            calls_attention=True,
        )

    def test_someone_else_at_the_spot_hears_it_faintly(self) -> None:
        """同じ場所のほかの人には、耳を澄ましていても muffled の文に Unidentified を当てて HearsFaintly で届く。"""
        outcome = self._whisper().perceived_by(awake(CAROL, attentive=True), self._reach(), _VALUES, VIEW)

        assert isinstance(outcome, Perceived)
        assert outcome.quality == HearsFaintly()
        assert outcome.text == _MUFFLED.unidentified()

    def test_a_departed_listener_at_the_spot_hears_it_faintly_too(self) -> None:
        """宛先でない去った人も、同じ場所にいれば muffled の文に Unidentified を当てて HearsFaintly で聞く。宛先だけに伝える行為を守る。"""
        outcome = self._whisper().perceived_by(departed(CAROL), self._reach(), _VALUES, VIEW)

        assert isinstance(outcome, Perceived)
        assert outcome.quality == HearsFaintly()
        assert outcome.text == _MUFFLED.unidentified()

    def test_someone_at_another_spot_does_not_hear_it(self) -> None:
        """別の場所の人には、音が届いていても NotPerceived を返す。"""
        outcome = self._whisper().perceived_by(awake(CAROL, HALL, attentive=True), self._reach(), _VALUES, VIEW)

        assert outcome == NotPerceived()

    def test_an_addressee_at_another_spot_does_not_hear_it(self) -> None:
        """宛先でも、鳴った場所にいなければ NotPerceived を返す。"""
        outcome = self._whisper().perceived_by(awake(BOB, HALL, attentive=True), self._reach(), _VALUES, VIEW)

        assert outcome == NotPerceived()


class TestSoundStimulusTraveller:
    """SoundStimulus.perceived_by が、移動中の人には今の区間の両端で鳴った大きい音だけを、隣の場所の音として届けることを保証する。"""

    _EMPTY_REACH = SoundReach(levels={})

    @pytest.mark.parametrize(
        ("loudness", "quality"), [(Loudness.LOUD, HearsClearly()), (Loudness.VERY_LOUD, HearsClearly())]
    )
    def test_a_loud_sound_at_an_end_of_the_passage_is_heard(self, loudness: Loudness, quality) -> None:
        """区間の端 (広間) で鳴った大きい音は、loss_per_passage 15 だけ弱めた大きさ (75→60、90→75) で聞こえ方が決まる。"""
        outcome = _speech(loudness, origin=HALL).perceived_by(travelling(BOB), self._EMPTY_REACH, _VALUES, VIEW)

        assert isinstance(outcome, Perceived)
        assert outcome.quality == quality

    def test_a_loud_sound_at_the_far_end_is_heard_too(self) -> None:
        """区間のもう一方の端 (地下室) で鳴った大きい音も聞こえる。"""
        outcome = _speech(Loudness.LOUD, origin=CELLAR).perceived_by(travelling(BOB), self._EMPTY_REACH, _VALUES, VIEW)

        assert isinstance(outcome, Perceived)

    @pytest.mark.parametrize("loudness", [Loudness.WHISPER, Loudness.NORMAL])
    def test_a_quieter_sound_at_an_end_is_not_heard(self, loudness: Loudness) -> None:
        """区間の端で鳴っても、ささやき・ふつうの音は NotPerceived を返す。"""
        outcome = _speech(loudness, origin=HALL).perceived_by(travelling(BOB), self._EMPTY_REACH, _VALUES, VIEW)

        assert outcome == NotPerceived()

    @pytest.mark.parametrize("origin", [SQUARE, HALL])
    def test_both_ends_of_the_first_passage_count(self, origin) -> None:
        """最初の区間 (広場→広間) を歩いているときは、出発した広場と行き先の広間の両方で鳴った大きい音が聞こえる。"""
        outcome = _speech(Loudness.LOUD, origin=origin).perceived_by(setting_out(BOB), self._EMPTY_REACH, _VALUES, VIEW)

        assert isinstance(outcome, Perceived)

    def test_a_loud_sound_beyond_the_first_passage_is_not_heard(self) -> None:
        """最初の区間を歩いているとき、その先の地下室で鳴った大きい音は NotPerceived を返す。"""
        outcome = _speech(Loudness.VERY_LOUD, origin=CELLAR).perceived_by(
            setting_out(BOB), self._EMPTY_REACH, _VALUES, VIEW
        )

        assert outcome == NotPerceived()

    def test_a_loud_sound_away_from_the_passage_is_not_heard(self) -> None:
        """今の区間の端でない場所 (通り過ぎた広場) で鳴った大きい音は NotPerceived を返す。"""
        outcome = _speech(Loudness.VERY_LOUD, origin=SQUARE).perceived_by(
            travelling(BOB), self._EMPTY_REACH, _VALUES, VIEW
        )

        assert outcome == NotPerceived()

    def test_listening_closely_while_travelling_lowers_the_boundaries(self) -> None:
        """loss_per_passage を 40 にした世界では大きい音が 35 になり、ふだんはくぐもるが、耳を澄ますとはっきり聞こえる。"""
        values = HearingValues(
            loudness=_VALUES.loudness,
            loss_per_passage=SoundLoss(40),
            clear_from=_VALUES.clear_from,
            muffled_from=_VALUES.muffled_from,
            faint_from=_VALUES.faint_from,
            attentive_allowance=_VALUES.attentive_allowance,
        )
        stimulus = _speech(Loudness.LOUD, origin=HALL)

        assert stimulus.perceived_by(travelling(BOB), self._EMPTY_REACH, values, VIEW).quality == HearsMuffled()
        assert (
            stimulus.perceived_by(travelling(BOB, attentive=True), self._EMPTY_REACH, values, VIEW).quality
            == HearsClearly()
        )


class TestSoundStimulusDepartedListener:
    """SoundStimulus.perceived_by が、去った人には届いた音をはっきり聞かせることを保証する。"""

    def test_a_departed_listener_hears_a_faint_voice_clearly(self) -> None:
        """生きている人にはかすかな大きさでも、去った人には clear の文に view で呼び方を当てて HearsClearly で届く。"""
        outcome = _speech().perceived_by(departed(BOB, HALL), _reach(25), _VALUES, VIEW)

        assert outcome == Perceived(
            perceiver=BOB,
            text=_CLEAR.seen_by(VIEW),
            quality=HearsClearly(),
            happened_at=WorldTick(9),
            calls_attention=True,
        )

    def test_a_departed_listener_hears_a_noise_without_identifying_anyone(self) -> None:
        """物音は、去った人にも Unidentified のまま届く。"""
        outcome = _speech(source=Noise()).perceived_by(departed(BOB, HALL), _reach(25), _VALUES, VIEW)

        assert isinstance(outcome, Perceived)
        assert outcome.text == _CLEAR.unidentified()

    def test_a_departed_listener_does_not_hear_what_does_not_reach_them(self) -> None:
        """去った人の場所に届いていなければ NotPerceived を返す。"""
        outcome = _speech().perceived_by(
            departed(BOB, HALL), SoundReach(levels={SQUARE: SoundLevel(60)}), _VALUES, VIEW
        )

        assert outcome == NotPerceived()


class TestSoundStimulusFallenListener:
    """SoundStimulus.perceived_by が、倒れている人には届いた音のうち自分が関わるものだけを NoticedLater で渡すことを保証する。"""

    _LATER = about("{speaker}が呼んでいたらしい", speaker=ALICE)

    def test_a_fallen_person_involved_notices_later(self) -> None:
        """関わっている倒れた人には、届いた音の noticed_later を view で呼び方を当てて NoticedLater で渡す。"""
        outcome = _speech(noticed_later=self._LATER, involved=(ALICE, BOB)).perceived_by(
            fallen(BOB, HALL), _reach(25), _VALUES, VIEW
        )

        assert outcome == NoticedLater(notice=MissedNotice(text=self._LATER.seen_by(VIEW), happened_at=WorldTick(9)))

    def test_a_fallen_person_involved_misses_what_does_not_reach_them(self) -> None:
        """関わっていても、届かない音は NotPerceived を返す。"""
        outcome = _speech(noticed_later=self._LATER, involved=(ALICE, BOB)).perceived_by(
            fallen(BOB, HALL), _reach(10), _VALUES, VIEW
        )

        assert outcome == NotPerceived()

    def test_a_fallen_person_not_involved_perceives_nothing(self) -> None:
        """関わっていない倒れた人には NotPerceived を返す。"""
        outcome = _speech(noticed_later=self._LATER).perceived_by(fallen(BOB, HALL), _reach(55), _VALUES, VIEW)

        assert outcome == NotPerceived()

    def test_a_fallen_person_involved_without_a_noticed_later_text_perceives_nothing(self) -> None:
        """関わっていて届いても、noticed_later が NotNoticedLater なら NotPerceived を返す。"""
        outcome = _speech(involved=(ALICE, BOB)).perceived_by(fallen(BOB, HALL), _reach(55), _VALUES, VIEW)

        assert outcome == NotPerceived()

    def test_a_fallen_addressee_of_a_whisper_notices_later(self) -> None:
        """ささやきの宛先が同じ場所で倒れていれば、noticed_later を NoticedLater で渡す。"""
        whisper = _speech(
            Loudness.WHISPER, source=Voice(whispered_to=BOB), noticed_later=self._LATER, involved=(ALICE, BOB)
        )

        outcome = whisper.perceived_by(fallen(BOB), SoundReach(levels={SQUARE: SoundLevel(30)}), _VALUES, VIEW)

        assert outcome == NoticedLater(notice=MissedNotice(text=self._LATER.seen_by(VIEW), happened_at=WorldTick(9)))
