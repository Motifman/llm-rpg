from typing import Any, Callable, Optional, Protocol

from ai_rpg_world.application.world.services.monster_behavior_context_builder import (
    MonsterBehaviorContextBuilder,
)
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.monster.service.behavior_state_transition_service import (
    BehaviorStateTransitionService,
)
from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import (
    PursuitFailureReason,
)
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.enum.world_enum import BehaviorActionType
from ai_rpg_world.domain.world.service.behavior_service import BehaviorService

from ai_rpg_world.application.world.services.monster_foraging_rule import (
    MonsterForagingRule,
)
from ai_rpg_world.application.world.services.monster_pursuit_failure_rule import (
    MonsterPursuitFailureRule,
)
from ai_rpg_world.application.world.services.monster_target_context_builder import (
    MonsterTargetContextBuilder,
)


class _SyncEventDispatcherProtocol(Protocol):
    def flush_sync_events(self) -> None: ...


class MonsterBehaviorCoordinator:
    """monster behavior を一本道で調停する coordinator。"""

    def __init__(
        self,
        monster_repository: MonsterRepository,
        behavior_service: BehaviorService,
        transition_service: BehaviorStateTransitionService,
        action_resolver_factory: Callable[[PhysicalMapAggregate, WorldObject], Any],
        foraging_rule: MonsterForagingRule,
        pursuit_failure_rule: MonsterPursuitFailureRule,
        unit_of_work: UnitOfWork,
        behavior_context_builder: MonsterBehaviorContextBuilder,
        target_context_builder: MonsterTargetContextBuilder,
        action_resolver_factory_getter: Optional[
            Callable[[], Callable[[PhysicalMapAggregate, WorldObject], Any]]
        ] = None,
        sync_event_dispatcher: Optional["_SyncEventDispatcherProtocol"] = None,
    ) -> None:
        self._monster_repository = monster_repository
        self._behavior_service = behavior_service
        self._transition_service = transition_service
        self._action_resolver_factory = action_resolver_factory
        self._action_resolver_factory_getter = action_resolver_factory_getter
        self._foraging_rule = foraging_rule
        self._pursuit_failure_rule = pursuit_failure_rule
        self._unit_of_work = unit_of_work
        self._behavior_context_builder = behavior_context_builder
        self._target_context_builder = target_context_builder
        self._sync_event_dispatcher = sync_event_dispatcher

    def _flush_sync_events(self) -> None:
        if self._sync_event_dispatcher is not None:
            self._sync_event_dispatcher.flush_sync_events()
        else:
            self._unit_of_work.process_sync_events()

    def process_actor_behavior(
        self,
        actor: WorldObject,
        physical_map: PhysicalMapAggregate,
        current_tick: WorldTick,
    ) -> None:
        monster = self._monster_repository.find_by_world_object_id(actor.object_id)
        if monster is None:
            return

        skill_context = self._behavior_context_builder.build_skill_context(
            actor,
            current_tick,
        )
        target_context = self._target_context_builder.build_target_context(
            actor,
            physical_map,
            current_tick,
        )
        growth_context = self._behavior_context_builder.build_growth_context(
            actor,
            current_tick,
        )
        foraging = self._foraging_rule.evaluate(
            actor,
            physical_map,
            monster,
            current_tick,
        )
        observation = self._behavior_service.build_observation(
            actor.object_id,
            physical_map,
            target_context=target_context,
            skill_context=skill_context,
            growth_context=growth_context,
            pack_rally_coordinate=None,
            current_tick=current_tick,
            visible_feed=foraging.visible_feed,
            selected_feed_target=foraging.selected_feed_target,
        )
        snapshot = monster.to_behavior_state_snapshot(actor.coordinate, current_tick)
        transition_result = self._transition_service.compute_transition(
            observation=observation,
            snapshot=snapshot,
            actor_id=monster.world_object_id,
            actor_coordinate=actor.coordinate,
        )
        monster.apply_behavior_transition(transition_result, current_tick)
        monster.apply_territory_return_if_needed(actor.coordinate)

        failure_reason = self._pursuit_failure_rule.evaluate_pre_action(
            monster=monster,
            physical_map=physical_map,
            actor_coordinate=actor.coordinate,
            observation=observation,
        )
        if failure_reason is not None:
            self._fail_and_save(monster, failure_reason, current_tick)
            return

        action_resolver_factory = (
            self._action_resolver_factory_getter()
            if self._action_resolver_factory_getter is not None
            else self._action_resolver_factory
        )
        resolver = action_resolver_factory(physical_map, actor)
        action = resolver.resolve_action(monster, observation, actor.coordinate)
        failure_reason = self._pursuit_failure_rule.evaluate_post_action(
            monster=monster,
            actor_coordinate=actor.coordinate,
            observation=observation,
            action=action,
        )
        if failure_reason is not None:
            self._fail_and_save(monster, failure_reason, current_tick)
            return

        if action.action_type == BehaviorActionType.MOVE and action.coordinate is not None:
            monster.record_move(action.coordinate, current_tick)
        elif (
            action.action_type == BehaviorActionType.USE_SKILL
            and action.skill_slot_index is not None
        ):
            monster.record_use_skill(
                action.skill_slot_index,
                monster.behavior_target_id,
                current_tick,
            )
        elif (
            action.action_type == BehaviorActionType.INTERACT
            and action.target_id is not None
        ):
            monster.record_interact(action.target_id, current_tick)

        self._monster_repository.save(monster)
        self._flush_sync_events()

    def _fail_and_save(
        self,
        monster: MonsterAggregate,
        failure_reason: PursuitFailureReason,
        current_tick: WorldTick,
    ) -> None:
        monster.fail_pursuit(failure_reason, current_tick=current_tick)
        self._monster_repository.save(monster)
        self._flush_sync_events()
