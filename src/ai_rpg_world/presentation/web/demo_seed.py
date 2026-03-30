"""Create a minimal SQLite world database for the web viewer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_rpg_world.application.ui.contracts.dtos import ImportedSceneBundleDto
from ai_rpg_world.application.ui.services.tiled_scene_importer import TiledSceneImporter
from ai_rpg_world.application.world.world_state_sqlite_wiring import (
    attach_world_state_sqlite_repositories,
)
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
    PlayerProfileAggregate,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.enum.player_enum import Race, Role
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
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import (
    SkillLoadoutAggregate,
)
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import (
    BehaviorStateEnum,
    EcologyTypeEnum,
    MonsterFactionEnum,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_behavior_state import (
    MonsterBehaviorState,
)
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import (
    MonsterTemplateId,
)
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import (
    PhysicalMapAggregate,
)
from ai_rpg_world.domain.world.entity.gateway import Gateway
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    AutonomousBehaviorComponent,
    ChestComponent,
)
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.value_object.area import PointArea
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import (
    SqliteUnitOfWorkFactory,
)

DEFAULT_WEB_GAME_DB = Path("var/game/ai_rpg_world.db")
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_TILED_MAP_DIR = REPO_ROOT / "frontend" / "public" / "data" / "maps"
CHEST_COORDINATE = Coordinate(4, 5, 0)
MONSTER_START_COORDINATE = Coordinate(12, 11, 0)
PLAYER_START_COORDINATE = Coordinate(2, 13, 0)


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
            current_coordinate=PLAYER_START_COORDINATE,
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
                stamina=Stamina.create(1_000_000, 1_000_000),
                navigation_state=navigation_state,
            )
        )

        starter_bundle = _load_tiled_scene_bundle(
            spot_id=1,
            map_filename="spot_1.json",
            map_asset_key="spot_1",
        )
        south_gate_bundle = _load_tiled_scene_bundle(
            spot_id=2,
            map_filename="spot_2.json",
            map_asset_key="spot_2",
        )

        starter_town = PhysicalMapAggregate.create(
            SpotId(1),
            _build_tiles_from_imported_bundle(starter_bundle),
            objects=[
                WorldObject(
                    object_id=WorldObjectId.create(1),
                    coordinate=PLAYER_START_COORDINATE,
                    object_type=ObjectTypeEnum.PLAYER,
                    component=ActorComponent(
                        direction=DirectionEnum.EAST,
                        player_id=PlayerId(1),
                    ),
                ),
                WorldObject(
                    object_id=WorldObjectId.create(10_001),
                    coordinate=CHEST_COORDINATE,
                    object_type=ObjectTypeEnum.CHEST,
                    is_blocking=True,
                    component=ChestComponent(is_open=False),
                ),
                WorldObject(
                    object_id=WorldObjectId.create(20_001),
                    coordinate=MONSTER_START_COORDINATE,
                    object_type=ObjectTypeEnum.NPC,
                    component=AutonomousBehaviorComponent(
                        direction=DirectionEnum.WEST,
                        capability=MovementCapability.normal_walk().with_speed_modifier(0.5),
                        vision_range=5,
                        fov_angle=140.0,
                        patrol_points=[
                            Coordinate(12, 11, 0),
                            Coordinate(13, 11, 0),
                            Coordinate(13, 12, 0),
                            Coordinate(12, 12, 0),
                        ],
                        race="slime",
                        faction="enemy",
                        initial_position=MONSTER_START_COORDINATE,
                        random_move_chance=0.0,
                        ecology_type=EcologyTypeEnum.TERRITORIAL,
                        territory_radius=6,
                        prey_races={"human"},
                    ),
                ),
            ],
            gateways=_build_gateways_from_imported_bundle(starter_bundle),
        )
        south_gate = PhysicalMapAggregate.create(
            SpotId(2),
            _build_tiles_from_imported_bundle(south_gate_bundle),
            gateways=_build_gateways_from_imported_bundle(south_gate_bundle),
        )
        south_gate.set_weather(WeatherState(WeatherTypeEnum.RAIN, 0.6))

        slime_template = MonsterTemplate(
            template_id=MonsterTemplateId(1),
            name="Slime",
            base_stats=BaseStats(30, 0, 6, 6, 6, 0.02, 0.02),
            reward_info=RewardInfo(0, 0),
            respawn_info=RespawnInfo(200, True),
            race=Race.BEAST,
            faction=MonsterFactionEnum.ENEMY,
            description="A cautious demo slime that patrols and chases nearby players.",
            skill_ids=[],
            vision_range=5,
        )
        slime_loadout = SkillLoadoutAggregate.create(
            SkillLoadoutId(1),
            20_001,
            4,
            4,
        )
        slime = MonsterAggregate.reconstitute(
            MonsterId(1),
            slime_template,
            WorldObjectId.create(20_001),
            slime_loadout,
            MONSTER_START_COORDINATE,
            SpotId(1),
            WorldTick(0),
            behavior_state=MonsterBehaviorState.from_parts(
                state=BehaviorStateEnum.PATROL,
                target_id=None,
                last_known_position=None,
                initial_position=MONSTER_START_COORDINATE,
            ),
        )

        world_state.world_runtime.physical_maps.save(starter_town)
        world_state.world_runtime.physical_maps.save(south_gate)
        world_state.world_runtime.monsters.save(slime)

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


def _load_tiled_scene_bundle(
    *,
    spot_id: int,
    map_filename: str,
    map_asset_key: str,
) -> ImportedSceneBundleDto:
    tiled_map_path = DEFAULT_TILED_MAP_DIR / map_filename
    if not tiled_map_path.exists():
        raise FileNotFoundError(f"Tiled map not found: {tiled_map_path}")
    payload = json.loads(tiled_map_path.read_text(encoding="utf-8"))
    importer = TiledSceneImporter()
    return importer.import_map(
        payload,
        tiled_map_path=f"data/maps/{map_filename}",
        spot_id=spot_id,
        map_asset_key=map_asset_key,
    )


def _build_tiles_from_imported_bundle(bundle: ImportedSceneBundleDto) -> list[Tile]:
    scene_map = bundle.scene_map
    collision_grid = bundle.collision_grid
    tiles: list[Tile] = []
    for y in range(scene_map.map_height_tiles):
        for x in range(scene_map.map_width_tiles):
            terrain_name = None
            if collision_grid.terrain_rows:
                terrain_name = collision_grid.terrain_rows[y][x]
            is_passable = collision_grid.passable_rows[y][x]
            terrain = _terrain_from_imported_cell(terrain_name=terrain_name, is_passable=is_passable)
            tiles.append(Tile(Coordinate(x, y, 0), terrain))
    return tiles


def _terrain_from_imported_cell(*, terrain_name: str | None, is_passable: bool) -> TerrainType:
    if not is_passable:
        return TerrainType.wall()
    if terrain_name == "road":
        return TerrainType.road()
    if terrain_name == "bush":
        return TerrainType.bush()
    if terrain_name == "swamp":
        return TerrainType.swamp()
    if terrain_name == "water":
        return TerrainType.water()
    return TerrainType.grass()


def _build_gateways_from_imported_bundle(bundle: ImportedSceneBundleDto) -> list[Gateway]:
    gateways: list[Gateway] = []
    for dto in bundle.gateways:
        gateways.append(
            Gateway(
                gateway_id=GatewayId(dto.gateway_id),
                name=f"gateway-{dto.gateway_id}",
                area=PointArea(Coordinate(dto.tile_x, dto.tile_y, 0)),
                target_spot_id=SpotId(dto.target_spot_id),
                landing_coordinate=Coordinate(dto.landing_tile_x, dto.landing_tile_y, 0),
            )
        )
    return gateways


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_WEB_GAME_DB",
    "build_argument_parser",
    "main",
    "seed_demo_world_database",
]
