"""
PlayerPursuitState のテスト

正常ケース・例外ケース・境界ケースの網羅的検証。
"""

import pytest

from ai_rpg_world.domain.player.value_object.player_pursuit_state import PlayerPursuitState
from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import (
    PursuitLastKnownState,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_state import PursuitState
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import (
    PursuitTargetSnapshot,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestPlayerPursuitStateCreation:
    """PlayerPursuitState の生成"""

    def test_empty_creates_no_pursuit(self):
        """empty() で追跡なしの状態を作成"""
        state = PlayerPursuitState.empty()
        assert state.pursuit is None
        assert state.has_active_pursuit is False
        assert state.target_id is None
        assert state.target_snapshot is None
        assert state.last_known is None

    def test_default_constructor_has_no_pursuit(self):
        """デフォルトで追跡なし"""
        state = PlayerPursuitState()
        assert state.pursuit is None
        assert state.has_active_pursuit is False

    def test_from_parts_with_none_creates_empty(self):
        """from_parts(pursuit=None) で空状態"""
        state = PlayerPursuitState.from_parts(pursuit=None)
        assert state.has_active_pursuit is False

    def test_from_parts_with_pursuit_creates_active(self):
        """from_parts で PursuitState から構築"""
        actor_id = WorldObjectId(1001)
        target_id = WorldObjectId(2001)
        spot_id = SpotId(1)
        snapshot = PursuitTargetSnapshot(
            target_id=target_id,
            spot_id=spot_id,
            coordinate=Coordinate(3, 4, 0),
        )
        last_known = PursuitLastKnownState(
            target_id=target_id,
            spot_id=spot_id,
            coordinate=Coordinate(3, 4, 0),
            observed_at_tick=WorldTick(100),
        )
        pursuit = PursuitState(
            actor_id=actor_id,
            target_id=target_id,
            target_snapshot=snapshot,
            last_known=last_known,
        )
        state = PlayerPursuitState.from_parts(pursuit=pursuit)
        assert state.has_active_pursuit is True
        assert state.pursuit == pursuit
        assert state.target_id == target_id


class TestPlayerPursuitStateCleared:
    """cleared() のテスト"""

    @pytest.fixture
    def actor_id(self) -> WorldObjectId:
        return WorldObjectId(1001)

    @pytest.fixture
    def target_id(self) -> WorldObjectId:
        return WorldObjectId(2001)

    @pytest.fixture
    def spot_id(self) -> SpotId:
        return SpotId(1)

    @pytest.fixture
    def target_snapshot(self, target_id: WorldObjectId, spot_id: SpotId) -> PursuitTargetSnapshot:
        return PursuitTargetSnapshot(
            target_id=target_id,
            spot_id=spot_id,
            coordinate=Coordinate(3, 4, 0),
        )

    @pytest.fixture
    def last_known(self, target_id: WorldObjectId, spot_id: SpotId) -> PursuitLastKnownState:
        return PursuitLastKnownState(
            target_id=target_id,
            spot_id=spot_id,
            coordinate=Coordinate(5, 6, 0),
            observed_at_tick=WorldTick(100),
        )

    @pytest.fixture
    def state_with_pursuit(
        self,
        actor_id: WorldObjectId,
        target_id: WorldObjectId,
        target_snapshot: PursuitTargetSnapshot,
        last_known: PursuitLastKnownState,
    ) -> PlayerPursuitState:
        return PlayerPursuitState.empty().with_started(
            actor_id=actor_id,
            target_id=target_id,
            target_snapshot=target_snapshot,
            last_known=last_known,
        )

    def test_cleared_from_empty_returns_empty(self):
        """空の状態で cleared しても空のまま"""
        state = PlayerPursuitState.empty()
        cleared = state.cleared()
        assert cleared.pursuit is None
        assert cleared.has_active_pursuit is False
        assert cleared is not state

    def test_cleared_from_active_returns_empty(
        self,
        state_with_pursuit: PlayerPursuitState,
    ):
        """追跡中に cleared で追跡解除"""
        cleared = state_with_pursuit.cleared()
        assert cleared.pursuit is None
        assert cleared.has_active_pursuit is False
        assert cleared.target_id is None


class TestPlayerPursuitStateWithStarted:
    """with_started() のテスト"""

    @pytest.fixture
    def actor_id(self) -> WorldObjectId:
        return WorldObjectId(1001)

    @pytest.fixture
    def target_id(self) -> WorldObjectId:
        return WorldObjectId(2001)

    @pytest.fixture
    def spot_id(self) -> SpotId:
        return SpotId(2)

    @pytest.fixture
    def target_snapshot(self, target_id: WorldObjectId, spot_id: SpotId) -> PursuitTargetSnapshot:
        return PursuitTargetSnapshot(
            target_id=target_id,
            spot_id=spot_id,
            coordinate=Coordinate(10, 20, 0),
        )

    @pytest.fixture
    def last_known(self, target_id: WorldObjectId, spot_id: SpotId) -> PursuitLastKnownState:
        return PursuitLastKnownState(
            target_id=target_id,
            spot_id=spot_id,
            coordinate=Coordinate(10, 20, 0),
            observed_at_tick=WorldTick(50),
        )

    def test_with_started_creates_active_pursuit(
        self,
        actor_id: WorldObjectId,
        target_id: WorldObjectId,
        target_snapshot: PursuitTargetSnapshot,
        last_known: PursuitLastKnownState,
    ):
        """with_started で追跡状態になる"""
        state = PlayerPursuitState.empty().with_started(
            actor_id=actor_id,
            target_id=target_id,
            target_snapshot=target_snapshot,
            last_known=last_known,
        )
        assert state.has_active_pursuit is True
        assert state.target_id == target_id
        assert state.target_snapshot == target_snapshot
        assert state.last_known == last_known
        assert state.pursuit is not None
        assert state.pursuit.actor_id == actor_id
        assert state.pursuit.target_id == target_id

    def test_with_started_returns_new_instance(
        self,
        actor_id: WorldObjectId,
        target_id: WorldObjectId,
        target_snapshot: PursuitTargetSnapshot,
        last_known: PursuitLastKnownState,
    ):
        """with_started は新しいインスタンスを返す"""
        empty = PlayerPursuitState.empty()
        started = empty.with_started(
            actor_id=actor_id,
            target_id=target_id,
            target_snapshot=target_snapshot,
            last_known=last_known,
        )
        assert started is not empty
        assert empty.has_active_pursuit is False


class TestPlayerPursuitStateWithUpdated:
    """with_updated() のテスト"""

    @pytest.fixture
    def actor_id(self) -> WorldObjectId:
        return WorldObjectId(3001)

    @pytest.fixture
    def target_id(self) -> WorldObjectId:
        return WorldObjectId(4001)

    @pytest.fixture
    def spot_id(self) -> SpotId:
        return SpotId(3)

    @pytest.fixture
    def original_snapshot(self, target_id: WorldObjectId, spot_id: SpotId) -> PursuitTargetSnapshot:
        return PursuitTargetSnapshot(
            target_id=target_id,
            spot_id=spot_id,
            coordinate=Coordinate(1, 2, 0),
        )

    @pytest.fixture
    def original_last_known(self, target_id: WorldObjectId, spot_id: SpotId) -> PursuitLastKnownState:
        return PursuitLastKnownState(
            target_id=target_id,
            spot_id=spot_id,
            coordinate=Coordinate(1, 2, 0),
            observed_at_tick=WorldTick(100),
        )

    @pytest.fixture
    def state_with_pursuit(
        self,
        actor_id: WorldObjectId,
        target_id: WorldObjectId,
        original_snapshot: PursuitTargetSnapshot,
        original_last_known: PursuitLastKnownState,
    ) -> PlayerPursuitState:
        return PlayerPursuitState.empty().with_started(
            actor_id=actor_id,
            target_id=target_id,
            target_snapshot=original_snapshot,
            last_known=original_last_known,
        )

    def test_with_updated_changes_snapshot_and_last_known(
        self,
        actor_id: WorldObjectId,
        target_id: WorldObjectId,
        state_with_pursuit: PlayerPursuitState,
    ):
        """with_updated で target_snapshot と last_known が更新される"""
        new_snapshot = PursuitTargetSnapshot(
            target_id=target_id,
            spot_id=SpotId(3),
            coordinate=Coordinate(7, 8, 0),
        )
        new_last_known = PursuitLastKnownState(
            target_id=target_id,
            spot_id=SpotId(3),
            coordinate=Coordinate(7, 8, 0),
            observed_at_tick=WorldTick(200),
        )
        updated = state_with_pursuit.with_updated(
            target_snapshot=new_snapshot,
            last_known=new_last_known,
        )
        assert updated.target_snapshot == new_snapshot
        assert updated.last_known == new_last_known
        assert updated is not state_with_pursuit

    def test_with_updated_unchanged_returns_self(
        self,
        state_with_pursuit: PlayerPursuitState,
        original_snapshot: PursuitTargetSnapshot,
        original_last_known: PursuitLastKnownState,
    ):
        """変更がないとき self を返す（同一インスタンス）"""
        updated = state_with_pursuit.with_updated(
            target_snapshot=original_snapshot,
            last_known=original_last_known,
        )
        assert updated is state_with_pursuit

    def test_with_updated_none_snapshot_keeps_current(
        self,
        target_id: WorldObjectId,
        state_with_pursuit: PlayerPursuitState,
        original_snapshot: PursuitTargetSnapshot,
    ):
        """target_snapshot=None のとき現在の snapshot を保持"""
        new_last_known = PursuitLastKnownState(
            target_id=target_id,
            spot_id=SpotId(3),
            coordinate=Coordinate(9, 10, 0),
            observed_at_tick=WorldTick(300),
        )
        updated = state_with_pursuit.with_updated(
            target_snapshot=None,
            last_known=new_last_known,
        )
        assert updated.target_snapshot == original_snapshot
        assert updated.last_known == new_last_known

    def test_with_updated_empty_raises_value_error(self):
        """追跡なしの状態で with_updated は ValueError を送出"""
        empty = PlayerPursuitState.empty()
        last_known = PursuitLastKnownState(
            target_id=WorldObjectId(999),
            spot_id=SpotId(1),
            coordinate=Coordinate(0, 0, 0),
            observed_at_tick=None,
        )
        with pytest.raises(ValueError, match="Cannot update pursuit when no active pursuit exists"):
            empty.with_updated(
                target_snapshot=None,
                last_known=last_known,
            )


class TestPlayerPursuitStateProperties:
    """プロパティの委譲テスト"""

    @pytest.fixture
    def active_state(self) -> PlayerPursuitState:
        spot = SpotId(1)
        target_id = WorldObjectId(5001)
        return PlayerPursuitState.empty().with_started(
            actor_id=WorldObjectId(5000),
            target_id=target_id,
            target_snapshot=PursuitTargetSnapshot(
                target_id=target_id,
                spot_id=spot,
                coordinate=Coordinate(0, 0, 0),
            ),
            last_known=PursuitLastKnownState(
                target_id=target_id,
                spot_id=spot,
                coordinate=Coordinate(0, 0, 0),
                observed_at_tick=None,
            ),
        )

    def test_target_id_delegates_to_pursuit(self, active_state: PlayerPursuitState):
        assert active_state.target_id == WorldObjectId(5001)

    def test_target_snapshot_delegates_to_pursuit(self, active_state: PlayerPursuitState):
        assert active_state.target_snapshot is not None
        assert active_state.target_snapshot.target_id == WorldObjectId(5001)

    def test_last_known_delegates_to_pursuit(self, active_state: PlayerPursuitState):
        assert active_state.last_known is not None


class TestPlayerPursuitStateEquality:
    """等価性のテスト"""

    def test_empty_states_are_equal(self):
        """空状態同士は等価"""
        a = PlayerPursuitState.empty()
        b = PlayerPursuitState.empty()
        assert a == b

    def test_from_parts_with_same_pursuit_are_equal(self):
        """同一 PursuitState から構築したインスタンスは等価"""
        spot = SpotId(1)
        target_id = WorldObjectId(99)
        pursuit = PursuitState(
            actor_id=WorldObjectId(1),
            target_id=target_id,
            target_snapshot=PursuitTargetSnapshot(
                target_id=target_id,
                spot_id=spot,
                coordinate=Coordinate(0, 0, 0),
            ),
            last_known=PursuitLastKnownState(
                target_id=target_id,
                spot_id=spot,
                coordinate=Coordinate(0, 0, 0),
                observed_at_tick=None,
            ),
        )
        a = PlayerPursuitState.from_parts(pursuit=pursuit)
        b = PlayerPursuitState.from_parts(pursuit=pursuit)
        assert a == b
