from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.sound_exception import (
    HearingBoundariesOutOfOrderException,
    MissingLoudnessLevelException,
)
from ai_rpg_world.game_world.domain.sound import (
    HearingValues,
    HearsClearly,
    HearsFaintly,
    HearsMuffled,
    HearsNothing,
    Loudness,
    NotReached,
    SoundLevel,
    SoundLink,
    SoundLoss,
    SoundNetwork,
)
from ai_rpg_world.game_world.domain.value_object import SpotId


def _default_values() -> HearingValues:
    return HearingValues(
        loudness={
            Loudness.WHISPER: SoundLevel(30),
            Loudness.NORMAL: SoundLevel(60),
            Loudness.LOUD: SoundLevel(75),
            Loudness.VERY_LOUD: SoundLevel(90),
        },
        loss_per_passage=SoundLoss(15),
        clear_from=SoundLevel(50),
        muffled_from=SoundLevel(35),
        faint_from=SoundLevel(20),
        attentive_allowance=SoundLoss(15),
    )


class TestHearingValuesLevelOf:
    """HearingValues.level_of が、作る側が渡した表のとおりに音の大きさの段階を大きさに変えることを保証する。"""

    @pytest.mark.parametrize(
        ("loudness", "level"),
        [
            (Loudness.WHISPER, 30),
            (Loudness.NORMAL, 60),
            (Loudness.LOUD, 75),
            (Loudness.VERY_LOUD, 90),
        ],
    )
    def test_level_of_returns_the_level_given_for_the_loudness(self, loudness: Loudness, level: int) -> None:
        """既定の表 (ささやき 30、ふつう 60、大きい 75、とても大きい 90) のとおりの大きさを返す。"""
        assert _default_values().level_of(loudness) == SoundLevel(level)


class TestHearingValuesQuality:
    """HearingValues.quality が、はっきり・くぐもる・かすか・聞こえないの境目どおりに聞こえ方を答えることを保証する。"""

    @pytest.mark.parametrize(
        ("level", "expected"),
        [
            (50, HearsClearly()),
            (49, HearsMuffled()),
            (35, HearsMuffled()),
            (34, HearsFaintly()),
            (20, HearsFaintly()),
            (19, HearsNothing()),
        ],
    )
    def test_quality_follows_the_boundaries_when_not_attentive(self, level: int, expected: object) -> None:
        """耳を澄ましていない人は、50 以上ではっきり、35 以上でくぐもる、20 以上でかすか、それ未満は聞こえない。"""
        assert _default_values().quality(SoundLevel(level), attentive=False) == expected

    def test_not_reached_is_heard_as_nothing(self) -> None:
        """音が届かなかった場所 (NotReached) では、耳を澄ましていても聞こえない。"""
        values = _default_values()

        assert values.quality(NotReached(), attentive=False) == HearsNothing()
        assert values.quality(NotReached(), attentive=True) == HearsNothing()

    @pytest.mark.parametrize(
        ("level", "expected"),
        [
            (35, HearsClearly()),
            (34, HearsMuffled()),
            (20, HearsMuffled()),
            (19, HearsFaintly()),
            (5, HearsFaintly()),
            (4, HearsNothing()),
        ],
    )
    def test_attentive_listener_has_every_boundary_lowered_by_the_allowance(self, level: int, expected: object) -> None:
        """耳を澄ました人は、3 つの境目がすべて 15 下がり、35 以上ではっきり、20 以上でくぐもる、5 以上でかすかに聞こえる。"""
        assert _default_values().quality(SoundLevel(level), attentive=True) == expected


class TestHearingValuesQuietestAudible:
    """HearingValues.quietest_audible が、耳を澄ました人まで含めて聞こえうる最も小さい大きさを返すことを保証する。"""

    def test_quietest_audible_is_faint_boundary_minus_the_attentive_allowance(self) -> None:
        """かすかの境目 20 から耳を澄ました分 15 を引いた 5 を返す。spread で耳を澄ました人に届く音を切らないため。"""
        assert _default_values().quietest_audible() == SoundLevel(5)

    def test_quietest_audible_stops_at_zero(self) -> None:
        """耳を澄ました分がかすかの境目より大きいとき、負にならず 0 を返す。"""
        values = HearingValues(
            loudness=_default_values().loudness,
            loss_per_passage=SoundLoss(15),
            clear_from=SoundLevel(50),
            muffled_from=SoundLevel(35),
            faint_from=SoundLevel(10),
            attentive_allowance=SoundLoss(15),
        )

        assert values.quietest_audible() == SoundLevel(0)

    def test_spreading_down_to_quietest_audible_lets_an_attentive_listener_hear_faintly(self) -> None:
        """quietest_audible を spread の下限に渡すと、3 本先のふつうの音 (60 − 15 × 3 = 15) も届き、耳を澄ました人にはかすかに聞こえる。"""
        values = _default_values()
        hall, corridor, cellar, tower = SpotId("hall"), SpotId("corridor"), SpotId("cellar"), SpotId("tower")
        network = SoundNetwork(
            links=tuple(
                SoundLink(ends=ends, loss=values.loss_per_passage)
                for ends in ((hall, corridor), (corridor, cellar), (cellar, tower))
            )
        )

        reach = network.spread(hall, values.level_of(Loudness.NORMAL), values.quietest_audible())

        assert values.quality(reach.level_at(tower), attentive=True) == HearsFaintly()
        assert values.quality(reach.level_at(tower), attentive=False) == HearsNothing()


class TestHearingValuesConsistency:
    """設定が食い違った HearingValues は作れないことを保証する。"""

    def test_missing_loudness_raises_domain_exception(self) -> None:
        """音の大きさの表に 4 段階のどれかが欠けていると MissingLoudnessLevelException を投げる。"""
        loudness = dict(_default_values().loudness)
        del loudness[Loudness.VERY_LOUD]

        with pytest.raises(MissingLoudnessLevelException):
            HearingValues(
                loudness=loudness,
                loss_per_passage=SoundLoss(15),
                clear_from=SoundLevel(50),
                muffled_from=SoundLevel(35),
                faint_from=SoundLevel(20),
                attentive_allowance=SoundLoss(15),
            )

    @pytest.mark.parametrize(
        ("clear", "muffled", "faint"),
        [(35, 50, 20), (50, 20, 35)],
    )
    def test_boundaries_out_of_order_raise_domain_exception(self, clear: int, muffled: int, faint: int) -> None:
        """境目が「はっきり ≥ くぐもる ≥ かすか」の順に並んでいないと HearingBoundariesOutOfOrderException を投げる。"""
        with pytest.raises(HearingBoundariesOutOfOrderException):
            HearingValues(
                loudness=_default_values().loudness,
                loss_per_passage=SoundLoss(15),
                clear_from=SoundLevel(clear),
                muffled_from=SoundLevel(muffled),
                faint_from=SoundLevel(faint),
                attentive_allowance=SoundLoss(15),
            )

    def test_equal_boundaries_are_accepted(self) -> None:
        """隣り合う境目が等しい設定 (くぐもる段階の無い世界) は作れる。その大きさでははっきり聞こえる。"""
        values = HearingValues(
            loudness=_default_values().loudness,
            loss_per_passage=SoundLoss(15),
            clear_from=SoundLevel(35),
            muffled_from=SoundLevel(35),
            faint_from=SoundLevel(20),
            attentive_allowance=SoundLoss(15),
        )

        assert values.quality(SoundLevel(35), attentive=False) == HearsClearly()

    def test_changing_the_given_mapping_afterwards_does_not_change_the_levels(self) -> None:
        """作るときに渡した大きさの表をあとで書き換えても、level_of の答えは変わらない。"""
        loudness = dict(_default_values().loudness)
        values = HearingValues(
            loudness=loudness,
            loss_per_passage=SoundLoss(15),
            clear_from=SoundLevel(50),
            muffled_from=SoundLevel(35),
            faint_from=SoundLevel(20),
            attentive_allowance=SoundLoss(15),
        )

        loudness[Loudness.NORMAL] = SoundLevel(10)

        assert values.level_of(Loudness.NORMAL) == SoundLevel(60)
