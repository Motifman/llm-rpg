from __future__ import annotations

from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.perception import (
    AnnouncementStimulus,
    Background,
    BodilyStimulus,
    Notable,
    NoTarget,
    NotNoticedLater,
    NotSeenWithoutActor,
    Salience,
    SightStimulus,
    SightTexts,
    SoundStimulus,
    Stimulus,
    Voice,
)
from ai_rpg_world.game_world.domain.perception.sound_stimulus import NotWhispered
from ai_rpg_world.game_world.domain.sound import Loudness
from ai_rpg_world.game_world.domain.value_object import WorldTick
from tests.game_world.domain.perception._builders import ALICE, SQUARE, about

_AT = WorldTick(2)


def _bodily(salience: Salience = Notable()) -> BodilyStimulus:
    return BodilyStimulus(person=ALICE, text=about("足が痛む"), salience=salience, at=_AT)


def _sight(salience: Salience = Notable(), *, always_delivered: bool = False) -> SightStimulus:
    texts = SightTexts(
        clear=about("扉が開いた"),
        dim=about("何かが動いた"),
        unseen_actor=NotSeenWithoutActor(),
        noticed_later=NotNoticedLater(),
    )
    return SightStimulus(
        where=SQUARE,
        witness=texts,
        target=NoTarget(),
        seen_in_dark=False,
        manner=Openly(),
        actor_departed=False,
        involved=(ALICE,),
        salience=salience,
        always_delivered=always_delivered,
        at=_AT,
    )


def _sound(salience: Salience = Notable()) -> SoundStimulus:
    return SoundStimulus(
        origin=SQUARE,
        loudness=Loudness.LOUD,
        clear=about("扉の軋む音がした"),
        muffled=about("何かの音がした"),
        noticed_later=NotNoticedLater(),
        source=Voice(whispered_to=NotWhispered()),
        involved=(ALICE,),
        salience=salience,
        at=_AT,
    )


def _announcement(salience: Salience = Notable()) -> AnnouncementStimulus:
    return AnnouncementStimulus(audience=frozenset({ALICE}), text=about("夜が明けた"), salience=salience, at=_AT)


def _in_delivery_order(*stimuli: Stimulus) -> list[Stimulus]:
    return sorted(stimuli, key=lambda stimulus: stimulus.delivery_rank())


class TestDeliveryRank:
    """刺激の delivery_rank が、本人の体 → 見える → 聞こえる → 世界の知らせ、同じ種類なら目立つものを先にする順を決めることを保証する。"""

    def test_senses_are_ordered_body_sight_sound_announcement(self) -> None:
        """知らせ・音・見える・体の順に並べても、体 → 見える → 聞こえる → 知らせの順になる。"""
        stimuli = (_announcement(), _sound(), _sight(), _bodily())

        assert _in_delivery_order(*stimuli) == [stimuli[3], stimuli[2], stimuli[1], stimuli[0]]

    def test_notable_comes_before_background_of_the_same_sense(self) -> None:
        """同じ見える刺激なら、目立つ刺激が目立たない刺激より先になる。"""
        quiet, loud = _sight(Background()), _sight(Notable())

        assert _in_delivery_order(quiet, loud) == [loud, quiet]

    def test_sense_outranks_salience(self) -> None:
        """目立たない本人の体の刺激でも、目立つ見える刺激より先になる。"""
        quiet_body, loud_sight = _bodily(Background()), _sight(Notable())

        assert _in_delivery_order(loud_sight, quiet_body) == [quiet_body, loud_sight]


class TestAlwaysDelivered:
    """ほかの刺激と重なっても届ける印 (always_delivered) を、見える刺激だけが宣言どおりに持つことを保証する。"""

    def test_only_a_sight_declared_so_is_always_delivered(self) -> None:
        """always_delivered を真にした見える刺激だけが真で、ほかの見える刺激と、体・音・知らせの刺激は偽になる。"""
        assert _sight(always_delivered=True).always_delivered
        assert not any(stimulus.always_delivered for stimulus in (_sight(), _bodily(), _sound(), _announcement()))
