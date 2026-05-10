"""Helpers for normalized monster aggregate persistence."""

from __future__ import annotations

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum, MonsterStatusEnum
from ai_rpg_world.domain.monster.value_object.attacker_ref import (
    AttackerKind,
    AttackerRef,
)
from ai_rpg_world.domain.monster.value_object.feed_memory import FeedMemory
from ai_rpg_world.domain.monster.value_object.feed_memory_entry import FeedMemoryEntry
from ai_rpg_world.domain.monster.value_object.monster_behavior_state import MonsterBehaviorState
from ai_rpg_world.domain.monster.value_object.monster_hp import MonsterHp
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_mp import MonsterMp
from ai_rpg_world.domain.monster.value_object.monster_pursuit_state import MonsterPursuitState
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
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
        # Phase 4a/4b: spot graph 用フィールド復元 (migration v24)
        last_observed_target_spot_id=_optional_spot_id(
            row, "behavior_last_observed_target_spot_id"
        ),
        flee_until_tick=_optional_tick(row, "behavior_flee_until_tick"),
        chase_attacker_ref=_decode_attacker_ref(row),
        chase_started_at_tick=_optional_tick(row, "behavior_chase_started_at_tick"),
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


def _optional_spot_id(row: object, key: str) -> SpotId | None:
    """row[key] が NULL なら None、そうでなければ SpotId を作る。

    migration v24 で追加された行 (behavior_last_observed_target_spot_id 等)
    用。古いスキーマで該当列が無い row では KeyError ではなく None を返す
    (sqlite3.Row は対応列が無いと KeyError を投げるため、try/except でラップ)。
    """
    try:
        value = row[key]
    except (KeyError, IndexError):
        return None
    if value is None:
        return None
    return SpotId(int(value))


def _optional_tick(row: object, key: str) -> WorldTick | None:
    """row[key] が NULL なら None、そうでなければ WorldTick を作る。"""
    try:
        value = row[key]
    except (KeyError, IndexError):
        return None
    if value is None:
        return None
    return WorldTick(int(value))


def _decode_attacker_ref(row: object) -> AttackerRef | None:
    """`behavior_chase_attacker_ref_kind` + 該当 ID から AttackerRef を復元。

    kind=NULL なら None。kind='player' なら player_id 側、'monster' なら
    monster_id 側を読む。スキーマ未マイグレーション (kind カラム自体が無い)
    の場合も None として扱う。
    """
    try:
        kind_value = row["behavior_chase_attacker_ref_kind"]
    except (KeyError, IndexError):
        return None
    if kind_value is None:
        return None
    kind = AttackerKind(str(kind_value))
    if kind == AttackerKind.PLAYER:
        player_id_value = row["behavior_chase_attacker_ref_player_id"]
        if player_id_value is None:
            # kind だけセットされて ID 側が NULL は不整合だが防御
            return None
        return AttackerRef.of_player(PlayerId(int(player_id_value)))
    monster_id_value = row["behavior_chase_attacker_ref_monster_id"]
    if monster_id_value is None:
        return None
    return AttackerRef.of_monster(MonsterId(int(monster_id_value)))


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
