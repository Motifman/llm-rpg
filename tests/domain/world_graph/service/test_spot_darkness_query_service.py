"""SpotDarknessQueryService のテスト。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.service.spot_darkness_query_service import (
    SpotDarknessQueryService,
)
from ai_rpg_world.domain.world_graph.value_object.time_of_day import TimeOfDay


def _spot(*, is_outdoor: bool, is_intrinsically_dark: bool) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(1),
        name="X",
        description="",
        category=SpotCategoryEnum.TOWN,
        parent_id=None,
        is_outdoor=is_outdoor,
        is_intrinsically_dark=is_intrinsically_dark,
    )


def _tod(is_dark: bool) -> TimeOfDay:
    return TimeOfDay(
        ratio=0.0 if not is_dark else 0.9,
        phase_name="x",
        display_text="X",
        ambient_light=1.0 if not is_dark else 0.05,
        is_dark=is_dark,
    )


@pytest.fixture
def service():
    return SpotDarknessQueryService()


class TestSpotDarknessQueryService:
    """SpotDarknessQueryService.is_dark の合成判定挙動。"""

    def test_intrinsically_dark_always_dark(self, service: SpotDarknessQueryService) -> None:
        """intrinsic dark のスポットは時刻によらず常に暗いと判定される。"""
        spot = _spot(is_outdoor=False, is_intrinsically_dark=True)
        assert service.is_dark(spot, _tod(False)) is True
        assert service.is_dark(spot, _tod(True)) is True
        assert service.is_dark(spot, None) is True

    def test_outdoor_dark_only_when_phase_dark(self, service: SpotDarknessQueryService) -> None:
        """屋外スポットはフェーズが暗い時のみ暗いと判定される。"""
        spot = _spot(is_outdoor=True, is_intrinsically_dark=False)
        assert service.is_dark(spot, _tod(False)) is False
        assert service.is_dark(spot, _tod(True)) is True

    def test_outdoor_with_no_cycle_is_not_dark(self, service: SpotDarknessQueryService) -> None:
        """昼夜サイクル無効（time_of_day=None）の屋外は暗くない扱いになる。"""
        spot = _spot(is_outdoor=True, is_intrinsically_dark=False)
        assert service.is_dark(spot, None) is False

    def test_indoor_non_intrinsic_dark_is_not_dark(self, service: SpotDarknessQueryService) -> None:
        """屋内かつ非 intrinsic のスポットは本サービスでは暗くないと判定される（視覚モデルは atmosphere 側で扱う）。"""
        spot = _spot(is_outdoor=False, is_intrinsically_dark=False)
        assert service.is_dark(spot, _tod(True)) is False
        assert service.is_dark(spot, _tod(False)) is False
        assert service.is_dark(spot, None) is False

    def test_intrinsic_dark_outdoor_is_dark(self, service: SpotDarknessQueryService) -> None:
        """is_intrinsically_dark と屋外条件の両方が成立しても True が返る（OR 合成）。"""
        spot = _spot(is_outdoor=True, is_intrinsically_dark=True)
        assert service.is_dark(spot, _tod(False)) is True
