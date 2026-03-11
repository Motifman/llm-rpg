"""PursuitLastKnownState 値オブジェクトのテスト"""

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import (
    PursuitLastKnownState,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestPursuitLastKnownState:
    """PursuitLastKnownState の生成と不変性を確認する。"""

    def test_create_with_required_fields(self):
        """最後の既知状態を位置情報つきで生成できること"""
        state = PursuitLastKnownState(
            target_id=WorldObjectId(20),
            spot_id=SpotId(3),
            coordinate=Coordinate(7, 8, 0),
        )

        assert state.target_id == WorldObjectId(20)
        assert state.spot_id == SpotId(3)
        assert state.coordinate == Coordinate(7, 8, 0)
        assert state.observed_at_tick is None

    def test_create_with_observed_tick(self):
        """観測tickを保持できること"""
        state = PursuitLastKnownState(
            target_id=WorldObjectId(20),
            spot_id=SpotId(3),
            coordinate=Coordinate(7, 8, 0),
            observed_at_tick=WorldTick(42),
        )

        assert state.observed_at_tick == WorldTick(42)

    def test_state_is_frozen(self):
        """最後の既知状態は不変であること"""
        state = PursuitLastKnownState(
            target_id=WorldObjectId(20),
            spot_id=SpotId(3),
            coordinate=Coordinate(7, 8, 0),
        )

        with pytest.raises(AttributeError):
            state.coordinate = Coordinate(1, 1, 0)  # type: ignore[misc]
