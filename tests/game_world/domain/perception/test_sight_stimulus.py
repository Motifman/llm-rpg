from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.action.manner import Openly, Stealthily
from ai_rpg_world.game_world.domain.exception.perception_exception import TargetNotInvolvedException
from ai_rpg_world.game_world.domain.lighting import Lighting, SeesClearly, SeesShapes
from ai_rpg_world.game_world.domain.people import Unidentified
from ai_rpg_world.game_world.domain.perception import (
    Background,
    Notable,
    NoTarget,
    NotNoticedLater,
    NotSeenInDim,
    NotSeenWithoutActor,
)
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.perception_outcome import NoticedLater, NotPerceived, Perceived
from ai_rpg_world.game_world.domain.perception.sight_stimulus import SightStimulus, SightTarget, SightTexts
from ai_rpg_world.game_world.domain.value_object import WorldTick
from tests.game_world.domain.perception._builders import (
    ALICE,
    BOB,
    CAROL,
    HALL,
    SQUARE,
    VIEW,
    about,
    awake,
    departed,
    fallen,
    travelling,
)
from tests.game_world.support.world_in_memory import FractionsInOrder
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_STEALTH = world_rules_for_tests().stealth
_NO_DRAWS = FractionsInOrder(())


def _witness(*, dim: bool = True) -> SightTexts:
    return SightTexts(
        clear=about("{actor}が棚の扉を開けた", actor=ALICE),
        dim=about("{actor}が棚のあたりで何かしている", actor=ALICE) if dim else NotSeenInDim(),
        unseen_actor=NotSeenWithoutActor(),
        noticed_later=NotNoticedLater(),
    )


_TARGET_TEXTS = SightTexts(
    clear=about("{actor}があなたの荷に手を入れた", actor=ALICE),
    dim=about("誰かがあなたの荷に触れた気がする"),
    unseen_actor=NotSeenWithoutActor(),
    noticed_later=about("荷が軽くなっている"),
)


def _opening(
    *,
    dim: bool = True,
    seen_in_dark: bool = False,
    stealthily: bool = False,
    salience=Notable(),
    target=NoTarget(),
    actor_departed: bool = False,
    unseen_actor=None,
    witness_noticed_later=None,
) -> SightStimulus:
    witness = _witness(dim=dim)
    if unseen_actor is not None or witness_noticed_later is not None:
        witness = SightTexts(
            clear=witness.clear,
            dim=witness.dim,
            unseen_actor=unseen_actor if unseen_actor is not None else witness.unseen_actor,
            noticed_later=witness_noticed_later if witness_noticed_later is not None else witness.noticed_later,
        )
    involved = (ALICE,) if isinstance(target, NoTarget) else (ALICE, target.person)
    return SightStimulus(
        where=SQUARE,
        witness=witness,
        target=target,
        seen_in_dark=seen_in_dark,
        manner=Stealthily() if stealthily else Openly(),
        actor_departed=actor_departed,
        involved=involved,
        salience=salience,
        always_delivered=False,
        at=WorldTick(5),
    )


class TestSightStimulusLighting:
    """SightStimulus.perceived_by が、その場所の明るさで、はっきり・形だけ・見えないを決めることを保証する。"""

    @pytest.mark.parametrize("lighting", [Lighting.BRIGHT, Lighting.DUSKY])
    def test_in_light_the_clear_text_is_seen_with_names_from_the_view(self, lighting: Lighting) -> None:
        """明るい・薄暗い場所では、clear の文に view で呼び方を当て、SeesClearly と刺激の時刻を付けて届く。"""
        outcome = _opening().perceived_by(awake(BOB), lighting, VIEW, _NO_DRAWS, _STEALTH)

        assert outcome == Perceived(
            perceiver=BOB,
            text=about("{actor}が棚の扉を開けた", actor=ALICE).seen_by(VIEW),
            quality=SeesClearly(),
            happened_at=WorldTick(5),
            calls_attention=True,
        )

    def test_in_the_dark_the_dim_text_is_seen_with_nobody_identified(self) -> None:
        """暗い場所では、dim の文に Unidentified を当てて SeesShapes で届く。"""
        outcome = _opening().perceived_by(awake(BOB), Lighting.DARK, VIEW, _NO_DRAWS, _STEALTH)

        assert isinstance(outcome, Perceived)
        assert outcome.quality == SeesShapes()
        assert outcome.text.people == {"actor": Unidentified()}
        assert outcome.text.template == "{actor}が棚のあたりで何かしている"

    def test_in_the_dark_without_a_dim_text_nothing_is_seen(self) -> None:
        """暗い場所で dim が NotSeenInDim なら NotPerceived を返す。"""
        outcome = _opening(dim=False).perceived_by(awake(BOB), Lighting.DARK, VIEW, _NO_DRAWS, _STEALTH)

        assert outcome == NotPerceived()

    def test_in_pitch_dark_nothing_is_seen(self) -> None:
        """真っ暗な場所では、seen_in_dark でない刺激は NotPerceived を返す。"""
        outcome = _opening().perceived_by(awake(BOB), Lighting.PITCH_DARK, VIEW, _NO_DRAWS, _STEALTH)

        assert outcome == NotPerceived()

    def test_in_pitch_dark_what_is_seen_in_dark_arrives_as_the_dim_text(self) -> None:
        """真っ暗な場所でも、seen_in_dark の刺激は dim の文で SeesShapes として届く。"""
        outcome = _opening(seen_in_dark=True).perceived_by(awake(BOB), Lighting.PITCH_DARK, VIEW, _NO_DRAWS, _STEALTH)

        assert isinstance(outcome, Perceived)
        assert outcome.quality == SeesShapes()
        assert outcome.text.template == "{actor}が棚のあたりで何かしている"


class TestSightStimulusWhereabouts:
    """SightStimulus.perceived_by が、刺激の場所にいる人にだけ届くことを保証する。"""

    def test_someone_at_another_spot_does_not_see_it(self) -> None:
        """別の場所にいる人には、明るくても NotPerceived を返す。"""
        outcome = _opening().perceived_by(awake(BOB, HALL), Lighting.BRIGHT, VIEW, _NO_DRAWS, _STEALTH)

        assert outcome == NotPerceived()


class TestSightStimulusCallsAttention:
    """SightStimulus.perceived_by の calls_attention が、関わっているか目立つ刺激のときに真になることを保証する。"""

    def test_background_sight_not_involving_the_viewer_does_not_call_attention(self) -> None:
        """Background の刺激を、関わっていない人が見たとき calls_attention は偽。"""
        outcome = _opening(salience=Background()).perceived_by(awake(BOB), Lighting.BRIGHT, VIEW, _NO_DRAWS, _STEALTH)

        assert isinstance(outcome, Perceived)
        assert outcome.calls_attention is False

    def test_background_sight_involving_the_viewer_calls_attention(self) -> None:
        """Background の刺激でも、involved にいる人が見たとき calls_attention は真。"""
        outcome = _opening(salience=Background()).perceived_by(awake(ALICE), Lighting.BRIGHT, VIEW, _NO_DRAWS, _STEALTH)

        assert isinstance(outcome, Perceived)
        assert outcome.calls_attention is True


class TestSightStimulusStealth:
    """SightStimulus.perceived_by が、こっそり行った行為に、見ていた人ごとに StealthRule の確率で気づくかを決めることを保証する。"""

    def test_a_bystander_notices_when_the_draw_is_below_the_chance(self) -> None:
        """明るい場所の見ていた人は、引いた値 0.39 が notice_by_bystander の SeesClearly 0.4 より小さいので気づく。"""
        outcome = _opening(stealthily=True).perceived_by(
            awake(CAROL), Lighting.BRIGHT, VIEW, FractionsInOrder((0.39,)), _STEALTH
        )

        assert isinstance(outcome, Perceived)

    def test_a_bystander_misses_it_when_the_draw_reaches_the_chance(self) -> None:
        """引いた値 0.4 が確率 0.4 に届くと気づかず NotPerceived を返す。"""
        outcome = _opening(stealthily=True).perceived_by(
            awake(CAROL), Lighting.BRIGHT, VIEW, FractionsInOrder((0.4,)), _STEALTH
        )

        assert outcome == NotPerceived()

    def test_the_chance_follows_how_well_the_bystander_sees(self) -> None:
        """暗い場所では notice_by_bystander の SeesShapes 0.15 で決まり、0.2 を引くと気づかない。"""
        outcome = _opening(stealthily=True).perceived_by(
            awake(CAROL), Lighting.DARK, VIEW, FractionsInOrder((0.2,)), _STEALTH
        )

        assert outcome == NotPerceived()

    def test_an_attentive_bystander_gets_the_attentive_bonus(self) -> None:
        """耳を澄ましている人は attentive_bonus 0.2 が足されて 0.6 になり、0.5 を引いても気づく。"""
        outcome = _opening(stealthily=True).perceived_by(
            awake(CAROL, attentive=True), Lighting.BRIGHT, VIEW, FractionsInOrder((0.5,)), _STEALTH
        )

        assert isinstance(outcome, Perceived)

    def test_nothing_is_drawn_for_someone_who_cannot_see_it(self) -> None:
        """真っ暗で見えない人のためには偶然を引かない。値を並べなくても NotPerceived を返す。"""
        outcome = _opening(stealthily=True).perceived_by(awake(CAROL), Lighting.PITCH_DARK, VIEW, _NO_DRAWS, _STEALTH)

        assert outcome == NotPerceived()


class TestSightStimulusTarget:
    """SightStimulus.perceived_by が、関わった相手には target の文と notice_by_target の確率を使うことを保証する。"""

    def test_the_target_sees_the_target_text(self) -> None:
        """相手には witness ではなく target の clear の文が届く。"""
        outcome = _opening(target=SightTarget(person=BOB, texts=_TARGET_TEXTS)).perceived_by(
            awake(BOB), Lighting.BRIGHT, VIEW, _NO_DRAWS, _STEALTH
        )

        assert isinstance(outcome, Perceived)
        assert outcome.text.template == "{actor}があなたの荷に手を入れた"

    def test_a_bystander_still_sees_the_witness_text(self) -> None:
        """相手でない見ていた人には witness の文が届く。"""
        outcome = _opening(target=SightTarget(person=BOB, texts=_TARGET_TEXTS)).perceived_by(
            awake(CAROL), Lighting.BRIGHT, VIEW, _NO_DRAWS, _STEALTH
        )

        assert isinstance(outcome, Perceived)
        assert outcome.text.template == "{actor}が棚の扉を開けた"

    def test_the_target_notices_stealth_with_the_target_chance(self) -> None:
        """こっそり行ったとき、相手は notice_by_target の SeesClearly 0.6 で決まり、0.5 を引くと気づく。"""
        outcome = _opening(stealthily=True, target=SightTarget(person=BOB, texts=_TARGET_TEXTS)).perceived_by(
            awake(BOB), Lighting.BRIGHT, VIEW, FractionsInOrder((0.5,)), _STEALTH
        )

        assert isinstance(outcome, Perceived)

    def test_a_bystander_does_not_get_the_target_chance(self) -> None:
        """同じ刺激でも、見ていた人は notice_by_bystander の 0.4 で決まり、0.5 を引くと気づかない。"""
        outcome = _opening(stealthily=True, target=SightTarget(person=BOB, texts=_TARGET_TEXTS)).perceived_by(
            awake(CAROL), Lighting.BRIGHT, VIEW, FractionsInOrder((0.5,)), _STEALTH
        )

        assert outcome == NotPerceived()


class TestSightStimulusConstruction:
    """SightStimulus を作るときに、相手が関わった人に入っているかを確かめることを保証する。"""

    def test_a_target_missing_from_involved_is_refused(self) -> None:
        """SightTarget.person が involved に無ければ TargetNotInvolvedException を投げる。倒れた相手が後から気づけなくなるのを防ぐ。"""
        with pytest.raises(TargetNotInvolvedException):
            SightStimulus(
                where=SQUARE,
                witness=_witness(),
                target=SightTarget(person=BOB, texts=_TARGET_TEXTS),
                seen_in_dark=False,
                manner=Openly(),
                actor_departed=False,
                involved=(ALICE,),
                salience=Notable(),
                always_delivered=False,
                at=WorldTick(5),
            )


class TestSightStimulusDepartedActor:
    """SightStimulus.perceived_by が、去った人の行為を、生きている人には unseen_actor、去った人には clear で届けることを保証する。"""

    _UNSEEN = about("棚の扉がひとりでに開いた")

    def test_a_living_viewer_sees_the_unseen_actor_text(self) -> None:
        """生きている人には unseen_actor の文が SeesClearly で届く。"""
        outcome = _opening(actor_departed=True, unseen_actor=self._UNSEEN).perceived_by(
            awake(BOB), Lighting.BRIGHT, VIEW, _NO_DRAWS, _STEALTH
        )

        assert isinstance(outcome, Perceived)
        assert outcome.text == self._UNSEEN.seen_by(VIEW)

    def test_a_living_viewer_in_the_dark_sees_the_unseen_actor_text_unidentified(self) -> None:
        """暗い場所の生きている人には、unseen_actor の文に Unidentified を当てて SeesShapes で届く。"""
        unseen = about("{actor}のいないところで扉が動いた", actor=ALICE)
        outcome = _opening(actor_departed=True, unseen_actor=unseen).perceived_by(
            awake(BOB), Lighting.DARK, VIEW, _NO_DRAWS, _STEALTH
        )

        assert outcome == Perceived(
            perceiver=BOB,
            text=unseen.unidentified(),
            quality=SeesShapes(),
            happened_at=WorldTick(5),
            calls_attention=True,
        )

    def test_a_living_viewer_sees_nothing_without_an_unseen_actor_text(self) -> None:
        """unseen_actor が NotSeenWithoutActor なら、生きている人には NotPerceived を返す。"""
        outcome = _opening(actor_departed=True).perceived_by(awake(BOB), Lighting.BRIGHT, VIEW, _NO_DRAWS, _STEALTH)

        assert outcome == NotPerceived()

    def test_a_departed_viewer_sees_the_clear_text(self) -> None:
        """去った人には clear の文が SeesClearly で届く。"""
        outcome = _opening(actor_departed=True, unseen_actor=self._UNSEEN).perceived_by(
            departed(BOB), Lighting.BRIGHT, VIEW, _NO_DRAWS, _STEALTH
        )

        assert isinstance(outcome, Perceived)
        assert outcome.text.template == "{actor}が棚の扉を開けた"


class TestSightStimulusDepartedViewer:
    """SightStimulus.perceived_by が、去った人には明るさとこっそりに関わらず、同じ場所の行為をはっきり見せることを保証する。"""

    def test_a_departed_viewer_sees_clearly_in_pitch_dark(self) -> None:
        """真っ暗でも、去った人には clear の文が SeesClearly で届く。"""
        outcome = _opening().perceived_by(departed(BOB), Lighting.PITCH_DARK, VIEW, _NO_DRAWS, _STEALTH)

        assert isinstance(outcome, Perceived)
        assert outcome.quality == SeesClearly()

    def test_a_departed_viewer_notices_stealth_without_drawing(self) -> None:
        """こっそり行った行為にも、偶然を引かずに気づく。"""
        outcome = _opening(stealthily=True).perceived_by(departed(BOB), Lighting.BRIGHT, VIEW, _NO_DRAWS, _STEALTH)

        assert isinstance(outcome, Perceived)

    def test_a_departed_target_sees_the_target_text(self) -> None:
        """去った人が相手なら、target の clear の文が届く。"""
        outcome = _opening(target=SightTarget(person=BOB, texts=_TARGET_TEXTS)).perceived_by(
            departed(BOB), Lighting.PITCH_DARK, VIEW, _NO_DRAWS, _STEALTH
        )

        assert isinstance(outcome, Perceived)
        assert outcome.text.template == "{actor}があなたの荷に手を入れた"

    def test_a_departed_viewer_elsewhere_does_not_see_it(self) -> None:
        """別の場所にいる去った人には NotPerceived を返す。"""
        outcome = _opening().perceived_by(departed(BOB, HALL), Lighting.BRIGHT, VIEW, _NO_DRAWS, _STEALTH)

        assert outcome == NotPerceived()


class TestSightStimulusFallenViewer:
    """SightStimulus.perceived_by が、倒れている人には自分が関わる行為だけを、明るさとこっそりに関わらず NoticedLater で渡すことを保証する。"""

    def test_a_fallen_target_notices_later_even_in_pitch_dark_and_stealth(self) -> None:
        """倒れている相手には、真っ暗でこっそりでも、偶然を引かずに target の noticed_later を NoticedLater で渡す。"""
        outcome = _opening(stealthily=True, target=SightTarget(person=BOB, texts=_TARGET_TEXTS)).perceived_by(
            fallen(BOB), Lighting.PITCH_DARK, VIEW, _NO_DRAWS, _STEALTH
        )

        assert outcome == NoticedLater(
            notice=MissedNotice(text=about("荷が軽くなっている").seen_by(VIEW), happened_at=WorldTick(5))
        )

    def test_a_fallen_actor_notices_later_with_the_witness_text(self) -> None:
        """倒れている人が相手でなく involved にいるなら、witness の noticed_later を渡す。"""
        later = about("{actor}は棚の扉を開けたはずだ", actor=ALICE)
        outcome = _opening(witness_noticed_later=later).perceived_by(
            fallen(ALICE), Lighting.BRIGHT, VIEW, _NO_DRAWS, _STEALTH
        )

        assert outcome == NoticedLater(notice=MissedNotice(text=later.seen_by(VIEW), happened_at=WorldTick(5)))

    def test_a_fallen_person_without_a_noticed_later_text_perceives_nothing(self) -> None:
        """関わっていても noticed_later が NotNoticedLater なら NotPerceived を返す。"""
        outcome = _opening().perceived_by(fallen(ALICE), Lighting.BRIGHT, VIEW, _NO_DRAWS, _STEALTH)

        assert outcome == NotPerceived()

    def test_a_fallen_person_not_involved_perceives_nothing(self) -> None:
        """関わっていない倒れている人には、明るくても NotPerceived を返す。"""
        outcome = _opening(witness_noticed_later=about("何かあったらしい")).perceived_by(
            fallen(CAROL), Lighting.BRIGHT, VIEW, _NO_DRAWS, _STEALTH
        )

        assert outcome == NotPerceived()

    def test_a_fallen_target_elsewhere_perceives_nothing(self) -> None:
        """別の場所で倒れている相手には NotPerceived を返す。"""
        outcome = _opening(target=SightTarget(person=BOB, texts=_TARGET_TEXTS)).perceived_by(
            fallen(BOB, HALL), Lighting.BRIGHT, VIEW, _NO_DRAWS, _STEALTH
        )

        assert outcome == NotPerceived()


class TestSightStimulusTraveller:
    """SightStimulus.perceived_by が、移動中の人には見える刺激を届けないことを保証する。"""

    def test_someone_travelling_does_not_see_it(self) -> None:
        """移動中の人は、明るくても NotPerceived を返す。"""
        outcome = _opening().perceived_by(travelling(BOB), Lighting.BRIGHT, VIEW, _NO_DRAWS, _STEALTH)

        assert outcome == NotPerceived()
