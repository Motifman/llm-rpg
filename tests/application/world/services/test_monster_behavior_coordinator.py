from types import SimpleNamespace
import unittest.mock as mock

from ai_rpg_world.application.world.services.monster_behavior_coordinator import (
    MonsterBehaviorCoordinator,
)
from ai_rpg_world.application.world.services.monster_behavior_context_builder import (
    MonsterBehaviorContextBuilder,
)
from ai_rpg_world.application.world.services.monster_target_context_builder import (
    MonsterTargetContextBuilder,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum
from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import (
    PursuitFailureReason,
)
from ai_rpg_world.domain.world.enum.world_enum import BehaviorActionType
from ai_rpg_world.domain.world.value_object.behavior_action import BehaviorAction
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestMonsterBehaviorCoordinator:
    @staticmethod
    def _behavior_context_builder(skill_context, growth_context):
        builder = mock.create_autospec(MonsterBehaviorContextBuilder, instance=True)
        builder.build_skill_context.return_value = skill_context
        builder.build_growth_context.return_value = growth_context
        return builder

    @staticmethod
    def _target_context_builder(target_context):
        builder = mock.create_autospec(MonsterTargetContextBuilder, instance=True)
        builder.build_target_context.return_value = target_context
        return builder

    @staticmethod
    def _foraging_rule(result):
        rule = mock.Mock()
        rule.evaluate.return_value = result
        return rule

    def test_runs_foraging_observation_transition_failure_resolver_record_in_order(self):
        order: list[str] = []
        monster = mock.Mock()
        monster.world_object_id = WorldObjectId(1)
        monster.behavior_target_id = WorldObjectId(100)
        monster.behavior_state = BehaviorStateEnum.CHASE
        monster.has_active_pursuit = True
        monster.to_behavior_state_snapshot.return_value = mock.sentinel.snapshot
        monster_repository = mock.Mock()
        monster_repository.find_by_world_object_id.return_value = monster
        behavior_service = mock.Mock()
        behavior_service.build_observation.side_effect = (
            lambda *args, **kwargs: order.append("observation")
            or SimpleNamespace(selected_target=mock.sentinel.target)
        )
        foraging_rule = mock.Mock()
        foraging_rule.evaluate.return_value = SimpleNamespace(
            visible_feed=[mock.sentinel.feed],
            selected_feed_target=mock.sentinel.feed,
        )
        foraging_rule.evaluate.side_effect = (
            lambda *args, **kwargs: order.append("foraging")
            or SimpleNamespace(
                visible_feed=[mock.sentinel.feed],
                selected_feed_target=mock.sentinel.feed,
            )
        )
        transition_service = mock.Mock()
        transition_service.compute_transition.side_effect = (
            lambda **kwargs: order.append("transition") or mock.sentinel.transition
        )
        failure_rule = mock.Mock()
        failure_rule.evaluate_pre_action.side_effect = (
            lambda **kwargs: order.append("pre-failure") or None
        )
        failure_rule.evaluate_post_action.side_effect = (
            lambda **kwargs: order.append("post-failure") or None
        )
        resolver = mock.Mock()
        resolver.resolve_action.side_effect = (
            lambda *args, **kwargs: order.append("resolver")
            or BehaviorAction.move(Coordinate(1, 0, 0))
        )
        action_resolver_factory = mock.Mock(return_value=resolver)
        actor = SimpleNamespace(object_id=WorldObjectId(1), coordinate=Coordinate(0, 0, 0))
        physical_map = mock.Mock()
        unit_of_work = mock.Mock()
        coordinator = MonsterBehaviorCoordinator(
            monster_repository=monster_repository,
            behavior_service=behavior_service,
            transition_service=transition_service,
            action_resolver_factory=action_resolver_factory,
            foraging_rule=foraging_rule,
            pursuit_failure_rule=failure_rule,
            unit_of_work=unit_of_work,
            behavior_context_builder=self._behavior_context_builder(
                mock.sentinel.skill,
                mock.sentinel.growth,
            ),
            target_context_builder=self._target_context_builder(
                mock.sentinel.target_context
            ),
        )

        coordinator.process_actor_behavior(actor, physical_map, WorldTick(10))

        assert order == [
            "foraging",
            "observation",
            "transition",
            "pre-failure",
            "resolver",
            "post-failure",
        ]
        monster.apply_behavior_transition.assert_called_once_with(
            mock.sentinel.transition,
            WorldTick(10),
        )
        monster.record_move.assert_called_once_with(Coordinate(1, 0, 0), WorldTick(10))
        monster_repository.save.assert_called_once_with(monster)
        unit_of_work.process_sync_events.assert_called_once()

    def test_fails_with_target_missing_before_resolver(self):
        monster = mock.Mock()
        monster.world_object_id = WorldObjectId(1)
        monster.behavior_target_id = WorldObjectId(100)
        monster.behavior_state = BehaviorStateEnum.SEARCH
        monster.has_active_pursuit = True
        monster.to_behavior_state_snapshot.return_value = mock.sentinel.snapshot
        monster_repository = mock.Mock()
        monster_repository.find_by_world_object_id.return_value = monster
        behavior_service = mock.Mock()
        behavior_service.build_observation.return_value = SimpleNamespace(selected_target=None)
        transition_service = mock.Mock()
        transition_service.compute_transition.return_value = mock.sentinel.transition
        failure_rule = mock.Mock()
        failure_rule.evaluate_pre_action.return_value = PursuitFailureReason.TARGET_MISSING
        resolver = mock.Mock()
        unit_of_work = mock.Mock()
        coordinator = MonsterBehaviorCoordinator(
            monster_repository=monster_repository,
            behavior_service=behavior_service,
            transition_service=transition_service,
            action_resolver_factory=mock.Mock(return_value=resolver),
            foraging_rule=self._foraging_rule(
                SimpleNamespace(visible_feed=[], selected_feed_target=None)
            ),
            pursuit_failure_rule=failure_rule,
            unit_of_work=unit_of_work,
            behavior_context_builder=self._behavior_context_builder(None, None),
            target_context_builder=self._target_context_builder(None),
        )
        actor = SimpleNamespace(object_id=WorldObjectId(1), coordinate=Coordinate(0, 0, 0))

        coordinator.process_actor_behavior(actor, mock.Mock(), WorldTick(10))

        resolver.resolve_action.assert_not_called()
        monster.fail_pursuit.assert_called_once_with(
            PursuitFailureReason.TARGET_MISSING,
            current_tick=WorldTick(10),
        )

    def test_fails_with_vision_lost_at_last_known_after_resolver(self):
        monster = mock.Mock()
        monster.world_object_id = WorldObjectId(1)
        monster.behavior_target_id = WorldObjectId(100)
        monster.behavior_state = BehaviorStateEnum.SEARCH
        monster.has_active_pursuit = True
        monster.to_behavior_state_snapshot.return_value = mock.sentinel.snapshot
        monster_repository = mock.Mock()
        monster_repository.find_by_world_object_id.return_value = monster
        behavior_service = mock.Mock()
        behavior_service.build_observation.return_value = SimpleNamespace(selected_target=None)
        transition_service = mock.Mock()
        transition_service.compute_transition.return_value = mock.sentinel.transition
        failure_rule = mock.Mock()
        failure_rule.evaluate_pre_action.return_value = None
        failure_rule.evaluate_post_action.return_value = (
            PursuitFailureReason.VISION_LOST_AT_LAST_KNOWN
        )
        resolver = mock.Mock()
        resolver.resolve_action.return_value = BehaviorAction.wait()
        unit_of_work = mock.Mock()
        coordinator = MonsterBehaviorCoordinator(
            monster_repository=monster_repository,
            behavior_service=behavior_service,
            transition_service=transition_service,
            action_resolver_factory=mock.Mock(return_value=resolver),
            foraging_rule=self._foraging_rule(
                SimpleNamespace(visible_feed=[], selected_feed_target=None)
            ),
            pursuit_failure_rule=failure_rule,
            unit_of_work=unit_of_work,
            behavior_context_builder=self._behavior_context_builder(None, None),
            target_context_builder=self._target_context_builder(None),
        )
        actor = SimpleNamespace(object_id=WorldObjectId(1), coordinate=Coordinate(0, 0, 0))

        coordinator.process_actor_behavior(actor, mock.Mock(), WorldTick(10))

        resolver.resolve_action.assert_called_once()
        monster.fail_pursuit.assert_called_once_with(
            PursuitFailureReason.VISION_LOST_AT_LAST_KNOWN,
            current_tick=WorldTick(10),
        )
        monster.record_move.assert_not_called()
        unit_of_work.process_sync_events.assert_called_once()

    def test_records_skill_and_interact_actions(self):
        for action in (
            BehaviorAction(action_type=BehaviorActionType.USE_SKILL, skill_slot_index=2),
            BehaviorAction(action_type=BehaviorActionType.INTERACT, target_id=WorldObjectId(200)),
        ):
            monster = mock.Mock()
            monster.world_object_id = WorldObjectId(1)
            monster.behavior_target_id = WorldObjectId(100)
            monster.behavior_state = BehaviorStateEnum.CHASE
            monster.has_active_pursuit = True
            monster.to_behavior_state_snapshot.return_value = mock.sentinel.snapshot
            monster_repository = mock.Mock()
            monster_repository.find_by_world_object_id.return_value = monster
            behavior_service = mock.Mock()
            behavior_service.build_observation.return_value = SimpleNamespace(selected_target=mock.sentinel.target)
            transition_service = mock.Mock()
            transition_service.compute_transition.return_value = mock.sentinel.transition
            resolver = mock.Mock()
            resolver.resolve_action.return_value = action
            coordinator = MonsterBehaviorCoordinator(
                monster_repository=monster_repository,
                behavior_service=behavior_service,
                transition_service=transition_service,
                action_resolver_factory=mock.Mock(return_value=resolver),
                foraging_rule=self._foraging_rule(
                    SimpleNamespace(visible_feed=[], selected_feed_target=None)
                ),
                pursuit_failure_rule=mock.Mock(
                    evaluate_pre_action=mock.Mock(return_value=None),
                    evaluate_post_action=mock.Mock(return_value=None),
                ),
                unit_of_work=mock.Mock(),
                behavior_context_builder=self._behavior_context_builder(None, None),
                target_context_builder=self._target_context_builder(None),
            )
            actor = SimpleNamespace(object_id=WorldObjectId(1), coordinate=Coordinate(0, 0, 0))

            coordinator.process_actor_behavior(actor, mock.Mock(), WorldTick(10))

            if action.action_type == BehaviorActionType.USE_SKILL:
                monster.record_use_skill.assert_called_once_with(2, monster.behavior_target_id, WorldTick(10))
            else:
                monster.record_interact.assert_called_once_with(WorldObjectId(200), WorldTick(10))
