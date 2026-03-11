"""PursuitState 値オブジェクトのテスト"""

import pytest

from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import (
    PursuitFailureReason,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import (
    PursuitLastKnownState,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_state import PursuitState
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import (
    PursuitTargetSnapshot,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestPursuitState:
    """PursuitState の基本語彙を確認する。"""

    def test_create_with_target_snapshot_and_last_known(self):
        """可視中の対象と last-known を同時に保持できること"""
        state = PursuitState(
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            target_snapshot=PursuitTargetSnapshot(
                target_id=WorldObjectId(2),
                spot_id=SpotId(5),
                coordinate=Coordinate(10, 4, 0),
            ),
            last_known=PursuitLastKnownState(
                target_id=WorldObjectId(2),
                spot_id=SpotId(5),
                coordinate=Coordinate(10, 4, 0),
            ),
        )

        assert state.actor_id == WorldObjectId(1)
        assert state.target_id == WorldObjectId(2)
        assert state.has_target_snapshot is True
        assert state.last_known is not None

    def test_create_with_last_known_only(self):
        """視界喪失後も last-known だけで追跡状態を表現できること"""
        state = PursuitState(
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            last_known=PursuitLastKnownState(
                target_id=WorldObjectId(2),
                spot_id=SpotId(5),
                coordinate=Coordinate(10, 4, 0),
            ),
        )

        assert state.has_target_snapshot is False
        assert state.last_known == PursuitLastKnownState(
            target_id=WorldObjectId(2),
            spot_id=SpotId(5),
            coordinate=Coordinate(10, 4, 0),
        )

    def test_create_failed_state_with_structured_reason(self):
        """失敗理由を構造化 enum で保持できること"""
        state = PursuitState(
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            last_known=PursuitLastKnownState(
                target_id=WorldObjectId(2),
                spot_id=SpotId(5),
                coordinate=Coordinate(10, 4, 0),
            ),
            failure_reason=PursuitFailureReason.VISION_LOST_AT_LAST_KNOWN,
        )

        assert state.is_failed is True
        assert (
            state.failure_reason
            == PursuitFailureReason.VISION_LOST_AT_LAST_KNOWN
        )

    def test_requires_target_snapshot_or_last_known(self):
        """現在情報か last-known のどちらかは必須であること"""
        with pytest.raises(ValueError):
            PursuitState(
                actor_id=WorldObjectId(1),
                target_id=WorldObjectId(2),
            )

    def test_rejects_mismatched_last_known_target(self):
        """last-known の対象ID不一致を拒否すること"""
        with pytest.raises(ValueError):
            PursuitState(
                actor_id=WorldObjectId(1),
                target_id=WorldObjectId(2),
                last_known=PursuitLastKnownState(
                    target_id=WorldObjectId(3),
                    spot_id=SpotId(5),
                    coordinate=Coordinate(10, 4, 0),
                ),
            )

    def test_pursuit_state_is_separate_from_static_movement_fields(self):
        """追跡状態が static movement の destination/path を再利用しないこと"""
        state = PursuitState(
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            target_snapshot=PursuitTargetSnapshot(
                target_id=WorldObjectId(2),
                spot_id=SpotId(5),
                coordinate=Coordinate(10, 4, 0),
            ),
            last_known=PursuitLastKnownState(
                target_id=WorldObjectId(2),
                spot_id=SpotId(5),
                coordinate=Coordinate(10, 4, 0),
            ),
        )

        assert not hasattr(state, "current_destination")
        assert not hasattr(state, "planned_path")
        assert not hasattr(state, "goal_spot_id")
