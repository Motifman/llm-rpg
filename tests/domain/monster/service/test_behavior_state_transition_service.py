"""モンスターの行動遷移に渡す対象の値を保証する。"""

import pytest

from ai_rpg_world.domain.monster.service.behavior_state_transition_service import SpotTargetParams
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestSpotTargetParams:
    """SpotTargetParams の生成と不変性"""

    def test_create_with_required(self):
        """必須フィールドで作成できること"""
        oid = WorldObjectId(1)
        coord = Coordinate(5, 5)
        params = SpotTargetParams(target_id=oid, coordinate=coord)
        assert params.target_id == oid
        assert params.coordinate == coord
        assert params.effective_flee_threshold is None
        assert params.allow_chase is None


    def test_spot_target_params_is_frozen(self):
        """SpotTargetParams は frozen であること"""
        params = SpotTargetParams(
            target_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0),
        )
        with pytest.raises(AttributeError):
            params.target_id = WorldObjectId(2)  # type: ignore[misc]
