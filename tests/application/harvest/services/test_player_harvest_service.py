from unittest.mock import MagicMock

from ai_rpg_world.application.harvest.contracts.dtos import HarvestCommandResultDto
from ai_rpg_world.application.harvest.services.player_harvest_service import (
    PlayerHarvestApplicationService,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent, HarvestableComponent
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


def _create_status() -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(1),
        base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp.create(100, 100),
        mp=Mp.create(30, 30),
        stamina=Stamina.create(100, 100),
        current_spot_id=SpotId(1),
        current_coordinate=Coordinate(0, 0, 0),
    )


def test_start_harvest_by_target_turns_actor_and_forwards_command():
    data_store = InMemoryDataStore()

    def create_uow():
        return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)

    unit_of_work, _ = InMemoryUnitOfWork.create_with_event_publisher(
        unit_of_work_factory=create_uow,
        data_store=data_store,
    )
    physical_map_repo = InMemoryPhysicalMapRepository(data_store, unit_of_work)
    player_status_repo = InMemoryPlayerStatusRepository(data_store, unit_of_work)
    player_status_repo.save(_create_status())
    time_provider = InMemoryGameTimeProvider(initial_tick=123)

    physical_map = PhysicalMapAggregate.create(
        SpotId(1),
        [Tile(Coordinate(x, y, 0), TerrainType.grass()) for x in range(3) for y in range(3)],
    )
    physical_map.add_object(
        WorldObject(
            WorldObjectId(1),
            Coordinate(0, 0, 0),
            ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(1)),
        )
    )
    physical_map.add_object(
        WorldObject(
            WorldObjectId(2),
            Coordinate(1, 0, 0),
            ObjectTypeEnum.RESOURCE,
            component=HarvestableComponent(loot_table_id=1, harvest_duration=5, stamina_cost=1),
        )
    )
    physical_map_repo.save(physical_map)

    harvest_command_service = MagicMock()
    harvest_command_service.start_harvest.return_value = HarvestCommandResultDto(
        success=True,
        message="採集を開始しました",
        data={},
    )
    service = PlayerHarvestApplicationService(
        harvest_command_service=harvest_command_service,
        physical_map_repository=physical_map_repo,
        player_status_repository=player_status_repo,
        time_provider=time_provider,
    )

    result = service.start_harvest_by_target(player_id=1, target_world_object_id=2)

    assert result.success is True
    updated_map = physical_map_repo.find_by_spot_id(SpotId(1))
    assert updated_map.get_actor(WorldObjectId(1)).direction == DirectionEnum.EAST
    command = harvest_command_service.start_harvest.call_args[0][0]
    assert command.actor_id == "1"
    assert command.target_id == "2"
    assert command.spot_id == "1"
    assert command.current_tick == 123
