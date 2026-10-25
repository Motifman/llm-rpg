import unittest.mock as mock
from types import SimpleNamespace

from ai_rpg_world.application.world.contracts.dtos import VisibleObjectDto
from ai_rpg_world.application.world.services.pursuit_continuation_service import (
    PursuitContinuationAction,
    PursuitContinuationService,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_navigation_state import PlayerNavigationState
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import PursuitFailureReason
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import PursuitTargetSnapshot
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestPursuitContinuationService:
    """追跡対象の可視性と経路の状態に応じて追跡の継続・失敗を決める。"""

    @staticmethod
    def _player_status(player_id: int = 1) -> PlayerStatusAggregate:
        return PlayerStatusAggregate(
            player_id=PlayerId(player_id),
            base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
            stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
            exp_table=ExpTable(100, 1.5),
            growth=Growth(1, 0, ExpTable(100, 1.5)),
            gold=Gold(0),
            hp=Hp.create(100, 100),
            mp=Mp.create(30, 30),
            stamina=Stamina.create(100, 100),
            navigation_state=PlayerNavigationState.from_parts(
                current_spot_id=SpotId(1), current_coordinate=Coordinate(0, 0, 0)
            ),
        )

    @staticmethod
    def _current_state(
        *, visible_objects: list[VisibleObjectDto], current_spot_id: int = 1, has_active_path: bool = False
    ) -> SimpleNamespace:
        return SimpleNamespace(
            visible_objects=visible_objects, has_active_path=has_active_path, current_spot_id=current_spot_id
        )

    @staticmethod
    def _visible_target(
        target_id: int, *, x: int, y: int, z: int = 0, object_kind: str = "monster"
    ) -> VisibleObjectDto:
        return VisibleObjectDto(
            object_id=target_id,
            object_type="actor",
            x=x,
            y=y,
            z=z,
            distance=1,
            display_name=f"target-{target_id}",
            object_kind=object_kind,
        )

    def test_pursuit_continuation_marks_pathless_pursuit_for_same_tick_continuation(self) -> None:
        """追跡経路がないとき、再計画して同じtickの移動継続を許可する。"""
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(target_id=WorldObjectId(99), spot_id=SpotId(1), coordinate=Coordinate(2, 0, 0))
        )
        movement_service = mock.Mock()
        movement_service.replan_path_to_coordinate_in_current_unit_of_work.return_value = SimpleNamespace(success=True)
        world_query_service = mock.Mock()
        world_query_service.get_player_current_state.return_value = self._current_state(
            visible_objects=[], has_active_path=False
        )
        continuation_service = PursuitContinuationService(world_query_service, movement_service=movement_service)
        decision = continuation_service.evaluate_tick(status)
        assert decision.continuation_checked is True
        assert decision.action == PursuitContinuationAction.CONTINUE_PURSUIT
        assert decision.should_advance_movement is True
        assert decision.replan_required is True
        assert decision.replan_attempted is True
        assert decision.target_world_object_id == 99
        movement_service.replan_path_to_coordinate_in_current_unit_of_work.assert_called_once()
        world_query_service.get_player_current_state.assert_called_once()

    def test_pursuit_continuation_refreshes_visible_target_only_when_coordinate_changes(self) -> None:
        """可視対象の座標が変化した場合だけ追跡情報を更新し、経路を再計画する。"""
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(target_id=WorldObjectId(99), spot_id=SpotId(1), coordinate=Coordinate(2, 0, 0))
        )
        world_query_service = mock.Mock()
        world_query_service.get_player_current_state.side_effect = [
            self._current_state(visible_objects=[self._visible_target(99, x=2, y=0)], has_active_path=True),
            self._current_state(visible_objects=[self._visible_target(99, x=3, y=0)], has_active_path=True),
        ]
        movement_service = mock.Mock()
        movement_service.replan_path_to_coordinate_in_current_unit_of_work.return_value = SimpleNamespace(success=True)
        continuation_service = PursuitContinuationService(world_query_service, movement_service=movement_service)
        first = continuation_service.evaluate_tick(status)
        second = continuation_service.evaluate_tick(status)
        assert first.pursuit_updated is False
        assert first.replan_attempted is False
        assert second.pursuit_updated is True
        assert second.replan_attempted is True
        assert status.pursuit_state is not None
        assert status.pursuit_state.target_snapshot.coordinate == Coordinate(3, 0, 0)
        assert status.pursuit_state.last_known.coordinate == Coordinate(3, 0, 0)

    def test_pursuit_continuation_preserves_last_visible_snapshot_when_target_is_lost(self) -> None:
        """対象を見失ったとき、最後に見えた座標を保持して追跡を継続する。"""
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(target_id=WorldObjectId(55), spot_id=SpotId(1), coordinate=Coordinate(4, 1, 0))
        )
        movement_service = mock.Mock()
        movement_service.replan_path_to_coordinate_in_current_unit_of_work.return_value = SimpleNamespace(success=True)
        world_query_service = mock.Mock()
        world_query_service.get_player_current_state.return_value = self._current_state(
            visible_objects=[], has_active_path=False
        )
        continuation_service = PursuitContinuationService(world_query_service, movement_service=movement_service)
        decision = continuation_service.evaluate_tick(status)
        assert decision.action == PursuitContinuationAction.CONTINUE_PURSUIT
        assert decision.has_visible_target is False
        assert decision.replan_attempted is True
        assert status.pursuit_state is not None
        assert status.pursuit_state.target_snapshot.coordinate == Coordinate(4, 1, 0)
        assert status.pursuit_state.last_known.coordinate == Coordinate(4, 1, 0)

    def test_pursuit_continuation_invisible_target_does_not_become_target_missing(self) -> None:
        """対象が見えなくても別スポットに実在すれば、対象消失として失敗しない。"""
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(target_id=WorldObjectId(66), spot_id=SpotId(1), coordinate=Coordinate(4, 1, 0))
        )
        movement_service = mock.Mock()
        movement_service.replan_path_to_coordinate_in_current_unit_of_work.return_value = SimpleNamespace(success=True)
        world_query_service = mock.Mock()
        world_query_service.get_player_current_state.return_value = self._current_state(
            visible_objects=[], has_active_path=False
        )
        physical_map_repository = mock.Mock()
        physical_map_repository.find_spot_id_by_object_id.return_value = SpotId(2)
        continuation_service = PursuitContinuationService(
            world_query_service, movement_service=movement_service, physical_map_repository=physical_map_repository
        )
        decision = continuation_service.evaluate_tick(status)
        assert decision.action == PursuitContinuationAction.CONTINUE_PURSUIT
        assert decision.failure_reason is None
        assert status.pursuit_state is not None

    def test_pursuit_continuation_fails_with_target_missing_when_world_lookup_cannot_resolve_target(self) -> None:
        """対象を世界から取得できないとき、追跡を失敗させて予定経路を消す。"""
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(target_id=WorldObjectId(70), spot_id=SpotId(1), coordinate=Coordinate(4, 1, 0))
        )
        status.set_destination(Coordinate(1, 0, 0), [Coordinate(0, 0, 0), Coordinate(1, 0, 0)], goal_spot_id=SpotId(1))
        world_query_service = mock.Mock()
        world_query_service.get_player_current_state.return_value = self._current_state(
            visible_objects=[], has_active_path=True
        )
        physical_map_repository = mock.Mock()
        physical_map_repository.find_spot_id_by_object_id.return_value = None
        continuation_service = PursuitContinuationService(
            world_query_service, physical_map_repository=physical_map_repository
        )
        decision = continuation_service.evaluate_tick(status)
        assert decision.action == PursuitContinuationAction.PURSUIT_FAILED
        assert decision.failure_reason == PursuitFailureReason.TARGET_MISSING
        assert status.has_active_pursuit is False
        assert status.planned_path == []

    def test_pursuit_continuation_fails_with_vision_lost_at_last_known(self) -> None:
        """最後に見た座標へ着いても対象が見えないとき、視界喪失で追跡を終了する。"""
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(target_id=WorldObjectId(71), spot_id=SpotId(1), coordinate=Coordinate(0, 0, 0))
        )
        world_query_service = mock.Mock()
        world_query_service.get_player_current_state.return_value = self._current_state(
            visible_objects=[], has_active_path=False
        )
        physical_map_repository = mock.Mock()
        physical_map_repository.find_spot_id_by_object_id.return_value = SpotId(1)
        continuation_service = PursuitContinuationService(
            world_query_service, physical_map_repository=physical_map_repository
        )
        decision = continuation_service.evaluate_tick(status)
        assert decision.action == PursuitContinuationAction.PURSUIT_FAILED
        assert decision.failure_reason == PursuitFailureReason.VISION_LOST_AT_LAST_KNOWN
        assert status.has_active_pursuit is False

    def test_pursuit_continuation_fails_with_path_unreachable_for_invisible_target(self) -> None:
        """見えない対象への経路を再計画できないとき、到達不能で追跡と予定経路を消す。"""
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(target_id=WorldObjectId(72), spot_id=SpotId(1), coordinate=Coordinate(3, 0, 0))
        )
        movement_service = mock.Mock()
        movement_service.replan_path_to_coordinate_in_current_unit_of_work.return_value = SimpleNamespace(success=False)
        world_query_service = mock.Mock()
        world_query_service.get_player_current_state.return_value = self._current_state(
            visible_objects=[], has_active_path=False
        )
        physical_map_repository = mock.Mock()
        physical_map_repository.find_spot_id_by_object_id.return_value = SpotId(1)
        continuation_service = PursuitContinuationService(
            world_query_service, movement_service=movement_service, physical_map_repository=physical_map_repository
        )
        decision = continuation_service.evaluate_tick(status)
        assert decision.action == PursuitContinuationAction.PURSUIT_FAILED
        assert decision.failure_reason == PursuitFailureReason.PATH_UNREACHABLE
        assert status.has_active_pursuit is False
        assert status.planned_path == []
