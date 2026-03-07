import pytest

from ai_rpg_world.application.world.contracts.commands import InteractWorldObjectCommand
from ai_rpg_world.application.world.exceptions.command.interaction_command_exception import (
    InteractionTargetNotFoundException,
)
from ai_rpg_world.application.world.services.interaction_command_service import (
    InteractionCommandService,
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
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent, ChestComponent
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


def _create_status(player_id: int, spot_id: int, coord: Coordinate) -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp.create(100, 100),
        mp=Mp.create(30, 30),
        stamina=Stamina.create(100, 100),
        current_spot_id=SpotId(spot_id),
        current_coordinate=coord,
    )


def _create_map() -> PhysicalMapAggregate:
    tiles = [
        Tile(Coordinate(x, y, 0), TerrainType.grass())
        for x in range(3)
        for y in range(3)
    ]
    return PhysicalMapAggregate.create(SpotId(1), tiles)


class TestInteractionCommandService:
    @pytest.fixture
    def setup_service(self):
        data_store = InMemoryDataStore()

        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)

        unit_of_work, _ = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )
        physical_map_repo = InMemoryPhysicalMapRepository(data_store, unit_of_work)
        player_status_repo = InMemoryPlayerStatusRepository(data_store, unit_of_work)
        time_provider = InMemoryGameTimeProvider(initial_tick=100)
        service = InteractionCommandService(
            physical_map_repository=physical_map_repo,
            player_status_repository=player_status_repo,
            time_provider=time_provider,
            unit_of_work=unit_of_work,
        )
        return service, physical_map_repo, player_status_repo

    def test_interact_world_object_turns_actor_and_toggles_chest(self, setup_service):
        service, physical_map_repo, player_status_repo = setup_service
        player_status_repo.save(_create_status(1, 1, Coordinate(0, 0, 0)))

        physical_map = _create_map()
        actor = WorldObject(
            WorldObjectId(1),
            Coordinate(0, 0, 0),
            ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(1)),
        )
        chest = WorldObject(
            WorldObjectId(2),
            Coordinate(1, 0, 0),
            ObjectTypeEnum.CHEST,
            component=ChestComponent(is_open=False),
        )
        physical_map.add_object(actor)
        physical_map.add_object(chest)
        physical_map_repo.save(physical_map)

        service.interact_world_object(
            InteractWorldObjectCommand(player_id=1, target_world_object_id=2)
        )

        updated_map = physical_map_repo.find_by_spot_id(SpotId(1))
        updated_actor = updated_map.get_actor(WorldObjectId(1))
        updated_chest = updated_map.get_object(WorldObjectId(2))
        assert updated_actor.direction == DirectionEnum.EAST
        assert updated_chest.component.is_open is True

    def test_interact_world_object_target_not_found_raises(self, setup_service):
        service, physical_map_repo, player_status_repo = setup_service
        player_status_repo.save(_create_status(1, 1, Coordinate(0, 0, 0)))
        physical_map = _create_map()
        physical_map.add_object(
            WorldObject(
                WorldObjectId(1),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(1)),
            )
        )
        physical_map_repo.save(physical_map)

        with pytest.raises(InteractionTargetNotFoundException):
            service.interact_world_object(
                InteractWorldObjectCommand(player_id=1, target_world_object_id=999)
            )
