"""MoveResultAssembler の単体テスト。正常ケース・例外ケース・境界ケースを網羅する。"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.world.services.move_result_assembler import MoveResultAssembler
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_navigation_state import PlayerNavigationState
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.player.enum.player_enum import Role
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    PlayerNotFoundException,
    MapNotFoundException,
)


def _create_minimal_player_status(
    player_id: int = 1,
    spot_id: int = 1,
    x: int = 0,
    y: int = 0,
    navigation_state: PlayerNavigationState | None = None,
):
    nav = navigation_state or PlayerNavigationState.from_parts(
        current_spot_id=SpotId(spot_id),
        current_coordinate=Coordinate(x, y, 0),
    )
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(1000),
        hp=Hp.create(100, 100),
        mp=Mp.create(50, 50),
        stamina=Stamina.create(100, 100),
        navigation_state=nav,
    )


def _create_minimal_profile(player_id: int = 1, name: str = "TestPlayer"):
    return PlayerProfileAggregate.create(
        player_id=PlayerId(player_id),
        name=PlayerName(name),
        role=Role.CITIZEN,
    )


class TestCreateSuccess:
    """create_success のテスト"""

    class TestSuccessCases:
        def test_creates_success_dto_with_all_fields(
            self,
        ):
            profile_repo = MagicMock()
            profile_repo.find_by_id.return_value = _create_minimal_profile(1, "Alice")
            spot_repo = MagicMock()
            spot_repo.find_by_id.side_effect = lambda sid: (
                Spot(SpotId(1), "Village", "") if int(sid) == 1 else None
            )
            assembler = MoveResultAssembler(profile_repo, spot_repo)
            status = _create_minimal_player_status(1, 1, 1, 2)

            result = assembler.create_success(
                status,
                SpotId(1),
                Coordinate(1, 1, 0),
                Coordinate(1, 2, 0),
                arrival_tick=150,
                message="移動しました",
            )

            assert result.success is True
            assert result.player_id == 1
            assert result.player_name == "Alice"
            assert result.from_spot_id == 1
            assert result.from_spot_name == "Village"
            assert result.to_spot_id == 1
            assert result.to_spot_name == "Village"
            assert result.from_coordinate == {"x": 1, "y": 1, "z": 0}
            assert result.to_coordinate == {"x": 1, "y": 2, "z": 0}
            assert result.busy_until_tick == 150
            assert result.message == "移動しました"
            assert result.error_message is None

        def test_creates_success_dto_when_from_and_to_spot_differ(
            self,
        ):
            profile_repo = MagicMock()
            profile_repo.find_by_id.return_value = _create_minimal_profile(1, "Bob")
            spot_repo = MagicMock()
            spot_repo.find_by_id.side_effect = lambda sid: {
                1: Spot(SpotId(1), "Start", ""),
                2: Spot(SpotId(2), "Goal", ""),
            }.get(int(sid))
            assembler = MoveResultAssembler(profile_repo, spot_repo)
            status = _create_minimal_player_status(1, 2, 0, 0)

            result = assembler.create_success(
                status,
                SpotId(1),
                Coordinate(5, 5, 0),
                Coordinate(0, 0, 0),
                arrival_tick=200,
                message="マップを移動しました",
            )

            assert result.success is True
            assert result.from_spot_id == 1
            assert result.from_spot_name == "Start"
            assert result.to_spot_id == 2
            assert result.to_spot_name == "Goal"

    class TestExceptionCases:
        def test_raises_player_not_found_when_profile_missing(
            self,
        ):
            profile_repo = MagicMock()
            profile_repo.find_by_id.return_value = None
            spot_repo = MagicMock()
            assembler = MoveResultAssembler(profile_repo, spot_repo)
            status = _create_minimal_player_status(1, 1)

            with pytest.raises(PlayerNotFoundException):
                assembler.create_success(
                    status,
                    SpotId(1),
                    Coordinate(0, 0, 0),
                    Coordinate(1, 0, 0),
                    100,
                    "msg",
                )

        def test_raises_map_not_found_when_from_spot_missing(
            self,
        ):
            profile_repo = MagicMock()
            profile_repo.find_by_id.return_value = _create_minimal_profile(1)
            spot_repo = MagicMock()
            spot_repo.find_by_id.side_effect = lambda sid: None
            assembler = MoveResultAssembler(profile_repo, spot_repo)
            status = _create_minimal_player_status(1, 1)

            with pytest.raises(MapNotFoundException):
                assembler.create_success(
                    status,
                    SpotId(1),
                    Coordinate(0, 0, 0),
                    Coordinate(1, 0, 0),
                    100,
                    "msg",
                )

        def test_raises_map_not_found_when_to_spot_missing(
            self,
        ):
            profile_repo = MagicMock()
            profile_repo.find_by_id.return_value = _create_minimal_profile(1)
            spot_repo = MagicMock()
            spot_repo.find_by_id.side_effect = lambda sid: (
                Spot(SpotId(1), "Village", "") if int(sid) == 1 else None
            )
            assembler = MoveResultAssembler(profile_repo, spot_repo)
            status = _create_minimal_player_status(
                1, 2, 0, 0
            )

            with pytest.raises(MapNotFoundException):
                assembler.create_success(
                    status,
                    SpotId(1),
                    Coordinate(0, 0, 0),
                    Coordinate(1, 0, 0),
                    100,
                    "msg",
                )


class TestCreateFailure:
    """create_failure のテスト"""

    class TestSuccessCases:
        def test_creates_failure_dto_with_player_status(
            self,
        ):
            profile_repo = MagicMock()
            profile_repo.find_by_id.return_value = _create_minimal_profile(1, "Charlie")
            spot_repo = MagicMock()
            spot_repo.find_by_id.return_value = Spot(SpotId(1), "Town", "")
            assembler = MoveResultAssembler(profile_repo, spot_repo)
            status = _create_minimal_player_status(1, 1, 3, 4)

            result = assembler.create_failure(
                1,
                "経路がブロックされています",
                player_status=status,
            )

            assert result.success is False
            assert result.player_id == 1
            assert result.player_name == "Charlie"
            assert result.from_spot_id == 1
            assert result.from_spot_name == "Town"
            assert result.to_spot_id == 1
            assert result.to_spot_name == "Town"
            assert result.from_coordinate == {"x": 3, "y": 4, "z": 0}
            assert result.to_coordinate == {"x": 3, "y": 4, "z": 0}
            assert result.busy_until_tick == 0
            assert result.message == "移動失敗"
            assert result.error_message == "経路がブロックされています"

        def test_creates_failure_dto_without_player_status(
            self,
        ):
            profile_repo = MagicMock()
            spot_repo = MagicMock()
            assembler = MoveResultAssembler(profile_repo, spot_repo)

            result = assembler.create_failure(99, "プレイヤーが見つかりません")

            assert result.success is False
            assert result.player_id == 99
            assert result.player_name == ""
            assert result.from_spot_id == 0
            assert result.from_spot_name == ""
            assert result.to_spot_id == 0
            assert result.to_spot_name == ""
            assert result.from_coordinate == {"x": 0, "y": 0, "z": 0}
            assert result.to_coordinate == {"x": 0, "y": 0, "z": 0}
            assert result.error_message == "プレイヤーが見つかりません"
            profile_repo.find_by_id.assert_not_called()
            spot_repo.find_by_id.assert_not_called()

        def test_creates_failure_dto_when_profile_missing_uses_empty_name(
            self,
        ):
            profile_repo = MagicMock()
            profile_repo.find_by_id.return_value = None
            spot_repo = MagicMock()
            spot_repo.find_by_id.return_value = Spot(SpotId(1), "Place", "")
            assembler = MoveResultAssembler(profile_repo, spot_repo)
            status = _create_minimal_player_status(1, 1)

            result = assembler.create_failure(1, "エラー", player_status=status)

            assert result.success is False
            assert result.player_name == ""
            assert result.from_spot_name == "Place"

        def test_creates_failure_dto_when_spot_missing_uses_empty_names(
            self,
        ):
            profile_repo = MagicMock()
            profile_repo.find_by_id.return_value = _create_minimal_profile(1)
            spot_repo = MagicMock()
            spot_repo.find_by_id.return_value = None
            assembler = MoveResultAssembler(profile_repo, spot_repo)
            status = _create_minimal_player_status(1, 1)

            result = assembler.create_failure(1, "エラー", player_status=status)

            assert result.success is False
            assert result.player_name == "TestPlayer"
            assert result.from_spot_name == ""
            assert result.to_spot_name == ""

        def test_creates_failure_dto_when_current_coordinate_is_none(
            self,
        ):
            profile_repo = MagicMock()
            profile_repo.find_by_id.return_value = _create_minimal_profile(1)
            spot_repo = MagicMock()
            spot_repo.find_by_id.return_value = Spot(SpotId(1), "A", "")
            assembler = MoveResultAssembler(profile_repo, spot_repo)
            status = _create_minimal_player_status(
                1, 1,
                navigation_state=PlayerNavigationState.from_parts(
                    current_spot_id=SpotId(1),
                    current_coordinate=None,
                ),
            )

            result = assembler.create_failure(1, "座標不明", player_status=status)

            assert result.success is False
            assert result.from_coordinate == {"x": 0, "y": 0, "z": 0}
            assert result.to_coordinate == {"x": 0, "y": 0, "z": 0}
