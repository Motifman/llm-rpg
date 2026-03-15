"""
PlayerNavigationState のテスト

正常ケース・例外ケース・境界ケースの網羅的検証。
"""

import pytest

from ai_rpg_world.domain.player.value_object.player_navigation_state import (
    PlayerNavigationState,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestPlayerNavigationStateEmpty:
    """empty() のテスト"""

    def test_creates_empty_state(self):
        """すべて None または空の経路で初期状態を作成"""
        state = PlayerNavigationState.empty()
        assert state.current_spot_id is None
        assert state.current_coordinate is None
        assert state.current_destination is None
        assert state.planned_path == ()
        assert state.goal_destination_type is None
        assert state.goal_spot_id is None
        assert state.goal_location_area_id is None
        assert state.goal_world_object_id is None


class TestPlayerNavigationStateFromParts:
    """from_parts のテスト"""

    def test_builds_from_individual_fields(self):
        """個別フィールドから構築"""
        spot_id = SpotId(1)
        coord = Coordinate(5, 10, 0)
        dest = Coordinate(10, 15, 0)
        path = [Coordinate(5, 10, 0), Coordinate(6, 10, 0), Coordinate(7, 10, 0)]
        goal_spot = SpotId(2)
        goal_loc = LocationAreaId(101)
        goal_obj = WorldObjectId(999)

        state = PlayerNavigationState.from_parts(
            current_spot_id=spot_id,
            current_coordinate=coord,
            current_destination=dest,
            planned_path=path,
            goal_destination_type="location",
            goal_spot_id=goal_spot,
            goal_location_area_id=goal_loc,
            goal_world_object_id=goal_obj,
        )

        assert state.current_spot_id == spot_id
        assert state.current_coordinate == coord
        assert state.current_destination == dest
        assert state.planned_path == tuple(path)
        assert state.goal_destination_type == "location"
        assert state.goal_spot_id == goal_spot
        assert state.goal_location_area_id == goal_loc
        assert state.goal_world_object_id == goal_obj

    def test_from_parts_with_defaults(self):
        """デフォルト値で構築"""
        state = PlayerNavigationState.from_parts()
        assert state.current_spot_id is None
        assert state.planned_path == ()
        assert state.goal_destination_type is None

    def test_from_parts_with_empty_list_path(self):
        """空リストの経路で構築"""
        state = PlayerNavigationState.from_parts(planned_path=[])
        assert state.planned_path == ()


class TestPlayerNavigationStateWithDestinationSet:
    """with_destination_set のテスト"""

    @pytest.fixture
    def base_state(self) -> PlayerNavigationState:
        return PlayerNavigationState.from_parts(
            current_spot_id=SpotId(1),
            current_coordinate=Coordinate(0, 0, 0),
        )

    def test_sets_destination_and_path(self, base_state: PlayerNavigationState):
        """目的地と経路を設定"""
        dest = Coordinate(5, 5, 0)
        path = [Coordinate(0, 0, 0), Coordinate(1, 1, 0), Coordinate(5, 5, 0)]

        new_state = base_state.with_destination_set(
            destination=dest,
            path=path,
            goal_destination_type="spot",
            goal_spot_id=SpotId(2),
        )

        assert new_state.current_destination == dest
        assert new_state.planned_path == tuple(path)
        assert new_state.goal_destination_type == "spot"
        assert new_state.goal_spot_id == SpotId(2)
        assert new_state.current_spot_id == base_state.current_spot_id
        assert new_state.current_coordinate == base_state.current_coordinate

    def test_with_destination_set_clears_goal_when_none(self, base_state: PlayerNavigationState):
        """goal_* を None で渡すとクリア"""
        dest = Coordinate(3, 3, 0)
        path = [Coordinate(0, 0, 0), Coordinate(3, 3, 0)]
        new_state = base_state.with_destination_set(destination=dest, path=path)
        assert new_state.goal_destination_type is None
        assert new_state.goal_spot_id is None


class TestPlayerNavigationStateCleared:
    """cleared() のテスト"""

    def test_cleared_from_empty_returns_cleared(self):
        """空の状態で cleared しても位置は維持"""
        state = PlayerNavigationState.from_parts(
            current_spot_id=SpotId(1),
            current_coordinate=Coordinate(2, 3, 0),
        )
        cleared = state.cleared()
        assert cleared.current_destination is None
        assert cleared.planned_path == ()
        assert cleared.goal_spot_id is None
        assert cleared.current_spot_id == SpotId(1)
        assert cleared.current_coordinate == Coordinate(2, 3, 0)

    def test_cleared_from_with_destination(self):
        """目的地設定後に cleared で経路・目標のみクリア"""
        state = PlayerNavigationState.from_parts(
            current_spot_id=SpotId(1),
            current_coordinate=Coordinate(0, 0, 0),
        ).with_destination_set(
            destination=Coordinate(5, 5, 0),
            path=[Coordinate(0, 0, 0), Coordinate(5, 5, 0)],
            goal_spot_id=SpotId(2),
        )
        cleared = state.cleared()
        assert cleared.planned_path == ()
        assert cleared.current_destination is None
        assert cleared.goal_spot_id is None
        assert cleared.current_spot_id == SpotId(1)


class TestPlayerNavigationStateAdvanceStep:
    """advance_step() のテスト"""

    def test_advance_step_empty_path_returns_none_and_cleared(self):
        """経路が空のとき (None, cleared) を返す"""
        state = PlayerNavigationState.from_parts(planned_path=[])
        next_coord, new_state = state.advance_step()
        assert next_coord is None
        assert new_state.planned_path == ()

    def test_advance_step_single_element_returns_none_and_cleared(self):
        """経路が1要素のとき (None, cleared) を返す"""
        state = PlayerNavigationState.from_parts(
            planned_path=[Coordinate(0, 0, 0)],
        )
        next_coord, new_state = state.advance_step()
        assert next_coord is None
        assert new_state.planned_path == ()

    def test_advance_step_two_elements_returns_next_and_clears(self):
        """経路が2要素のとき [1] を返し、1要素残るので cleared"""
        c0 = Coordinate(0, 0, 0)
        c1 = Coordinate(1, 0, 0)
        state = PlayerNavigationState.from_parts(planned_path=[c0, c1])
        next_coord, new_state = state.advance_step()
        assert next_coord == c1
        assert new_state.planned_path == ()

    def test_advance_step_three_elements_returns_next_and_shortens_path(self):
        """経路が3要素以上のとき [1] を返し、経路が短くなる"""
        c0 = Coordinate(0, 0, 0)
        c1 = Coordinate(1, 0, 0)
        c2 = Coordinate(2, 0, 0)
        state = PlayerNavigationState.from_parts(planned_path=[c0, c1, c2])
        next_coord, new_state = state.advance_step()
        assert next_coord == c1
        assert new_state.planned_path == (c0, c2)

    def test_advance_step_four_elements(self):
        """経路が4要素のとき複数回 advance 可能"""
        path = [
            Coordinate(0, 0, 0),
            Coordinate(1, 0, 0),
            Coordinate(2, 0, 0),
            Coordinate(3, 0, 0),
        ]
        state = PlayerNavigationState.from_parts(planned_path=path)

        next1, state1 = state.advance_step()
        assert next1 == Coordinate(1, 0, 0)
        assert len(state1.planned_path) == 3

        next2, state2 = state1.advance_step()
        assert next2 == Coordinate(2, 0, 0)
        assert len(state2.planned_path) == 2

        next3, state3 = state2.advance_step()
        assert next3 == Coordinate(3, 0, 0)
        assert state3.planned_path == ()


class TestPlayerNavigationStateWithLocationUpdated:
    """with_location_updated のテスト"""

    def test_updates_spot_and_coordinate(self):
        """現在地を更新"""
        state = PlayerNavigationState.from_parts(
            current_spot_id=SpotId(1),
            current_coordinate=Coordinate(0, 0, 0),
        )
        new_state = state.with_location_updated(
            spot_id=SpotId(2),
            coordinate=Coordinate(5, 10, 0),
        )
        assert new_state.current_spot_id == SpotId(2)
        assert new_state.current_coordinate == Coordinate(5, 10, 0)
        assert state.current_spot_id == SpotId(1)

    def test_with_location_updated_preserves_other_fields(self):
        """経路・目標は維持される"""
        state = PlayerNavigationState.from_parts(
            current_spot_id=SpotId(1),
            current_coordinate=Coordinate(0, 0, 0),
        ).with_destination_set(
            destination=Coordinate(3, 3, 0),
            path=[Coordinate(0, 0, 0), Coordinate(3, 3, 0)],
            goal_spot_id=SpotId(1),
        )
        new_state = state.with_location_updated(
            spot_id=SpotId(1),
            coordinate=Coordinate(1, 1, 0),
        )
        assert new_state.planned_path == state.planned_path
        assert new_state.goal_spot_id == SpotId(1)


class TestPlayerNavigationStatePlannedPathAsList:
    """planned_path_as_list のテスト"""

    def test_returns_copy_as_list(self):
        """List のコピーを返す"""
        path = [Coordinate(0, 0, 0), Coordinate(1, 1, 0)]
        state = PlayerNavigationState.from_parts(planned_path=path)
        result = state.planned_path_as_list()
        assert result == path
        assert result is not state.planned_path
        result.append(Coordinate(2, 2, 0))
        assert len(state.planned_path) == 2
