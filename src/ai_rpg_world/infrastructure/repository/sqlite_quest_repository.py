"""SQLite implementation of quest aggregate repository."""

from __future__ import annotations

import copy
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
from ai_rpg_world.infrastructure.repository.sqlite_pickle_codec import (
    blob_to_object,
    object_to_blob,
)


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
            "SELECT aggregate_blob FROM game_quests WHERE quest_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(blob_to_object(bytes(row["aggregate_blob"])))

    def find_by_ids(self, entity_ids: List[QuestId]) -> List[QuestAggregate]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[QuestAggregate]:
        cur = self._conn.execute("SELECT aggregate_blob FROM game_quests ORDER BY quest_id ASC")
        return [copy.deepcopy(blob_to_object(bytes(row["aggregate_blob"]))) for row in cur.fetchall()]

    def save(self, entity: QuestAggregate) -> QuestAggregate:
        acceptor_player_id = None if entity.acceptor_player_id is None else int(entity.acceptor_player_id)
        self._conn.execute(
            """
            INSERT INTO game_quests (
                quest_id, status, guild_id, acceptor_player_id, created_at, aggregate_blob
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(quest_id) DO UPDATE SET
                status = excluded.status,
                guild_id = excluded.guild_id,
                acceptor_player_id = excluded.acceptor_player_id,
                created_at = excluded.created_at,
                aggregate_blob = excluded.aggregate_blob
            """,
            (
                int(entity.quest_id),
                entity.status.value,
                entity.guild_id,
                acceptor_player_id,
                entity.created_at.isoformat(),
                object_to_blob(entity),
            ),
        )
        self._finalize_write()
        return entity

    def delete(self, entity_id: QuestId) -> bool:
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
            SELECT aggregate_blob FROM game_quests
            WHERE status = ? AND acceptor_player_id = ?
            ORDER BY quest_id ASC
            """,
            (QuestStatus.ACCEPTED.value, int(player_id)),
        )
        return [copy.deepcopy(blob_to_object(bytes(row["aggregate_blob"]))) for row in cur.fetchall()]


__all__ = ["SqliteQuestRepository"]
