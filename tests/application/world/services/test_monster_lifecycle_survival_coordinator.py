import unittest.mock as mock

from ai_rpg_world.application.world.services.hunger_migration_policy import (
    HungerMigrationCandidate,
)
from ai_rpg_world.application.world.services.monster_lifecycle_survival_coordinator import (
    MonsterLifecycleSurvivalCoordinator,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestMonsterLifecycleSurvivalCoordinator:
    def test_processes_starvation_and_old_age_before_behavior_and_returns_blocked_actor_ids(self):
        starving = mock.Mock()
        starving.world_object_id = WorldObjectId(1)
        starving.coordinate = Coordinate(1, 1, 0)
        starving.tick_hunger.return_value = True
        starving.die_from_old_age.return_value = False
        old = mock.Mock()
        old.world_object_id = WorldObjectId(2)
        old.coordinate = Coordinate(2, 2, 0)
        old.tick_hunger.return_value = False
        old.die_from_old_age.return_value = True
        active = mock.Mock()
        active.world_object_id = WorldObjectId(3)
        active.coordinate = Coordinate(3, 3, 0)
        active.tick_hunger.return_value = False
        active.die_from_old_age.return_value = False
        monster_repository = mock.Mock()
        monster_repository.find_by_spot_id.return_value = [starving, old, active]
        coordinator = MonsterLifecycleSurvivalCoordinator(
            monster_repository=monster_repository,
            physical_map_repository=mock.Mock(),
            connected_spots_provider_getter=lambda: None,
            map_transition_service_getter=lambda: None,
            hunger_migration_policy=mock.Mock(),
            spot_has_feed_for_monster=lambda *args, **kwargs: False,
            unit_of_work=mock.Mock(),
            logger=mock.Mock(),
        )
        physical_map = mock.Mock()
        physical_map.spot_id = SpotId(1)

        blocked_actor_ids = coordinator.process_survival_for_spot(
            physical_map,
            WorldTick(10),
        )

        assert blocked_actor_ids == {WorldObjectId(1), WorldObjectId(2)}
        starving.starve.assert_called_once_with(WorldTick(10))
        old.die_from_old_age.assert_called_once_with(WorldTick(10))
        active.tick_hunger.assert_called_once_with(WorldTick(10))

    def test_migration_apply_uses_policy_selected_migrant_only(self):
        migrant = mock.Mock()
        migrant.monster_id = MonsterId(1)
        migrant.world_object_id = WorldObjectId(101)
        migrant.hunger = 0.9
        migrant.coordinate = Coordinate(2, 2, 0)
        migrant.template.forage_threshold = 0.5
        migrant.template.preferred_feed_item_spec_ids = [1]
        migrant.tick_hunger.return_value = False
        migrant.die_from_old_age.return_value = False
        other = mock.Mock()
        other.monster_id = MonsterId(2)
        other.world_object_id = WorldObjectId(102)
        other.hunger = 0.7
        other.coordinate = Coordinate(1, 1, 0)
        other.template.forage_threshold = 0.5
        other.template.preferred_feed_item_spec_ids = [1]
        other.tick_hunger.return_value = False
        other.die_from_old_age.return_value = False
        monster_repository = mock.Mock()
        monster_repository.find_by_spot_id.return_value = [migrant, other]
        monster_repository.find_by_world_object_id.return_value = migrant
        physical_map_repository = mock.Mock()
        target_map = mock.Mock()
        physical_map_repository.find_by_spot_id.return_value = target_map
        provider = mock.Mock()
        provider.get_connected_spots.return_value = [SpotId(2)]
        transition_service = mock.Mock()
        policy = mock.Mock()
        policy.select_migrant.return_value = HungerMigrationCandidate(
            monster_id=MonsterId(1),
            world_object_id=WorldObjectId(101),
            hunger=0.9,
            forage_threshold=0.5,
            has_preferred_feed=True,
            spot_has_feed=False,
        )
        coordinator = MonsterLifecycleSurvivalCoordinator(
            monster_repository=monster_repository,
            physical_map_repository=physical_map_repository,
            connected_spots_provider_getter=lambda: provider,
            map_transition_service_getter=lambda: transition_service,
            hunger_migration_policy=policy,
            spot_has_feed_for_monster=lambda *args, **kwargs: False,
            unit_of_work=mock.Mock(),
            logger=mock.Mock(),
        )
        gateway = mock.Mock(
            target_spot_id=SpotId(2),
            landing_coordinate=Coordinate(0, 0, 0),
        )
        physical_map = mock.Mock()
        physical_map.spot_id = SpotId(1)
        physical_map.get_all_gateways.return_value = [gateway]

        blocked_actor_ids = coordinator.process_survival_for_spot(
            physical_map,
            WorldTick(10),
        )

        assert blocked_actor_ids == {WorldObjectId(101)}
        policy.select_migrant.assert_called_once()
        transition_service.transition_object.assert_called_once_with(
            physical_map,
            target_map,
            WorldObjectId(101),
            Coordinate(0, 0, 0),
        )
