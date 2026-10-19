"""BehaviorStateSnapshot 値オブジェクトのテスト"""

import pytest

from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum
from ai_rpg_world.domain.monster.value_object.behavior_state_snapshot import BehaviorStateSnapshot
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestBehaviorStateSnapshotCreation:
    """BehaviorStateSnapshot の生成テスト（正常・境界）"""

    @pytest.mark.parametrize(
        ("kwargs", "expected_state"),
        [
            ({"state": BehaviorStateEnum.IDLE}, BehaviorStateEnum.IDLE),
            (
                {
                    "state": BehaviorStateEnum.CHASE,
                    "target_id": None,
                    "last_known_target_position": None,
                    "hp_percentage": 1.0,
                    "phase_thresholds": (),
                    "flee_threshold": 0.0,
                },
                BehaviorStateEnum.CHASE,
            ),
        ],
        ids=["required_only", "explicit_defaults"],
    )
    def test_create_with_default_values(self, kwargs, expected_state):
        """省略した既定値と明示した既定値を、指定した状態とともに保持する。"""
        snapshot = BehaviorStateSnapshot(**kwargs)
        assert snapshot.state == expected_state
        assert snapshot.target_id is None
        assert snapshot.last_known_target_position is None
        assert snapshot.hp_percentage == 1.0
        assert snapshot.phase_thresholds == ()
        assert snapshot.flee_threshold == 0.0


    @pytest.mark.parametrize(
        ("kwargs", "expected_values"),
        [
            (
                {
                    "state": BehaviorStateEnum.FLEE,
                    "target_id": WorldObjectId(1),
                    "last_known_target_position": Coordinate(10, 20),
                    "hp_percentage": 0.25,
                    "phase_thresholds": (0.5, 0.25),
                    "flee_threshold": 0.3,
                },
                (BehaviorStateEnum.FLEE, WorldObjectId(1), Coordinate(10, 20),
                 0.25, (0.5, 0.25), 0.3),
            ),
            (
                {"state": BehaviorStateEnum.IDLE, "phase_thresholds": (0.5,)},
                (BehaviorStateEnum.IDLE, None, None, 1.0, (0.5,), 0.0),
            ),
            (
                {"state": BehaviorStateEnum.IDLE, "phase_thresholds": (0.5, 0.25)},
                (BehaviorStateEnum.IDLE, None, None, 1.0, (0.5, 0.25), 0.0),
            ),
        ],
        ids=["all_fields", "single_threshold_tuple", "former_append_input"],
    )
    def test_create_preserves_values_and_immutable_thresholds(self, kwargs, expected_values):
        """指定値を保持し、tupleで渡した閾値はtupleのままでappendを拒否する。"""
        snapshot = BehaviorStateSnapshot(**kwargs)
        state, target, position, hp, phases, flee = expected_values
        assert snapshot.state == state
        assert snapshot.target_id == target
        assert snapshot.last_known_target_position == position
        assert snapshot.hp_percentage == hp
        assert snapshot.phase_thresholds == phases
        assert snapshot.flee_threshold == flee
        assert isinstance(snapshot.phase_thresholds, tuple)
        with pytest.raises(AttributeError):
            snapshot.phase_thresholds.append(0.1)  # type: ignore[union-attr]


class TestBehaviorStateSnapshotImmutability:
    """不変性の検証"""

    def test_snapshot_is_frozen(self):
        """スナップショットは frozen で属性代入できないこと"""
        snapshot = BehaviorStateSnapshot(state=BehaviorStateEnum.IDLE)
        with pytest.raises(AttributeError):
            snapshot.state = BehaviorStateEnum.CHASE  # type: ignore[misc]
        with pytest.raises(AttributeError):
            snapshot.target_id = WorldObjectId(1)  # type: ignore[misc]
        with pytest.raises(AttributeError):
            snapshot.hp_percentage = 0.5  # type: ignore[misc]
