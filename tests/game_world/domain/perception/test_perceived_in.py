from __future__ import annotations

from collections.abc import Mapping

from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.condition.random_source import RandomSource
from ai_rpg_world.game_world.domain.lighting import Lighting, SeesClearly, SeesShapes
from ai_rpg_world.game_world.domain.people import PersonRef
from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
from ai_rpg_world.game_world.domain.perception import (
    AnnouncementStimulus,
    BodilyStimulus,
    Notable,
    NoTarget,
    NotNoticedLater,
    NotPerceived,
    NotSeenWithoutActor,
    Perceived,
    SightStimulus,
    SightTexts,
    SoundStimulus,
    Voice,
)
from ai_rpg_world.game_world.domain.perception.not_perceived_reason import NotPerceivedReason
from ai_rpg_world.game_world.domain.perception.perceived_quality import Felt, Told
from ai_rpg_world.game_world.domain.perception.sound_stimulus import NotWhispered
from ai_rpg_world.game_world.domain.rules.stealth_rule import StealthRule
from ai_rpg_world.game_world.domain.sound import HearingValues, HearsClearly, Loudness, SoundLevel, SoundReach
from ai_rpg_world.game_world.domain.value_object import DisplayName, PersonId, SpotId, WorldTick
from tests.game_world.domain.perception._builders import (
    ALICE,
    BOB,
    HALL,
    SQUARE,
    VIEW,
    PeopleByHandle,
    about,
    awake,
    ref,
)
from tests.game_world.support.world_in_memory import FractionsInOrder
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_RULES = world_rules_for_tests()
_AT = WorldTick(4)


class _Senses:
    def __init__(
        self,
        *,
        lighting: Mapping[SpotId, Lighting] | None = None,
        reach: Mapping[tuple[SpotId, Loudness], SoundReach] | None = None,
        views: Mapping[PersonId, PeopleAsSeen] | None = None,
    ) -> None:
        self._lighting = dict(lighting or {})
        self._reach = dict(reach or {})
        self._views = dict(views or {})

    def lighting_at(self, spot: SpotId) -> Lighting:
        return self._lighting[spot]

    def reach_of(self, origin: SpotId, loudness: Loudness) -> SoundReach:
        return self._reach.get((origin, loudness), SoundReach(levels={}))

    def view_for(self, viewer: PersonId) -> PeopleAsSeen:
        return self._views.get(viewer, VIEW)

    def random(self) -> RandomSource:
        return FractionsInOrder(())

    def stealth(self) -> StealthRule:
        return _RULES.stealth

    def hearing(self) -> HearingValues:
        return _RULES.hearing


def _named(handle: int, name: str) -> PersonRef:
    plain = ref(handle)
    return PersonRef(handle=plain.handle, appearance=plain.appearance, visible_name=DisplayName(name))


_ALICE_KNOWS_BOB = PeopleByHandle({ALICE: _named(1, "アリス"), BOB: _named(2, "ボブ")})


class TestSightStimulusPerceivedIn:
    """SightStimulus.perceived_in が、刺激の起きた場所の明るさを感覚に聞いて見え方を決めることを保証する。"""

    def _opening(self) -> SightStimulus:
        return SightStimulus(
            where=SQUARE,
            witness=SightTexts(
                clear=about("{actor}が棚を開けた", actor=BOB),
                dim=about("{actor}が棚のあたりで何かしている", actor=BOB),
                unseen_actor=NotSeenWithoutActor(),
                noticed_later=NotNoticedLater(),
            ),
            target=NoTarget(),
            seen_in_dark=False,
            manner=Openly(),
            actor_departed=False,
            involved=(BOB,),
            salience=Notable(),
            always_delivered=False,
            at=_AT,
        )

    def test_dark_spot_of_the_stimulus_gives_the_dim_text(self) -> None:
        """刺激の場所 (広場) が暗く、ほかの場所 (広間) が明るいとき、広場にいる人には dim の文が SeesShapes で届く。"""
        senses = _Senses(lighting={SQUARE: Lighting.DARK, HALL: Lighting.BRIGHT})

        outcome = self._opening().perceived_in(awake(ALICE, SQUARE), senses)

        assert outcome == Perceived(
            perceiver=ALICE,
            text=about("{actor}が棚のあたりで何かしている", actor=BOB).unidentified(),
            quality=SeesShapes(),
            happened_at=_AT,
            calls_attention=True,
            addressed_to_perceiver=False,
        )

    def test_bright_spot_gives_the_clear_text_seen_by_the_perceiver(self) -> None:
        """刺激の場所が明るいとき、見る人の呼び方を当てた clear の文が SeesClearly で届く。"""
        senses = _Senses(lighting={SQUARE: Lighting.BRIGHT}, views={ALICE: _ALICE_KNOWS_BOB})

        outcome = self._opening().perceived_in(awake(ALICE, SQUARE), senses)

        assert outcome == Perceived(
            perceiver=ALICE,
            text=about("{actor}が棚を開けた", actor=BOB).seen_by(_ALICE_KNOWS_BOB),
            quality=SeesClearly(),
            happened_at=_AT,
            calls_attention=True,
            addressed_to_perceiver=False,
        )


class TestSoundStimulusPerceivedIn:
    """SoundStimulus.perceived_in が、鳴った場所と音の大きさで感覚に音の届き方を聞くことを保証する。"""

    def _shout(self) -> SoundStimulus:
        return SoundStimulus(
            origin=SQUARE,
            loudness=Loudness.LOUD,
            clear=about("{speaker}が「来い」と叫んだ", speaker=BOB),
            muffled=about("{speaker}の声が聞こえる", speaker=BOB),
            noticed_later=NotNoticedLater(),
            source=Voice(whispered_to=NotWhispered()),
            involved=(BOB,),
            salience=Notable(),
            at=_AT,
        )

    def test_reach_of_the_origin_and_loudness_decides_hearing(self) -> None:
        """広場で鳴った大きい音が広間に 60 で届くとき、広間の人には、その人の呼び方で clear の文が届く。"""
        senses = _Senses(
            reach={(SQUARE, Loudness.LOUD): SoundReach(levels={SQUARE: SoundLevel(75), HALL: SoundLevel(60)})},
            views={ALICE: _ALICE_KNOWS_BOB},
        )

        outcome = self._shout().perceived_in(awake(ALICE, HALL), senses)

        assert outcome == Perceived(
            perceiver=ALICE,
            text=about("{speaker}が「来い」と叫んだ", speaker=BOB).seen_by(_ALICE_KNOWS_BOB),
            quality=HearsClearly(),
            happened_at=_AT,
            calls_attention=True,
            addressed_to_perceiver=False,
        )

    def test_reach_of_another_loudness_is_not_used(self) -> None:
        """広場のささやきだけが広間に届くとき、広場の大きい音は広間の人に届かず NotPerceived になる。"""
        senses = _Senses(reach={(SQUARE, Loudness.WHISPER): SoundReach(levels={HALL: SoundLevel(60)})})

        outcome = self._shout().perceived_in(awake(ALICE, HALL), senses)

        assert outcome == NotPerceived(NotPerceivedReason.OUT_OF_EARSHOT)


class TestBodilyAndAnnouncementPerceivedIn:
    """本人の体の刺激と世界の知らせの perceived_in が、知覚する本人から見た呼び方を感覚に聞くことを保証する。"""

    def test_bodily_text_is_seen_by_the_person_who_feels_it(self) -> None:
        """本人の体の刺激の文は、感じた本人の呼び方で当てて Felt で届く。"""
        text = about("{striker}に殴られた", striker=BOB)
        stimulus = BodilyStimulus(person=ALICE, text=text, salience=Notable(), at=_AT)

        outcome = stimulus.perceived_in(awake(ALICE), _Senses(views={ALICE: _ALICE_KNOWS_BOB}))

        assert outcome == Perceived(
            perceiver=ALICE,
            text=text.seen_by(_ALICE_KNOWS_BOB),
            quality=Felt(),
            happened_at=_AT,
            calls_attention=True,
            addressed_to_perceiver=False,
        )

    def test_announcement_text_is_seen_by_the_person_told(self) -> None:
        """世界の知らせの文は、知らされた本人の呼び方で当てて Told で届く。"""
        text = about("{caller}が皆を呼んでいる", caller=BOB)
        stimulus = AnnouncementStimulus(audience=frozenset({ALICE}), text=text, salience=Notable(), at=_AT)

        outcome = stimulus.perceived_in(awake(ALICE), _Senses(views={ALICE: _ALICE_KNOWS_BOB}))

        assert outcome == Perceived(
            perceiver=ALICE,
            text=text.seen_by(_ALICE_KNOWS_BOB),
            quality=Told(),
            happened_at=_AT,
            calls_attention=True,
            addressed_to_perceiver=False,
        )
