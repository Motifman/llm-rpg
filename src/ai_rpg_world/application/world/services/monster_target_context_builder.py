from typing import Optional

from typing import Callable, Optional

from ai_rpg_world.application.world.aggro_store import AggroStore
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    AutonomousBehaviorComponent,
)
from ai_rpg_world.domain.world.value_object.behavior_context import (
    TargetSelectionContext,
)
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class MonsterTargetContextBuilder:
    """aggro と pack 連携から target context を構築する。"""

    def __init__(
        self,
        monster_repository: MonsterRepository | None = None,
        aggro_store: AggroStore | None = None,
        monster_repository_getter: Callable[[], MonsterRepository | None] | None = None,
        aggro_store_getter: Callable[[], AggroStore | None] | None = None,
    ) -> None:
        self._monster_repository_getter = monster_repository_getter or (
            lambda: monster_repository
        )
        self._aggro_store_getter = aggro_store_getter or (lambda: aggro_store)

    def build_target_context(
        self,
        actor: WorldObject,
        physical_map: PhysicalMapAggregate,
        current_tick: WorldTick,
    ) -> Optional[TargetSelectionContext]:
        if not isinstance(actor.component, AutonomousBehaviorComponent):
            return None

        monster_repository = self._monster_repository_getter()
        aggro_store = self._aggro_store_getter()
        component = actor.component
        pack_leader_target_id: Optional[WorldObjectId] = None
        if (
            monster_repository is not None
            and component.pack_id is not None
            and not component.is_pack_leader
        ):
            pack_actors = physical_map.get_actors_in_pack(component.pack_id)
            leader_obj = next(
                (candidate for candidate in pack_actors if candidate.component.is_pack_leader),
                None,
            )
            if leader_obj is not None:
                leader_monster = monster_repository.find_by_world_object_id(
                    leader_obj.object_id
                )
                if (
                    leader_monster is not None
                    and leader_monster.behavior_target_id is not None
                ):
                    pack_leader_target_id = leader_monster.behavior_target_id

        if aggro_store is None and pack_leader_target_id is None:
            return None

        threat_by_id: dict[WorldObjectId, int] = {}
        if aggro_store is not None:
            threat_by_id = aggro_store.get_threat_by_attacker(
                physical_map.spot_id,
                actor.object_id,
                current_tick=current_tick.value,
                memory_policy=component.aggro_memory_policy,
            ) or {}

        if not threat_by_id and pack_leader_target_id is None:
            return None

        return TargetSelectionContext(
            threat_by_id=threat_by_id,
            pack_leader_target_id=pack_leader_target_id,
        )
