from ai_rpg_world.application.world.services.hunger_migration_policy import (
    HungerMigrationCandidate,
    HungerMigrationPolicy,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestHungerMigrationPolicy:
    def test_selects_single_highest_hunger_candidate_and_keeps_input_order_on_tie(self):
        policy = HungerMigrationPolicy()
        first = HungerMigrationCandidate(
            monster_id=MonsterId(1),
            world_object_id=WorldObjectId(101),
            hunger=0.9,
            forage_threshold=0.5,
            has_preferred_feed=True,
            spot_has_feed=False,
        )
        second = HungerMigrationCandidate(
            monster_id=MonsterId(2),
            world_object_id=WorldObjectId(102),
            hunger=0.9,
            forage_threshold=0.5,
            has_preferred_feed=True,
            spot_has_feed=False,
        )

        selected = policy.select_migrant([first, second])

        assert selected is first

    def test_ignores_candidates_without_feed_preference_below_threshold_or_when_spot_has_feed(self):
        policy = HungerMigrationPolicy()
        ineligible = [
            HungerMigrationCandidate(
                monster_id=MonsterId(1),
                world_object_id=WorldObjectId(101),
                hunger=0.8,
                forage_threshold=0.5,
                has_preferred_feed=False,
                spot_has_feed=False,
            ),
            HungerMigrationCandidate(
                monster_id=MonsterId(2),
                world_object_id=WorldObjectId(102),
                hunger=0.4,
                forage_threshold=0.5,
                has_preferred_feed=True,
                spot_has_feed=False,
            ),
            HungerMigrationCandidate(
                monster_id=MonsterId(3),
                world_object_id=WorldObjectId(103),
                hunger=0.95,
                forage_threshold=0.5,
                has_preferred_feed=True,
                spot_has_feed=True,
            ),
        ]

        selected = policy.select_migrant(ineligible)

        assert selected is None
