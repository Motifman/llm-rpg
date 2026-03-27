"""SQLite implementation of `MonsterRepository` for the single game DB."""

from __future__ import annotations

import copy
import sqlite3
from typing import Any, List, Optional

from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    allocate_sequence_value,
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_monster_state_codec import build_monster
from ai_rpg_world.infrastructure.repository.sqlite_monster_template_repository import (
    SqliteMonsterTemplateRepository,
    SqliteMonsterTemplateWriter,
)
from ai_rpg_world.infrastructure.repository.sqlite_skill_loadout_repository import (
    SqliteSkillLoadoutRepository,
)


_WORLD_OBJECT_SEQUENCE_START = 99_999


class SqliteMonsterAggregateRepository(MonsterRepository):
    """Store monsters in normalized tables plus existing template/loadout repositories."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        _commits_after_write: bool,
        event_sink: Any = None,
    ) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        self._event_sink = event_sink
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> "SqliteMonsterAggregateRepository":
        return cls(connection, _commits_after_write=True, event_sink=event_sink)

    @classmethod
    def for_shared_unit_of_work(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> "SqliteMonsterAggregateRepository":
        return cls(connection, _commits_after_write=False, event_sink=event_sink)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def _assert_shared_transaction_active(self) -> None:
        if self._commits_after_write:
            return
        if not self._conn.in_transaction:
            raise RuntimeError(
                "for_shared_unit_of_work で生成したリポジトリの書き込みは、"
                "アクティブなトランザクション内（with uow）で実行してください"
            )

    def _maybe_emit_events(self, aggregate: Any) -> None:
        sink = self._event_sink
        if sink is None or not hasattr(sink, "add_events_from_aggregate"):
            return
        if hasattr(sink, "is_in_transaction") and not sink.is_in_transaction():
            return
        sink.add_events_from_aggregate(aggregate)

    def generate_monster_id(self) -> MonsterId:
        self._assert_shared_transaction_active()
        monster_id = MonsterId(allocate_sequence_value(self._conn, "monster_id"))
        self._finalize_write()
        return monster_id

    def generate_world_object_id_for_npc(self) -> WorldObjectId:
        self._assert_shared_transaction_active()
        world_object_id = WorldObjectId(
            allocate_sequence_value(
                self._conn,
                "world_object_id",
                initial_value=_WORLD_OBJECT_SEQUENCE_START,
            )
        )
        self._finalize_write()
        return world_object_id

    def find_by_id(self, entity_id: MonsterId) -> Optional[MonsterAggregate]:
        cur = self._conn.execute(
            "SELECT * FROM game_monsters WHERE monster_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(self._build_monster_from_row(row))

    def find_by_ids(self, entity_ids: List[MonsterId]) -> List[MonsterAggregate]:
        return [x for monster_id in entity_ids for x in [self.find_by_id(monster_id)] if x is not None]

    def find_by_world_object_id(self, world_object_id: WorldObjectId) -> Optional[MonsterAggregate]:
        cur = self._conn.execute(
            "SELECT * FROM game_monsters WHERE world_object_id = ?",
            (int(world_object_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(self._build_monster_from_row(row))

    def find_by_spot_id(self, spot_id: SpotId) -> List[MonsterAggregate]:
        cur = self._conn.execute(
            "SELECT * FROM game_monsters WHERE spot_id = ? ORDER BY monster_id ASC",
            (int(spot_id),),
        )
        return [copy.deepcopy(self._build_monster_from_row(row)) for row in cur.fetchall()]

    def save(self, entity: MonsterAggregate) -> MonsterAggregate:
        self._assert_shared_transaction_active()
        self._maybe_emit_events(entity)

        began_local_transaction = False
        if self._commits_after_write and not self._conn.in_transaction:
            self._conn.execute("BEGIN")
            began_local_transaction = True
        try:
            template_writer = SqliteMonsterTemplateWriter.for_shared_unit_of_work(self._conn)
            template_writer.replace_template(entity.template)
            loadout_repo = SqliteSkillLoadoutRepository.for_shared_unit_of_work(self._conn)
            loadout_repo.save(entity.skill_loadout)

            self._conn.execute(
                """
                INSERT INTO game_monsters (
                    monster_id, world_object_id, spot_id, template_id, skill_loadout_id,
                    hp_value, hp_max, mp_value, mp_max, status, last_death_tick,
                    coordinate_x, coordinate_y, coordinate_z,
                    pack_id, is_pack_leader,
                    initial_spawn_x, initial_spawn_y, initial_spawn_z,
                    spawned_at_tick,
                    behavior_state, behavior_target_id,
                    behavior_last_known_x, behavior_last_known_y, behavior_last_known_z,
                    behavior_initial_x, behavior_initial_y, behavior_initial_z,
                    behavior_patrol_index, behavior_search_timer, behavior_failure_count,
                    pursuit_failure_reason, hunger, starvation_timer
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(monster_id) DO UPDATE SET
                    world_object_id = excluded.world_object_id,
                    spot_id = excluded.spot_id,
                    template_id = excluded.template_id,
                    skill_loadout_id = excluded.skill_loadout_id,
                    hp_value = excluded.hp_value,
                    hp_max = excluded.hp_max,
                    mp_value = excluded.mp_value,
                    mp_max = excluded.mp_max,
                    status = excluded.status,
                    last_death_tick = excluded.last_death_tick,
                    coordinate_x = excluded.coordinate_x,
                    coordinate_y = excluded.coordinate_y,
                    coordinate_z = excluded.coordinate_z,
                    pack_id = excluded.pack_id,
                    is_pack_leader = excluded.is_pack_leader,
                    initial_spawn_x = excluded.initial_spawn_x,
                    initial_spawn_y = excluded.initial_spawn_y,
                    initial_spawn_z = excluded.initial_spawn_z,
                    spawned_at_tick = excluded.spawned_at_tick,
                    behavior_state = excluded.behavior_state,
                    behavior_target_id = excluded.behavior_target_id,
                    behavior_last_known_x = excluded.behavior_last_known_x,
                    behavior_last_known_y = excluded.behavior_last_known_y,
                    behavior_last_known_z = excluded.behavior_last_known_z,
                    behavior_initial_x = excluded.behavior_initial_x,
                    behavior_initial_y = excluded.behavior_initial_y,
                    behavior_initial_z = excluded.behavior_initial_z,
                    behavior_patrol_index = excluded.behavior_patrol_index,
                    behavior_search_timer = excluded.behavior_search_timer,
                    behavior_failure_count = excluded.behavior_failure_count,
                    pursuit_failure_reason = excluded.pursuit_failure_reason,
                    hunger = excluded.hunger,
                    starvation_timer = excluded.starvation_timer
                """,
                (
                    int(entity.monster_id),
                    int(entity.world_object_id),
                    int(entity.spot_id) if entity.spot_id is not None else None,
                    int(entity.template.template_id),
                    int(entity.skill_loadout.loadout_id),
                    entity.hp.value,
                    entity.hp.max_hp,
                    entity.mp.value,
                    entity.mp.max_mp,
                    entity.status.value,
                    None if entity.last_death_tick is None else entity.last_death_tick.value,
                    None if entity.coordinate is None else entity.coordinate.x,
                    None if entity.coordinate is None else entity.coordinate.y,
                    None if entity.coordinate is None else entity.coordinate.z,
                    None if entity.pack_id is None else entity.pack_id.value,
                    1 if entity.is_pack_leader else 0,
                    None if entity.get_respawn_coordinate() is None else entity.get_respawn_coordinate().x,
                    None if entity.get_respawn_coordinate() is None else entity.get_respawn_coordinate().y,
                    None if entity.get_respawn_coordinate() is None else entity.get_respawn_coordinate().z,
                    None if entity.spawned_at_tick is None else entity.spawned_at_tick.value,
                    entity.behavior_state.value,
                    None if entity.behavior_target_id is None else int(entity.behavior_target_id),
                    None if entity.behavior_last_known_position is None else entity.behavior_last_known_position.x,
                    None if entity.behavior_last_known_position is None else entity.behavior_last_known_position.y,
                    None if entity.behavior_last_known_position is None else entity.behavior_last_known_position.z,
                    None if entity.behavior_initial_position is None else entity.behavior_initial_position.x,
                    None if entity.behavior_initial_position is None else entity.behavior_initial_position.y,
                    None if entity.behavior_initial_position is None else entity.behavior_initial_position.z,
                    entity.behavior_patrol_index,
                    entity.behavior_search_timer,
                    entity.behavior_failure_count,
                    None if entity.pursuit_state is None or entity.pursuit_state.failure_reason is None else entity.pursuit_state.failure_reason.value,
                    entity.hunger,
                    entity._lifecycle_state.starvation_timer,
                ),
            )
            monster_id = int(entity.monster_id)
            for table_name in (
                "game_monster_active_effects",
                "game_monster_feed_memories",
                "game_monster_pursuit_target_snapshots",
                "game_monster_pursuit_last_known",
            ):
                self._conn.execute(f"DELETE FROM {table_name} WHERE monster_id = ?", (monster_id,))
            self._conn.executemany(
                """
                INSERT INTO game_monster_active_effects (
                    monster_id, effect_index, effect_type, effect_value, expiry_tick
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        monster_id,
                        effect_index,
                        effect.effect_type.value,
                        effect.value,
                        effect.expiry_tick.value,
                    )
                    for effect_index, effect in enumerate(entity.active_effects)
                ],
            )
            self._conn.executemany(
                """
                INSERT INTO game_monster_feed_memories (
                    monster_id, memory_index, object_id, x, y, z
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        monster_id,
                        memory_index,
                        int(entry.object_id),
                        entry.coordinate.x,
                        entry.coordinate.y,
                        entry.coordinate.z,
                    )
                    for memory_index, entry in enumerate(entity.behavior_last_known_feed)
                ],
            )
            pursuit_state = entity.pursuit_state
            if pursuit_state is not None and pursuit_state.target_snapshot is not None:
                self._conn.execute(
                    """
                    INSERT INTO game_monster_pursuit_target_snapshots (
                        monster_id, target_id, spot_id, x, y, z
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        monster_id,
                        int(pursuit_state.target_snapshot.target_id),
                        int(pursuit_state.target_snapshot.spot_id),
                        pursuit_state.target_snapshot.coordinate.x,
                        pursuit_state.target_snapshot.coordinate.y,
                        pursuit_state.target_snapshot.coordinate.z,
                    ),
                )
            if pursuit_state is not None and pursuit_state.last_known is not None:
                self._conn.execute(
                    """
                    INSERT INTO game_monster_pursuit_last_known (
                        monster_id, target_id, spot_id, x, y, z, observed_at_tick
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        monster_id,
                        int(pursuit_state.last_known.target_id),
                        int(pursuit_state.last_known.spot_id),
                        pursuit_state.last_known.coordinate.x,
                        pursuit_state.last_known.coordinate.y,
                        pursuit_state.last_known.coordinate.z,
                        None
                        if pursuit_state.last_known.observed_at_tick is None
                        else pursuit_state.last_known.observed_at_tick.value,
                    ),
                )
            if began_local_transaction:
                self._conn.commit()
            else:
                self._finalize_write()
        except Exception:
            if began_local_transaction and self._conn.in_transaction:
                self._conn.rollback()
            raise
        return copy.deepcopy(entity)

    def delete(self, entity_id: MonsterId) -> bool:
        self._assert_shared_transaction_active()
        monster_id = int(entity_id)
        for table_name in (
            "game_monster_active_effects",
            "game_monster_feed_memories",
            "game_monster_pursuit_target_snapshots",
            "game_monster_pursuit_last_known",
        ):
            self._conn.execute(f"DELETE FROM {table_name} WHERE monster_id = ?", (monster_id,))
        cur = self._conn.execute(
            "DELETE FROM game_monsters WHERE monster_id = ?",
            (monster_id,),
        )
        self._finalize_write()
        return cur.rowcount > 0

    def find_all(self) -> List[MonsterAggregate]:
        cur = self._conn.execute("SELECT * FROM game_monsters ORDER BY monster_id ASC")
        return [copy.deepcopy(self._build_monster_from_row(row)) for row in cur.fetchall()]

    def _build_monster_from_row(self, row: sqlite3.Row) -> MonsterAggregate:
        template_repo = SqliteMonsterTemplateRepository.for_connection(self._conn)
        template = template_repo.find_by_id(int(row["template_id"]))
        if template is None:
            raise RuntimeError(
                "game_monsters が参照する template_id に対応する game_monster_templates が見つかりません"
            )
        loadout_repo = SqliteSkillLoadoutRepository.for_standalone_connection(self._conn)
        loadout = loadout_repo.find_by_id(int(row["skill_loadout_id"]))
        if loadout is None:
            raise RuntimeError(
                "game_monsters が参照する skill_loadout_id に対応する game_skill_loadouts が見つかりません"
            )
        monster_id = int(row["monster_id"])
        active_effect_rows = self._conn.execute(
            """
            SELECT effect_type, effect_value, expiry_tick
            FROM game_monster_active_effects
            WHERE monster_id = ?
            ORDER BY effect_index ASC
            """,
            (monster_id,),
        ).fetchall()
        feed_memory_rows = self._conn.execute(
            """
            SELECT object_id, x, y, z
            FROM game_monster_feed_memories
            WHERE monster_id = ?
            ORDER BY memory_index ASC
            """,
            (monster_id,),
        ).fetchall()
        pursuit_target_row = self._conn.execute(
            "SELECT * FROM game_monster_pursuit_target_snapshots WHERE monster_id = ?",
            (monster_id,),
        ).fetchone()
        pursuit_last_known_row = self._conn.execute(
            "SELECT * FROM game_monster_pursuit_last_known WHERE monster_id = ?",
            (monster_id,),
        ).fetchone()
        return build_monster(
            row=row,
            template=template,
            skill_loadout=loadout,
            active_effect_rows=list(active_effect_rows),
            feed_memory_rows=list(feed_memory_rows),
            pursuit_target_row=pursuit_target_row,
            pursuit_last_known_row=pursuit_last_known_row,
        )


__all__ = ["SqliteMonsterAggregateRepository"]
