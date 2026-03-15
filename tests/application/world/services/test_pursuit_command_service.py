import pytest

from ai_rpg_world.application.world.contracts.commands import (
    CancelPursuitCommand,
    StartPursuitCommand,
)
from ai_rpg_world.application.world.exceptions.command.pursuit_command_exception import (
    PursuitActorBusyException,
    PursuitActorNotPlacedException,
    PursuitActorObjectNotFoundException,
    PursuitInvalidTargetKindException,
    PursuitSelfTargetException,
    PursuitTargetNotFoundException,
    PursuitTargetNotVisibleException,
)
from ai_rpg_world.application.world.services.gateway_based_connected_spots_provider import (
    GatewayBasedConnectedSpotsProvider,
)
from ai_rpg_world.application.world.services.pursuit_command_service import (
    PursuitCommandService,
)
from ai_rpg_world.application.world.world_query_wiring import create_world_query_service
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
    PlayerProfileAggregate,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.player_navigation_state import (
    PlayerNavigationState,
)
from ai_rpg_world.domain.player.enum.player_enum import Role
from ai_rpg_world.domain.player.event.status_events import PlayerLocationChangedEvent
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import (
    StatGrowthFactor,
)
from ai_rpg_world.domain.pursuit.event.pursuit_events import (
    PursuitCancelledEvent,
    PursuitStartedEvent,
    PursuitUpdatedEvent,
)
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    ChestComponent,
)
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
    InMemoryPlayerProfileRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import (
    InMemorySpotRepository,
)
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


def _make_status(player_id: int, spot_id: int = 1, x: int = 0, y: int = 0) -> PlayerStatusAggregate:
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
        navigation_state=PlayerNavigationState.from_parts(
            current_spot_id=SpotId(spot_id),
            current_coordinate=Coordinate(x, y, 0),
        ),
    )


def _make_profile(player_id: int, name: str) -> PlayerProfileAggregate:
    return PlayerProfileAggregate.create(
        player_id=PlayerId(player_id),
        name=PlayerName(name),
        role=Role.CITIZEN,
    )


def _make_map(spot_id: int, objects: list[WorldObject]) -> PhysicalMapAggregate:
    tiles = {}
    for x in range(6):
        for y in range(6):
            coord = Coordinate(x, y, 0)
            tiles[coord] = Tile(coord, TerrainType.grass())
    return PhysicalMapAggregate(
        spot_id=SpotId(spot_id),
        tiles=tiles,
        objects=objects,
    )


def _make_player_object(player_id: int, x: int, y: int) -> WorldObject:
    return WorldObject(
        object_id=WorldObjectId.create(player_id),
        coordinate=Coordinate(x, y, 0),
        object_type=ObjectTypeEnum.PLAYER,
        component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(player_id)),
    )


def _make_monster_object(object_id: int, x: int, y: int) -> WorldObject:
    return WorldObject(
        object_id=WorldObjectId.create(object_id),
        coordinate=Coordinate(x, y, 0),
        object_type=ObjectTypeEnum.NPC,
        is_blocking=False,
    )


def _make_chest_object(object_id: int, x: int, y: int) -> WorldObject:
    return WorldObject(
        object_id=WorldObjectId.create(object_id),
        coordinate=Coordinate(x, y, 0),
        object_type=ObjectTypeEnum.CHEST,
        is_blocking=False,
        component=ChestComponent(is_open=True, item_ids=[]),
    )


class TestPursuitCommandService:
    @pytest.fixture
    def setup_service(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()

        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)

        unit_of_work, _ = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )

        status_repo = InMemoryPlayerStatusRepository(data_store, unit_of_work)
        profile_repo = InMemoryPlayerProfileRepository(data_store, unit_of_work)
        phys_repo = InMemoryPhysicalMapRepository(data_store, unit_of_work)
        spot_repo = InMemorySpotRepository(data_store, unit_of_work)
        spot_repo.save(Spot(SpotId(1), "Town", "A town"))
        time_provider = InMemoryGameTimeProvider(initial_tick=100)
        world_query_service = create_world_query_service(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            connected_spots_provider=GatewayBasedConnectedSpotsProvider(phys_repo),
            game_time_provider=time_provider,
        )
        service = PursuitCommandService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            world_query_service=world_query_service,
            unit_of_work=unit_of_work,
        )
        return service, status_repo, profile_repo, phys_repo, time_provider

    def test_start_pursuit_to_visible_player_succeeds_and_clears_path(self, setup_service):
        service, status_repo, profile_repo, phys_repo, _ = setup_service
        profile_repo.save(_make_profile(1, "Alice"))
        profile_repo.save(_make_profile(2, "Bob"))
        status = _make_status(1)
        status.set_destination(
            Coordinate(3, 0, 0),
            [Coordinate(0, 0, 0), Coordinate(1, 0, 0), Coordinate(3, 0, 0)],
        )
        status_repo.save(status)
        phys_repo.save(_make_map(1, [_make_player_object(1, 0, 0), _make_player_object(2, 1, 0)]))

        result = service.start_pursuit(StartPursuitCommand(player_id=1, target_world_object_id=2))

        saved = status_repo.find_by_id(PlayerId(1))
        assert result.success is True
        assert "Bob" in result.message
        assert saved is not None
        assert saved.pursuit_state is not None
        assert int(saved.pursuit_state.target_id) == 2
        assert saved.current_destination is None
        assert saved.planned_path == []
        assert any(isinstance(event, PursuitStartedEvent) for event in saved.get_events())

    def test_start_pursuit_to_visible_monster_succeeds(self, setup_service):
        service, status_repo, profile_repo, phys_repo, _ = setup_service
        profile_repo.save(_make_profile(1, "Alice"))
        status_repo.save(_make_status(1))
        phys_repo.save(_make_map(1, [_make_player_object(1, 0, 0), _make_monster_object(200, 1, 0)]))

        result = service.start_pursuit(StartPursuitCommand(player_id=1, target_world_object_id=200))

        saved = status_repo.find_by_id(PlayerId(1))
        assert result.success is True
        assert saved is not None and saved.pursuit_state is not None
        assert int(saved.pursuit_state.target_id) == 200

    def test_start_pursuit_missing_target_raises(self, setup_service):
        service, status_repo, profile_repo, phys_repo, _ = setup_service
        profile_repo.save(_make_profile(1, "Alice"))
        status_repo.save(_make_status(1))
        phys_repo.save(_make_map(1, [_make_player_object(1, 0, 0)]))

        with pytest.raises(PursuitTargetNotFoundException):
            service.start_pursuit(StartPursuitCommand(player_id=1, target_world_object_id=999))

    def test_start_pursuit_invisible_target_raises(self, setup_service):
        service, status_repo, profile_repo, phys_repo, _ = setup_service
        profile_repo.save(_make_profile(1, "Alice"))
        profile_repo.save(_make_profile(2, "Bob"))
        status_repo.save(_make_status(1))
        physical_map = _make_map(1, [_make_player_object(1, 0, 0), _make_player_object(2, 2, 0)])
        physical_map.change_tile_terrain(Coordinate(1, 0, 0), TerrainType.wall())
        phys_repo.save(physical_map)

        with pytest.raises(PursuitTargetNotVisibleException):
            service.start_pursuit(StartPursuitCommand(player_id=1, target_world_object_id=2))

    def test_start_pursuit_invalid_target_kind_raises(self, setup_service):
        service, status_repo, profile_repo, phys_repo, _ = setup_service
        profile_repo.save(_make_profile(1, "Alice"))
        status_repo.save(_make_status(1))
        phys_repo.save(_make_map(1, [_make_player_object(1, 0, 0), _make_chest_object(200, 1, 0)]))

        with pytest.raises(PursuitInvalidTargetKindException):
            service.start_pursuit(StartPursuitCommand(player_id=1, target_world_object_id=200))

    def test_start_pursuit_self_target_raises(self, setup_service):
        service, status_repo, profile_repo, phys_repo, _ = setup_service
        profile_repo.save(_make_profile(1, "Alice"))
        status_repo.save(_make_status(1))
        phys_repo.save(_make_map(1, [_make_player_object(1, 0, 0)]))

        with pytest.raises(PursuitSelfTargetException):
            service.start_pursuit(StartPursuitCommand(player_id=1, target_world_object_id=1))

    def test_start_pursuit_without_placement_raises(self, setup_service):
        service, status_repo, profile_repo, phys_repo, _ = setup_service
        profile_repo.save(_make_profile(1, "Alice"))
        status = _make_status(1)
        status.update_location(SpotId(1), Coordinate(0, 0, 0))
        status_repo.save(
            PlayerStatusAggregate(
                player_id=status.player_id,
                base_stats=status.base_stats,
                stat_growth_factor=status.stat_growth_factor,
                exp_table=status.exp_table,
                growth=status.growth,
                gold=status.gold,
                hp=status.hp,
                mp=status.mp,
                stamina=status.stamina,
            )
        )
        phys_repo.save(_make_map(1, [_make_player_object(1, 0, 0)]))

        with pytest.raises(PursuitActorNotPlacedException):
            service.start_pursuit(StartPursuitCommand(player_id=1, target_world_object_id=2))

    def test_start_pursuit_busy_actor_raises(self, setup_service):
        service, status_repo, profile_repo, phys_repo, time_provider = setup_service
        profile_repo.save(_make_profile(1, "Alice"))
        profile_repo.save(_make_profile(2, "Bob"))
        status_repo.save(_make_status(1))
        actor = _make_player_object(1, 0, 0)
        actor.set_busy(time_provider.get_current_tick().add_duration(5))
        phys_repo.save(_make_map(1, [actor, _make_player_object(2, 1, 0)]))

        with pytest.raises(PursuitActorBusyException):
            service.start_pursuit(StartPursuitCommand(player_id=1, target_world_object_id=2))

    def test_start_pursuit_missing_actor_object_raises(self, setup_service):
        service, status_repo, profile_repo, phys_repo, _ = setup_service
        profile_repo.save(_make_profile(1, "Alice"))
        profile_repo.save(_make_profile(2, "Bob"))
        status_repo.save(_make_status(1))
        phys_repo.save(_make_map(1, [_make_player_object(2, 1, 0)]))

        with pytest.raises(PursuitActorObjectNotFoundException):
            service.start_pursuit(StartPursuitCommand(player_id=1, target_world_object_id=2))

    def test_start_same_target_refreshes(self, setup_service):
        service, status_repo, profile_repo, phys_repo, _ = setup_service
        profile_repo.save(_make_profile(1, "Alice"))
        profile_repo.save(_make_profile(2, "Bob"))
        status_repo.save(_make_status(1))
        phys_repo.save(_make_map(1, [_make_player_object(1, 0, 0), _make_player_object(2, 1, 0)]))

        service.start_pursuit(StartPursuitCommand(player_id=1, target_world_object_id=2))
        phys_repo.save(_make_map(1, [_make_player_object(1, 0, 0), _make_player_object(2, 2, 0)]))

        result = service.start_pursuit(StartPursuitCommand(player_id=1, target_world_object_id=2))

        saved = status_repo.find_by_id(PlayerId(1))
        assert result.success is True
        assert saved is not None and saved.pursuit_state is not None
        assert saved.pursuit_state.target_snapshot.coordinate == Coordinate(2, 0, 0)
        assert any(isinstance(event, PursuitUpdatedEvent) for event in saved.get_events())

    def test_start_same_target_without_meaningful_change_is_noop(self, setup_service):
        service, status_repo, profile_repo, phys_repo, _ = setup_service
        profile_repo.save(_make_profile(1, "Alice"))
        profile_repo.save(_make_profile(2, "Bob"))
        status_repo.save(_make_status(1))
        phys_repo.save(_make_map(1, [_make_player_object(1, 0, 0), _make_player_object(2, 1, 0)]))

        service.start_pursuit(StartPursuitCommand(player_id=1, target_world_object_id=2))
        saved_before = status_repo.find_by_id(PlayerId(1))
        assert saved_before is not None
        saved_before.clear_events()

        result = service.start_pursuit(StartPursuitCommand(player_id=1, target_world_object_id=2))

        saved_after = status_repo.find_by_id(PlayerId(1))
        assert result.success is True
        assert result.no_op is True
        assert saved_after is not None and saved_after.pursuit_state is not None
        assert saved_after.pursuit_state.target_snapshot.coordinate == Coordinate(1, 0, 0)
        assert not any(isinstance(event, PursuitUpdatedEvent) for event in saved_after.get_events())
        assert not any(isinstance(event, PursuitCancelledEvent) for event in saved_after.get_events())

    def test_start_different_target_switches(self, setup_service):
        service, status_repo, profile_repo, phys_repo, _ = setup_service
        profile_repo.save(_make_profile(1, "Alice"))
        profile_repo.save(_make_profile(2, "Bob"))
        profile_repo.save(_make_profile(3, "Carol"))
        status_repo.save(_make_status(1))
        phys_repo.save(
            _make_map(
                1,
                [
                    _make_player_object(1, 0, 0),
                    _make_player_object(2, 1, 0),
                    _make_player_object(3, 1, 1),
                ],
            )
        )

        service.start_pursuit(StartPursuitCommand(player_id=1, target_world_object_id=2))
        result = service.start_pursuit(StartPursuitCommand(player_id=1, target_world_object_id=3))

        saved = status_repo.find_by_id(PlayerId(1))
        assert result.success is True
        assert "Carol" in result.message
        assert saved is not None and saved.pursuit_state is not None
        assert int(saved.pursuit_state.target_id) == 3
        assert any(isinstance(event, PursuitCancelledEvent) for event in saved.get_events())

    def test_cancel_pursuit_active_clears_state_and_path(self, setup_service):
        service, status_repo, profile_repo, phys_repo, _ = setup_service
        profile_repo.save(_make_profile(1, "Alice"))
        profile_repo.save(_make_profile(2, "Bob"))
        status = _make_status(1)
        status.set_destination(
            Coordinate(3, 0, 0),
            [Coordinate(0, 0, 0), Coordinate(1, 0, 0), Coordinate(3, 0, 0)],
        )
        status_repo.save(status)
        phys_repo.save(_make_map(1, [_make_player_object(1, 0, 0), _make_player_object(2, 1, 0)]))
        service.start_pursuit(StartPursuitCommand(player_id=1, target_world_object_id=2))

        result = service.cancel_pursuit(CancelPursuitCommand(player_id=1))

        saved = status_repo.find_by_id(PlayerId(1))
        assert result.success is True
        assert saved is not None
        assert saved.pursuit_state is None
        assert saved.current_destination is None
        assert saved.planned_path == []
        assert any(isinstance(event, PursuitCancelledEvent) for event in saved.get_events())

    def test_cancel_pursuit_without_active_pursuit_is_noop(self, setup_service):
        service, status_repo, profile_repo, phys_repo, _ = setup_service
        profile_repo.save(_make_profile(1, "Alice"))
        status = _make_status(1)
        status.set_destination(
            Coordinate(3, 0, 0),
            [Coordinate(0, 0, 0), Coordinate(1, 0, 0), Coordinate(3, 0, 0)],
        )
        status_repo.save(status)
        phys_repo.save(_make_map(1, [_make_player_object(1, 0, 0)]))

        result = service.cancel_pursuit(CancelPursuitCommand(player_id=1))

        saved = status_repo.find_by_id(PlayerId(1))
        assert result.success is True
        assert result.no_op is True
        assert saved is not None
        assert saved.current_destination == Coordinate(3, 0, 0)
        assert saved.planned_path != []
