"""空腹・疲労と HP の段階の梯子が、古い run と同じ区切りで段階の名前を選び、並びの崩れた梯子を断ることを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.body_tiers import HitPointsTier, HitPointsTiers, NeedTier, NeedTiers
from ai_rpg_world.game_world.domain.exception.surroundings_texts_exception import BodyTierLadderException
from ai_rpg_world.game_world.domain.value_object import DisplayName, HitPoints
from tests.game_world.support.world_design_for_tests import scene_texts


class TestNeedTiers:
    """NeedTiers.name_of が、上限に対する割合で、その割合以上から始まる最も高い段階を選ぶことを保証する。"""

    @pytest.mark.parametrize(
        ("amount", "expected"),
        [
            (0, "問題なし"),
            (19, "問題なし"),
            (20, "少し"),
            (39, "少し"),
            (40, "やや感じる"),
            (60, "高い"),
            (79, "高い"),
            (80, "危険"),
            (100, "危険"),
        ],
    )
    def test_tier_starts_at_its_percent_of_a_limit_of_100(self, amount: int, expected: str) -> None:
        """上限 100 のとき、0・20・40・60・80 から次の段階に上がる。"""
        assert scene_texts().need_tiers.name_of(amount, 100) == DisplayName(expected)

    def test_percent_is_taken_against_the_limit(self) -> None:
        """上限 200 のとき、39 はまだ「問題なし」で、40 (20%) から「少し」になる。"""
        tiers = scene_texts().need_tiers

        assert (tiers.name_of(39, 200), tiers.name_of(40, 200)) == (DisplayName("問題なし"), DisplayName("少し"))

    @pytest.mark.parametrize("starts", [(), (10, 50), (0, 50, 50), (0, 60, 40), (0, 100)])
    def test_ladder_not_rising_from_zero_below_100_is_refused(self, starts: tuple[int, ...]) -> None:
        """空、0 から始まらない、同じ値や下がる値を含む、100 以上の段階を含む梯子は BodyTierLadderException を投げる。"""
        with pytest.raises(BodyTierLadderException):
            NeedTiers(tuple(NeedTier(start, DisplayName(f"段階{start}")) for start in starts))


class TestHitPointsTiers:
    """HitPointsTiers.name_of が、最大 HP に対する割合で、その割合以下で終わる最も低い段階を選ぶことを保証する。"""

    @pytest.mark.parametrize(
        ("current", "expected"),
        [
            (0, "瀕死"),
            (15, "瀕死"),
            (16, "危険"),
            (35, "危険"),
            (36, "消耗"),
            (60, "消耗"),
            (61, "良好"),
            (100, "良好"),
        ],
    )
    def test_tier_ends_at_its_percent_of_100(self, current: int, expected: str) -> None:
        """最大 100 のとき、15 以下は瀕死、35 以下は危険、60 以下は消耗、それより上は良好。"""
        assert scene_texts().hit_points_tiers.name_of(HitPoints(current=current, maximum=100)) == DisplayName(expected)

    def test_percent_is_taken_against_the_maximum(self) -> None:
        """最大 40 のとき、6 (15%) は瀕死で、7 は危険になる。"""
        tiers = scene_texts().hit_points_tiers

        assert (tiers.name_of(HitPoints(6, 40)), tiers.name_of(HitPoints(7, 40))) == (
            DisplayName("瀕死"),
            DisplayName("危険"),
        )

    @pytest.mark.parametrize("ends", [(), (15, 60), (15, 15, 100), (60, 15, 100), (-1, 100)])
    def test_ladder_not_rising_to_100_is_refused(self, ends: tuple[int, ...]) -> None:
        """空、100 で終わらない、同じ値や下がる値を含む、0 未満から始まる梯子は BodyTierLadderException を投げる。"""
        with pytest.raises(BodyTierLadderException):
            HitPointsTiers(tuple(HitPointsTier(end, DisplayName(f"段階{end}")) for end in ends))
