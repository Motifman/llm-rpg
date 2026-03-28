"""Create a minimal SQLite world database for the web viewer."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai_rpg_world.application.world.world_state_sqlite_wiring import (
    attach_world_state_sqlite_repositories,
)
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
    PlayerProfileAggregate,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.enum.player_enum import Role
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.player.value_object.player_navigation_state import (
    PlayerNavigationState,
)
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import (
    StatGrowthFactor,
)
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import (
    PhysicalMapAggregate,
)
from ai_rpg_world.domain.world.entity.gateway import Gateway
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.area import PointArea
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import (
    SqliteUnitOfWorkFactory,
)

DEFAULT_WEB_GAME_DB = Path("var/game/ai_rpg_world.db")


def seed_demo_world_database(
    database: Path | str,
    *,
    overwrite: bool = False,
) -> Path:
    """Create a deterministic demo world database for the web viewer."""

    database_path = Path(database).expanduser().resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if database_path.exists():
        if not overwrite:
            raise FileExistsError(
                f"Demo world database already exists: {database_path}. "
                "Use overwrite=True to recreate it."
            )
        database_path.unlink()

    factory = SqliteUnitOfWorkFactory(database_path)
    with factory.create() as uow:
        world_state = attach_world_state_sqlite_repositories(
            uow.connection,
            event_sink=uow,
        )

        world_state.world_structure.spots.save(
            Spot(SpotId(1), "Starter Town", "A compact town square for viewer testing.")
        )
        world_state.world_structure.spots.save(
            Spot(SpotId(2), "South Gate", "A rainy gate connected to the starter town.")
        )

        exp_table = ExpTable(100, 1.5)
        navigation_state = PlayerNavigationState.from_parts(
            current_spot_id=SpotId(1),
            current_coordinate=Coordinate(0, 0, 0),
        )
        world_state.player_state.player_profiles.save(
            PlayerProfileAggregate.create(
                player_id=PlayerId(1),
                name=PlayerName("Hero"),
                role=Role.CITIZEN,
            )
        )
        world_state.player_state.player_statuses.save(
            PlayerStatusAggregate(
                player_id=PlayerId(1),
                base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
                stat_growth_factor=StatGrowthFactor(
                    1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01
                ),
                exp_table=exp_table,
                growth=Growth(1, 0, exp_table),
                gold=Gold(100),
                hp=Hp.create(100, 100),
                mp=Mp.create(50, 50),
                stamina=Stamina.create(100, 100),
                navigation_state=navigation_state,
            )
        )

        starter_town = PhysicalMapAggregate.create(
            SpotId(1),
            _make_tiles(width=4, height=4),
            objects=[
                WorldObject(
                    object_id=WorldObjectId.create(1),
                    coordinate=Coordinate(0, 0, 0),
                    object_type=ObjectTypeEnum.PLAYER,
                    component=ActorComponent(
                        direction=DirectionEnum.EAST,
                        player_id=PlayerId(1),
                    ),
                )
            ],
            gateways=[
                Gateway(
                    gateway_id=GatewayId(1),
                    name="starter-to-south-gate",
                    area=PointArea(Coordinate(2, 0, 0)),
                    target_spot_id=SpotId(2),
                    landing_coordinate=Coordinate(0, 1, 0),
                )
            ],
        )
        south_gate = PhysicalMapAggregate.create(
            SpotId(2),
            _make_tiles(width=4, height=4),
            gateways=[
                Gateway(
                    gateway_id=GatewayId(2),
                    name="south-gate-to-starter",
                    area=PointArea(Coordinate(0, 1, 0)),
                    target_spot_id=SpotId(1),
                    landing_coordinate=Coordinate(2, 0, 0),
                )
            ],
        )
        south_gate.set_weather(WeatherState(WeatherTypeEnum.RAIN, 0.6))

        world_state.world_runtime.physical_maps.save(starter_town)
        world_state.world_runtime.physical_maps.save(south_gate)

    return database_path


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a minimal SQLite database for the web viewer."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_WEB_GAME_DB,
        help="Output SQLite database path.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Recreate the database if it already exists.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    database_path = seed_demo_world_database(
        args.database,
        overwrite=args.overwrite,
    )
    print(f"Demo web database created at: {database_path}")
    return 0


def _make_tiles(*, width: int, height: int) -> list[Tile]:
    return [
        Tile(Coordinate(x, y, 0), TerrainType.grass())
        for x in range(width)
        for y in range(height)
    ]


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_WEB_GAME_DB",
    "build_argument_parser",
    "main",
    "seed_demo_world_database",
]
