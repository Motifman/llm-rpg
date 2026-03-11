"""PursuitTargetSnapshot 値オブジェクトのテスト"""

import pytest

from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import (
    PursuitTargetSnapshot,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestPursuitTargetSnapshot:
    """PursuitTargetSnapshot の生成と不変性を確認する。"""

    def test_create_with_required_fields(self):
        """対象IDと位置情報を明示して生成できること"""
        snapshot = PursuitTargetSnapshot(
            target_id=WorldObjectId(10),
            spot_id=SpotId(2),
            coordinate=Coordinate(4, 5, 0),
        )

        assert snapshot.target_id == WorldObjectId(10)
        assert snapshot.spot_id == SpotId(2)
        assert snapshot.coordinate == Coordinate(4, 5, 0)

    def test_snapshot_is_frozen(self):
        """スナップショットは不変であること"""
        snapshot = PursuitTargetSnapshot(
            target_id=WorldObjectId(10),
            spot_id=SpotId(2),
            coordinate=Coordinate(4, 5, 0),
        )

        with pytest.raises(AttributeError):
            snapshot.target_id = WorldObjectId(11)  # type: ignore[misc]

    def test_snapshot_keeps_target_metadata_explicit(self):
        """対象メタデータを座標とスポットで明示保持すること"""
        snapshot = PursuitTargetSnapshot(
            target_id=WorldObjectId(10),
            spot_id=SpotId(2),
            coordinate=Coordinate(4, 5, 0),
        )

        assert snapshot.spot_id == SpotId(2)
        assert snapshot.coordinate == Coordinate(4, 5, 0)
