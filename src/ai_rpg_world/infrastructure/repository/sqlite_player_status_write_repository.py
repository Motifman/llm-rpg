"""プレイヤーステータス集約の SQLite 実装（正規化テーブル、ゲーム書き込み DB）。"""
from __future__ import annotations

import copy
import sqlite3
from typing import Any, List, Optional

from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import init_game_write_schema
from ai_rpg_world.infrastructure.repository.sqlite_player_state_codec import build_player_status


class SqlitePlayerStatusWriteRepository(PlayerStatusRepository):
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
    ) -> SqlitePlayerStatusWriteRepository:
        return cls(connection, _commits_after_write=True, event_sink=event_sink)

    @classmethod
    def for_shared_unit_of_work(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> SqlitePlayerStatusWriteRepository:
        return cls(connection, _commits_after_write=False, event_sink=event_sink)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def _assert_shared_transaction_active(self) -> None:
        if self._commits_after_write:
            return
        if not self._conn.in_transaction:
            raise RuntimeError(
                "for_shared_unit_of_work で生成したリポジトリの書き込みは、アクティブなトランザクション内（with uow）で実行してください"
            )

    def _maybe_emit_events(self, aggregate: Any) -> None:
        sink = self._event_sink
        if sink is None or not hasattr(sink, "add_events_from_aggregate"):
            return
        if hasattr(sink, "is_in_transaction") and not sink.is_in_transaction():
            return
        sink.add_events_from_aggregate(aggregate)

    def find_by_id(self, player_id: PlayerId) -> Optional[PlayerStatusAggregate]:
        row = self._conn.execute("SELECT * FROM game_player_statuses WHERE player_id = ?", (int(player_id),)).fetchone()
        if row is None:
            return None
        return copy.deepcopy(self._build_status_from_row(row))

    def find_by_ids(self, player_ids: List[PlayerId]) -> List[PlayerStatusAggregate]:
        return [x for pid in player_ids for x in [self.find_by_id(pid)] if x is not None]

    def save(self, status: PlayerStatusAggregate) -> PlayerStatusAggregate:
        self._assert_shared_transaction_active()
        self._maybe_emit_events(status)
        player_id = int(status.player_id)
        self._conn.execute(
            """
            INSERT INTO game_player_statuses (
                player_id,
                base_max_hp, base_max_mp, base_attack, base_defense, base_speed, base_critical_rate, base_evasion_rate,
                growth_hp_factor, growth_mp_factor, growth_attack_factor, growth_defense_factor, growth_speed_factor,
                growth_critical_rate_factor, growth_evasion_rate_factor,
                exp_table_base_exp, exp_table_exponent, exp_table_level_offset,
                growth_level, growth_total_exp, gold_value,
                hp_value, hp_max, mp_value, mp_max, stamina_value, stamina_max,
                current_spot_id, current_coordinate_x, current_coordinate_y, current_coordinate_z,
                current_destination_x, current_destination_y, current_destination_z,
                goal_destination_type, goal_spot_id, goal_location_area_id, goal_world_object_id,
                is_down, attention_level
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                base_max_hp = excluded.base_max_hp,
                base_max_mp = excluded.base_max_mp,
                base_attack = excluded.base_attack,
                base_defense = excluded.base_defense,
                base_speed = excluded.base_speed,
                base_critical_rate = excluded.base_critical_rate,
                base_evasion_rate = excluded.base_evasion_rate,
                growth_hp_factor = excluded.growth_hp_factor,
                growth_mp_factor = excluded.growth_mp_factor,
                growth_attack_factor = excluded.growth_attack_factor,
                growth_defense_factor = excluded.growth_defense_factor,
                growth_speed_factor = excluded.growth_speed_factor,
                growth_critical_rate_factor = excluded.growth_critical_rate_factor,
                growth_evasion_rate_factor = excluded.growth_evasion_rate_factor,
                exp_table_base_exp = excluded.exp_table_base_exp,
                exp_table_exponent = excluded.exp_table_exponent,
                exp_table_level_offset = excluded.exp_table_level_offset,
                growth_level = excluded.growth_level,
                growth_total_exp = excluded.growth_total_exp,
                gold_value = excluded.gold_value,
                hp_value = excluded.hp_value,
                hp_max = excluded.hp_max,
                mp_value = excluded.mp_value,
                mp_max = excluded.mp_max,
                stamina_value = excluded.stamina_value,
                stamina_max = excluded.stamina_max,
                current_spot_id = excluded.current_spot_id,
                current_coordinate_x = excluded.current_coordinate_x,
                current_coordinate_y = excluded.current_coordinate_y,
                current_coordinate_z = excluded.current_coordinate_z,
                current_destination_x = excluded.current_destination_x,
                current_destination_y = excluded.current_destination_y,
                current_destination_z = excluded.current_destination_z,
                goal_destination_type = excluded.goal_destination_type,
                goal_spot_id = excluded.goal_spot_id,
                goal_location_area_id = excluded.goal_location_area_id,
                goal_world_object_id = excluded.goal_world_object_id,
                is_down = excluded.is_down,
                attention_level = excluded.attention_level
            """,
            (
                player_id,
                status.base_stats.max_hp, status.base_stats.max_mp, status.base_stats.attack, status.base_stats.defense, status.base_stats.speed, status.base_stats.critical_rate, status.base_stats.evasion_rate,
                status.stat_growth_factor.hp_factor, status.stat_growth_factor.mp_factor, status.stat_growth_factor.attack_factor, status.stat_growth_factor.defense_factor, status.stat_growth_factor.speed_factor,
                status.stat_growth_factor.critical_rate_factor, status.stat_growth_factor.evasion_rate_factor,
                status.exp_table.base_exp, status.exp_table.exponent, status.exp_table.level_offset,
                status.growth.level, status.growth.total_exp, status.gold.value,
                status.hp.value, status.hp.max_hp, status.mp.value, status.mp.max_mp, status.stamina.value, status.stamina.max_stamina,
                None if status.current_spot_id is None else int(status.current_spot_id),
                None if status.current_coordinate is None else status.current_coordinate.x,
                None if status.current_coordinate is None else status.current_coordinate.y,
                None if status.current_coordinate is None else status.current_coordinate.z,
                None if status.current_destination is None else status.current_destination.x,
                None if status.current_destination is None else status.current_destination.y,
                None if status.current_destination is None else status.current_destination.z,
                status.goal_destination_type,
                None if status.goal_spot_id is None else int(status.goal_spot_id),
                None if status.goal_location_area_id is None else int(status.goal_location_area_id),
                None if status.goal_world_object_id is None else int(status.goal_world_object_id),
                1 if status.is_down else 0,
                status.attention_level.value,
            ),
        )
        for table_name in (
            "game_player_navigation_path",
            "game_player_active_effects",
            "game_player_pursuit_target_snapshots",
            "game_player_pursuit_last_known",
        ):
            self._conn.execute(f"DELETE FROM {table_name} WHERE player_id = ?", (player_id,))
        self._conn.executemany(
            "INSERT INTO game_player_navigation_path (player_id, step_index, x, y, z) VALUES (?, ?, ?, ?, ?)",
            [(player_id, idx, coord.x, coord.y, coord.z) for idx, coord in enumerate(status.planned_path)],
        )
        self._conn.executemany(
            "INSERT INTO game_player_active_effects (player_id, effect_index, effect_type, effect_value, expiry_tick) VALUES (?, ?, ?, ?, ?)",
            [(player_id, idx, effect.effect_type.name, effect.value, effect.expiry_tick.value) for idx, effect in enumerate(status.active_effects)],
        )
        pursuit = status.pursuit_state
        if pursuit is not None and pursuit.target_snapshot is not None:
            self._conn.execute(
                "INSERT INTO game_player_pursuit_target_snapshots (player_id, target_id, spot_id, x, y, z) VALUES (?, ?, ?, ?, ?, ?)",
                (player_id, int(pursuit.target_snapshot.target_id), int(pursuit.target_snapshot.spot_id), pursuit.target_snapshot.coordinate.x, pursuit.target_snapshot.coordinate.y, pursuit.target_snapshot.coordinate.z),
            )
        if pursuit is not None and pursuit.last_known is not None:
            self._conn.execute(
                "INSERT INTO game_player_pursuit_last_known (player_id, target_id, spot_id, x, y, z, observed_at_tick) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (player_id, int(pursuit.last_known.target_id), int(pursuit.last_known.spot_id), pursuit.last_known.coordinate.x, pursuit.last_known.coordinate.y, pursuit.last_known.coordinate.z, None if pursuit.last_known.observed_at_tick is None else pursuit.last_known.observed_at_tick.value),
            )
        self._finalize_write()
        return copy.deepcopy(status)

    def save_all(self, statuses: List[PlayerStatusAggregate]) -> None:
        for s in statuses:
            self.save(s)

    def delete(self, player_id: PlayerId) -> bool:
        self._assert_shared_transaction_active()
        player_id_value = int(player_id)
        for table_name in (
            "game_player_navigation_path",
            "game_player_active_effects",
            "game_player_pursuit_target_snapshots",
            "game_player_pursuit_last_known",
        ):
            self._conn.execute(f"DELETE FROM {table_name} WHERE player_id = ?", (player_id_value,))
        cur = self._conn.execute("DELETE FROM game_player_statuses WHERE player_id = ?", (player_id_value,))
        self._finalize_write()
        return cur.rowcount > 0

    def find_all(self) -> List[PlayerStatusAggregate]:
        cur = self._conn.execute("SELECT * FROM game_player_statuses ORDER BY player_id ASC")
        return [copy.deepcopy(self._build_status_from_row(row)) for row in cur.fetchall()]

    def _build_status_from_row(self, row: sqlite3.Row) -> PlayerStatusAggregate:
        player_id = int(row["player_id"])
        path_rows = self._conn.execute(
            "SELECT step_index, x, y, z FROM game_player_navigation_path WHERE player_id = ? ORDER BY step_index ASC",
            (player_id,),
        ).fetchall()
        active_effect_rows = self._conn.execute(
            "SELECT effect_type, effect_value, expiry_tick FROM game_player_active_effects WHERE player_id = ? ORDER BY effect_index ASC",
            (player_id,),
        ).fetchall()
        pursuit_target_row = self._conn.execute(
            "SELECT * FROM game_player_pursuit_target_snapshots WHERE player_id = ?",
            (player_id,),
        ).fetchone()
        pursuit_last_known_row = self._conn.execute(
            "SELECT * FROM game_player_pursuit_last_known WHERE player_id = ?",
            (player_id,),
        ).fetchone()
        return build_player_status(
            row=row,
            path_rows=list(path_rows),
            active_effect_rows=list(active_effect_rows),
            pursuit_target_row=pursuit_target_row,
            pursuit_last_known_row=pursuit_last_known_row,
        )


__all__ = ["SqlitePlayerStatusWriteRepository"]
