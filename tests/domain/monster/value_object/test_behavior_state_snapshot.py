"""BehaviorStateSnapshot 値オブジェクトのテスト"""

import pytest

from ai_rpg_world.domain.monster.value_object.behavior_state_snapshot import BehaviorStateSnapshot
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum


class TestBehaviorStateSnapshotCreation:
    """BehaviorStateSnapshot の生成テスト（正常・境界）"""

    def test_create_with_required_only(self):
        """必須の state のみで作成できること"""
        snapshot = BehaviorStateSnapshot(state=BehaviorStateEnum.IDLE)
        assert snapshot.state == BehaviorStateEnum.IDLE
        assert snapshot.target_id is None
        assert snapshot.last_known_target_position is None
        assert snapshot.hp_percentage == 1.0
        assert snapshot.phase_thresholds == ()
        assert snapshot.flee_threshold == 0.0

    def test_create_with_defaults_explicit(self):
        """デフォルト値を明示して作成できること"""
        snapshot = BehaviorStateSnapshot(
            state=BehaviorStateEnum.CHASE,
            target_id=None,
            last_known_target_position=None,
            hp_percentage=1.0,
            phase_thresholds=(),
            flee_threshold=0.0,
        )
        assert snapshot.state == BehaviorStateEnum.CHASE
        assert snapshot.target_id is None
        assert snapshot.phase_thresholds == ()

    def test_create_with_all_fields(self):
        """全フィールドを指定して作成できること"""
        oid = WorldObjectId(1)
        coord = Coordinate(10, 20)
        snapshot = BehaviorStateSnapshot(
            state=BehaviorStateEnum.FLEE,
            target_id=oid,
            last_known_target_position=coord,
            hp_percentage=0.25,
            phase_thresholds=(0.5, 0.25),
            flee_threshold=0.3,
        )
        assert snapshot.state == BehaviorStateEnum.FLEE
        assert snapshot.target_id == oid
        assert snapshot.last_known_target_position == coord
        assert snapshot.hp_percentage == 0.25
        assert snapshot.phase_thresholds == (0.5, 0.25)
        assert snapshot.flee_threshold == 0.3

    def test_create_with_tuple_phase_thresholds(self):
        """phase_thresholds は tuple で保持されること"""
        snapshot = BehaviorStateSnapshot(
            state=BehaviorStateEnum.IDLE,
            phase_thresholds=(0.5,),
        )
        assert snapshot.phase_thresholds == (0.5,)
        assert isinstance(snapshot.phase_thresholds, tuple)


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

    def test_phase_thresholds_is_immutable_tuple(self):
        """phase_thresholds は tuple のため呼び出し元がリストで渡しても不変に保たれること"""
        snapshot = BehaviorStateSnapshot(
            state=BehaviorStateEnum.IDLE,
            phase_thresholds=(0.5, 0.25),
        )
        # tuple は変更不可
        with pytest.raises(AttributeError):
            snapshot.phase_thresholds.append(0.1)  # type: ignore[union-attr]
