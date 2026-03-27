"""SQLite implementation of quest aggregate repository."""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.quest.aggregate.quest_aggregate import QuestAggregate
from ai_rpg_world.domain.quest.enum.quest_enum import QuestStatus
from ai_rpg_world.domain.quest.repository.quest_repository import QuestRepository
from ai_rpg_world.domain.quest.value_object.quest_id import QuestId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    allocate_sequence_value,
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_quest_state_codec import build_quest


class SqliteQuestRepository(QuestRepository):
    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(cls, connection: sqlite3.Connection) -> "SqliteQuestRepository":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(cls, connection: sqlite3.Connection) -> "SqliteQuestRepository":
        return cls(connection, _commits_after_write=False)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def find_by_id(self, entity_id: QuestId) -> Optional[QuestAggregate]:
        cur = self._conn.execute(
            "SELECT * FROM game_quests WHERE quest_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self._build_quest_from_row(row)

    def find_by_ids(self, entity_ids: List[QuestId]) -> List[QuestAggregate]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[QuestAggregate]:
        cur = self._conn.execute("SELECT * FROM game_quests ORDER BY quest_id ASC")
        return [self._build_quest_from_row(row) for row in cur.fetchall()]

    def save(self, entity: QuestAggregate) -> QuestAggregate:
        acceptor_player_id = None if entity.acceptor_player_id is None else int(entity.acceptor_player_id)
        self._conn.execute(
            """
            INSERT INTO game_quests (
                quest_id, status, issuer_player_id, guild_id, acceptor_player_id,
                scope_type, scope_target_player_id, scope_guild_id,
                reward_gold, reward_exp, reserved_gold, version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(quest_id) DO UPDATE SET
                status = excluded.status,
                issuer_player_id = excluded.issuer_player_id,
                guild_id = excluded.guild_id,
                acceptor_player_id = excluded.acceptor_player_id,
                scope_type = excluded.scope_type,
                scope_target_player_id = excluded.scope_target_player_id,
                scope_guild_id = excluded.scope_guild_id,
                reward_gold = excluded.reward_gold,
                reward_exp = excluded.reward_exp,
                reserved_gold = excluded.reserved_gold,
                version = excluded.version,
                created_at = excluded.created_at
            """,
            (
                int(entity.quest_id),
                entity.status.value,
                None if entity.issuer_player_id is None else int(entity.issuer_player_id),
                entity.guild_id,
                acceptor_player_id,
                entity.scope.scope_type.value,
                None if entity.scope.target_player_id is None else int(entity.scope.target_player_id),
                entity.scope.guild_id,
                entity.reward.gold,
                entity.reward.exp,
                entity.reserved_gold,
                entity.version,
                entity.created_at.isoformat(),
            ),
        )
        self._conn.execute("DELETE FROM game_quest_objectives WHERE quest_id = ?", (int(entity.quest_id),))
        self._conn.execute("DELETE FROM game_quest_reward_items WHERE quest_id = ?", (int(entity.quest_id),))
        self._conn.execute("DELETE FROM game_quest_reserved_items WHERE quest_id = ?", (int(entity.quest_id),))
        self._conn.executemany(
            """
            INSERT INTO game_quest_objectives (
                quest_id, objective_index, objective_type, target_id,
                required_count, current_count, target_id_secondary
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(entity.quest_id),
                    index,
                    objective.objective_type.value,
                    objective.target_id,
                    objective.required_count,
                    objective.current_count,
                    objective.target_id_secondary,
                )
                for index, objective in enumerate(entity.objectives)
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_quest_reward_items (
                quest_id, reward_index, item_spec_id, quantity
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (int(entity.quest_id), index, int(item_spec_id), quantity)
                for index, (item_spec_id, quantity) in enumerate(entity.reward.item_rewards)
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_quest_reserved_items (
                quest_id, item_index, item_instance_id
            ) VALUES (?, ?, ?)
            """,
            [
                (int(entity.quest_id), index, int(item_instance_id))
                for index, item_instance_id in enumerate(entity.reserved_item_instance_ids)
            ],
        )
        self._finalize_write()
        return entity

    def delete(self, entity_id: QuestId) -> bool:
        cur = self._conn.execute(
            "DELETE FROM game_quest_objectives WHERE quest_id = ?",
            (int(entity_id),),
        )
        self._conn.execute(
            "DELETE FROM game_quest_reward_items WHERE quest_id = ?",
            (int(entity_id),),
        )
        self._conn.execute(
            "DELETE FROM game_quest_reserved_items WHERE quest_id = ?",
            (int(entity_id),),
        )
        cur = self._conn.execute(
            "DELETE FROM game_quests WHERE quest_id = ?",
            (int(entity_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0

    def generate_quest_id(self) -> QuestId:
        return QuestId(allocate_sequence_value(self._conn, "quest_id", initial_value=0))

    def find_accepted_quests_by_player(self, player_id: PlayerId) -> List[QuestAggregate]:
        cur = self._conn.execute(
            """
            SELECT * FROM game_quests
            WHERE status = ? AND acceptor_player_id = ?
            ORDER BY quest_id ASC
            """,
            (QuestStatus.ACCEPTED.value, int(player_id)),
        )
        return [self._build_quest_from_row(row) for row in cur.fetchall()]

    def _build_quest_from_row(self, row: sqlite3.Row) -> QuestAggregate:
        objective_rows = self._conn.execute(
            """
            SELECT objective_type, target_id, required_count, current_count, target_id_secondary
            FROM game_quest_objectives
            WHERE quest_id = ?
            ORDER BY objective_index ASC
            """,
            (int(row["quest_id"]),),
        ).fetchall()
        reward_rows = self._conn.execute(
            """
            SELECT item_spec_id, quantity
            FROM game_quest_reward_items
            WHERE quest_id = ?
            ORDER BY reward_index ASC
            """,
            (int(row["quest_id"]),),
        ).fetchall()
        reserved_rows = self._conn.execute(
            """
            SELECT item_instance_id
            FROM game_quest_reserved_items
            WHERE quest_id = ?
            ORDER BY item_index ASC
            """,
            (int(row["quest_id"]),),
        ).fetchall()
        return build_quest(
            row=row,
            objective_rows=[
                (
                    objective_row["objective_type"],
                    int(objective_row["target_id"]),
                    int(objective_row["required_count"]),
                    int(objective_row["current_count"]),
                    objective_row["target_id_secondary"],
                )
                for objective_row in objective_rows
            ],
            reward_rows=[
                (int(reward_row["item_spec_id"]), int(reward_row["quantity"]))
                for reward_row in reward_rows
            ],
            reserved_item_rows=[int(reserved_row["item_instance_id"]) for reserved_row in reserved_rows],
        )


__all__ = ["SqliteQuestRepository"]
