"""Helpers for normalized monster aggregate persistence."""

from __future__ import annotations

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum, MonsterStatusEnum
from ai_rpg_world.domain.monster.value_object.feed_memory import FeedMemory
from ai_rpg_world.domain.monster.value_object.feed_memory_entry import FeedMemoryEntry
from ai_rpg_world.domain.monster.value_object.monster_behavior_state import MonsterBehaviorState
from ai_rpg_world.domain.monster.value_object.monster_hp import MonsterHp
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_mp import MonsterMp
from ai_rpg_world.domain.monster.value_object.monster_pursuit_state import MonsterPursuitState
from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import PursuitFailureReason
from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import PursuitLastKnownState
from ai_rpg_world.domain.pursuit.value_object.pursuit_state import PursuitState
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import PursuitTargetSnapshot
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.pack_id import PackId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


def build_monster(
    *,
    row: object,
    template: object,
    skill_loadout: SkillLoadoutAggregate,
    active_effect_rows: list[object],
    feed_memory_rows: list[object],
    pursuit_target_row: object | None,
    pursuit_last_known_row: object | None,
) -> MonsterAggregate:
    behavior_state = MonsterBehaviorState.from_parts(
        state=BehaviorStateEnum(str(row["behavior_state"])),
        target_id=None if row["behavior_target_id"] is None else WorldObjectId(int(row["behavior_target_id"])),
        last_known_position=_coordinate_or_none(
            row["behavior_last_known_x"],
            row["behavior_last_known_y"],
            row["behavior_last_known_z"],
        ),
        initial_position=_coordinate_or_none(
            row["behavior_initial_x"],
            row["behavior_initial_y"],
            row["behavior_initial_z"],
        ),
        patrol_index=int(row["behavior_patrol_index"]),
        search_timer=int(row["behavior_search_timer"]),
        failure_count=int(row["behavior_failure_count"]),
    )
    pursuit_state = _build_pursuit_state(
        world_object_id=int(row["world_object_id"]),
        failure_reason=row["pursuit_failure_reason"],
        pursuit_target_row=pursuit_target_row,
        pursuit_last_known_row=pursuit_last_known_row,
    )
    monster = MonsterAggregate(
        monster_id=MonsterId(int(row["monster_id"])),
        template=template,
        world_object_id=WorldObjectId(int(row["world_object_id"])),
        skill_loadout=skill_loadout,
        hp=MonsterHp(int(row["hp_value"]), int(row["hp_max"])),
        mp=MonsterMp(int(row["mp_value"]), int(row["mp_max"])),
        status=MonsterStatusEnum(str(row["status"])),
        last_death_tick=None if row["last_death_tick"] is None else WorldTick(int(row["last_death_tick"])),
        coordinate=_coordinate_or_none(row["coordinate_x"], row["coordinate_y"], row["coordinate_z"]),
        spot_id=None if row["spot_id"] is None else SpotId(int(row["spot_id"])),
        active_effects=[
            StatusEffect(
                effect_type=StatusEffectType(str(effect_row["effect_type"])),
                value=float(effect_row["effect_value"]),
                expiry_tick=WorldTick(int(effect_row["expiry_tick"])),
            )
            for effect_row in active_effect_rows
        ],
        pack_id=None if row["pack_id"] is None else PackId.create(str(row["pack_id"])),
        is_pack_leader=bool(row["is_pack_leader"]),
        initial_spawn_coordinate=_coordinate_or_none(
            row["initial_spawn_x"],
            row["initial_spawn_y"],
            row["initial_spawn_z"],
        ),
        spawned_at_tick=None if row["spawned_at_tick"] is None else WorldTick(int(row["spawned_at_tick"])),
        behavior_state=behavior_state,
        feed_memory=FeedMemory(
            _entries=tuple(
                FeedMemoryEntry(
                    object_id=WorldObjectId(int(memory_row["object_id"])),
                    coordinate=Coordinate(
                        int(memory_row["x"]),
                        int(memory_row["y"]),
                        int(memory_row["z"]),
                    ),
                )
                for memory_row in feed_memory_rows
            )
        ),
        pursuit_state=pursuit_state,
        hunger=float(row["hunger"]),
        starvation_timer=int(row["starvation_timer"]),
    )
    monster.clear_events()
    return monster


def _coordinate_or_none(x: object, y: object, z: object) -> Coordinate | None:
    if x is None or y is None or z is None:
        return None
    return Coordinate(int(x), int(y), int(z))


def _build_pursuit_state(
    *,
    world_object_id: int,
    failure_reason: object,
    pursuit_target_row: object | None,
    pursuit_last_known_row: object | None,
) -> MonsterPursuitState:
    target_snapshot = None
    if pursuit_target_row is not None:
        target_snapshot = PursuitTargetSnapshot(
            target_id=WorldObjectId(int(pursuit_target_row["target_id"])),
            spot_id=SpotId(int(pursuit_target_row["spot_id"])),
            coordinate=Coordinate(
                int(pursuit_target_row["x"]),
                int(pursuit_target_row["y"]),
                int(pursuit_target_row["z"]),
            ),
        )
    last_known = None
    if pursuit_last_known_row is not None:
        last_known = PursuitLastKnownState(
            target_id=WorldObjectId(int(pursuit_last_known_row["target_id"])),
            spot_id=SpotId(int(pursuit_last_known_row["spot_id"])),
            coordinate=Coordinate(
                int(pursuit_last_known_row["x"]),
                int(pursuit_last_known_row["y"]),
                int(pursuit_last_known_row["z"]),
            ),
            observed_at_tick=(
                None
                if pursuit_last_known_row["observed_at_tick"] is None
                else WorldTick(int(pursuit_last_known_row["observed_at_tick"]))
            ),
        )
    if target_snapshot is None and last_known is None:
        return MonsterPursuitState()
    target_id = target_snapshot.target_id if target_snapshot is not None else last_known.target_id
    return MonsterPursuitState(
        pursuit=PursuitState(
            actor_id=WorldObjectId(world_object_id),
            target_id=target_id,
            target_snapshot=target_snapshot,
            last_known=last_known,
            failure_reason=(
                None if failure_reason is None else PursuitFailureReason(str(failure_reason))
            ),
        )
    )


__all__ = ["build_monster"]
