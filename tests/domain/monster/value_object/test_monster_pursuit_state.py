"""
MonsterPursuitState のテスト

追跡の有無、同期、解除、最後の既知情報の更新を検証する。
"""

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.value_object.monster_pursuit_state import MonsterPursuitState
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


class TestMonsterPursuitStateCreation:
    """MonsterPursuitState の生成"""

    @pytest.mark.parametrize("kwargs", [{}, {"pursuit": None}], ids=["default", "explicit_none"])
    def test_empty_state_has_no_pursuit(self, kwargs):
        """追跡を省略しても明示的にNoneを渡しても、すべての取得値は追跡なしを表す。"""
        state = MonsterPursuitState(**kwargs)
        assert state.pursuit is None
        assert state.has_active_pursuit is False
        assert state.target_id is None
        assert state.target_snapshot is None
        assert state.last_known is None


class TestMonsterPursuitStateCleared:
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
    ) -> MonsterPursuitState:
        return MonsterPursuitState().with_sync(
            actor_id=actor_id,
            target_id=target_id,
            target_snapshot=target_snapshot,
            last_known=last_known,
        )

    def test_cleared_from_empty_returns_empty(self):
        """空の状態で cleared しても空のまま"""
        state = MonsterPursuitState()
        cleared = state.cleared()
        assert cleared.pursuit is None
        assert cleared.has_active_pursuit is False
        assert cleared is not state

    def test_cleared_from_active_returns_empty(
        self,
        state_with_pursuit: MonsterPursuitState,
    ):
        """追跡中に cleared で追跡解除"""
        cleared = state_with_pursuit.cleared()
        assert cleared.pursuit is None
        assert cleared.has_active_pursuit is False
        assert cleared.target_id is None


class TestMonsterPursuitStateWithSync:
    """同期結果が指定した追跡情報を公開し、元の空状態を変更しないことを保証する。"""

    @pytest.mark.parametrize(
        ("actor_value", "target_value", "spot_value", "coordinate", "observed_at_tick"),
        [
            (1001, 2001, 2, Coordinate(10, 20, 0), WorldTick(50)),
            (5000, 5001, 1, Coordinate(0, 0, 0), None),
        ],
        ids=["observed_at_tick", "unknown_observation_tick"],
    )
    def test_with_sync_creates_active_pursuit(
        self,
        actor_value: int,
        target_value: int,
        spot_value: int,
        coordinate: Coordinate,
        observed_at_tick: WorldTick | None,
    ):
        """観測tickの有無にかかわらず指定値で追跡を作り、元の空状態とは別の実体を返す。"""
        actor_id = WorldObjectId(actor_value)
        target_id = WorldObjectId(target_value)
        spot_id = SpotId(spot_value)
        target_snapshot = PursuitTargetSnapshot(
            target_id=target_id,
            spot_id=spot_id,
            coordinate=coordinate,
        )
        last_known = PursuitLastKnownState(
            target_id=target_id,
            spot_id=spot_id,
            coordinate=coordinate,
            observed_at_tick=observed_at_tick,
        )
        empty = MonsterPursuitState()
        state = empty.with_sync(
            actor_id=actor_id,
            target_id=target_id,
            target_snapshot=target_snapshot,
            last_known=last_known,
        )
        assert state.has_active_pursuit is True
        assert state.target_id == target_id
        assert state.target_snapshot is not None
        assert state.target_snapshot.target_id == target_id
        assert state.target_snapshot == target_snapshot
        assert state.last_known is not None
        assert state.last_known == last_known
        assert state.pursuit is not None
        assert state.pursuit.actor_id == actor_id
        assert state.pursuit.target_id == target_id

        assert state is not empty
        assert empty.has_active_pursuit is False


class TestMonsterPursuitStateWithPreserveLastKnown:
    """with_preserve_last_known() のテスト"""

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
    def new_last_known(self, target_id: WorldObjectId, spot_id: SpotId) -> PursuitLastKnownState:
        return PursuitLastKnownState(
            target_id=target_id,
            spot_id=spot_id,
            coordinate=Coordinate(7, 8, 0),
            observed_at_tick=WorldTick(200),
        )

    @pytest.fixture
    def fallback_snapshot(self, target_id: WorldObjectId, spot_id: SpotId) -> PursuitTargetSnapshot:
        return PursuitTargetSnapshot(
            target_id=target_id,
            spot_id=spot_id,
            coordinate=Coordinate(7, 8, 0),
        )

    def test_preserve_keeps_existing_target_snapshot(
        self,
        actor_id: WorldObjectId,
        target_id: WorldObjectId,
        original_snapshot: PursuitTargetSnapshot,
        new_last_known: PursuitLastKnownState,
        fallback_snapshot: PursuitTargetSnapshot,
    ):
        """既存の target_snapshot を保持する"""
        state = MonsterPursuitState().with_sync(
            actor_id=actor_id,
            target_id=target_id,
            target_snapshot=original_snapshot,
            last_known=PursuitLastKnownState(
                target_id=target_id,
                spot_id=original_snapshot.spot_id,
                coordinate=original_snapshot.coordinate,
                observed_at_tick=None,
            ),
        )
        updated = state.with_preserve_last_known(
            actor_id=actor_id,
            target_id=target_id,
            last_known=new_last_known,
            target_snapshot=fallback_snapshot,
        )
        assert updated.target_snapshot == original_snapshot
        assert updated.last_known == new_last_known

    def test_preserve_uses_fallback_when_no_existing(
        self,
        actor_id: WorldObjectId,
        target_id: WorldObjectId,
        new_last_known: PursuitLastKnownState,
        fallback_snapshot: PursuitTargetSnapshot,
    ):
        """追跡なしの状態では fallback の target_snapshot を使用"""
        empty = MonsterPursuitState()
        updated = empty.with_preserve_last_known(
            actor_id=actor_id,
            target_id=target_id,
            last_known=new_last_known,
            target_snapshot=fallback_snapshot,
        )
        assert updated.target_snapshot == fallback_snapshot
        assert updated.last_known == new_last_known

    def test_preserve_uses_fallback_when_existing_has_no_snapshot(
        self,
        actor_id: WorldObjectId,
        target_id: WorldObjectId,
        spot_id: SpotId,
        new_last_known: PursuitLastKnownState,
        fallback_snapshot: PursuitTargetSnapshot,
    ):
        """既存snapshotがなくてもfallbackを採用し、古い位置と不明tickを新しい観測情報へ更新する。"""
        pursuit_last_known_only = PursuitState(
            actor_id=actor_id,
            target_id=target_id,
            target_snapshot=None,
            last_known=PursuitLastKnownState(
                target_id=target_id,
                spot_id=spot_id,
                coordinate=Coordinate(1, 1, 0),
                observed_at_tick=None,
            ),
        )
        state = MonsterPursuitState(pursuit=pursuit_last_known_only)
        updated = state.with_preserve_last_known(
            actor_id=actor_id,
            target_id=target_id,
            last_known=new_last_known,
            target_snapshot=fallback_snapshot,
        )
        assert updated.target_snapshot == fallback_snapshot
        assert updated.last_known == new_last_known
