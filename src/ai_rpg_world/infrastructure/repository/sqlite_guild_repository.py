"""SQLite implementation of guild aggregate repository."""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
from ai_rpg_world.domain.guild.repository.guild_repository import GuildRepository
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    allocate_sequence_value,
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_guild_state_codec import build_guild


class SqliteGuildRepository(GuildRepository):
    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(cls, connection: sqlite3.Connection) -> "SqliteGuildRepository":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(cls, connection: sqlite3.Connection) -> "SqliteGuildRepository":
        return cls(connection, _commits_after_write=False)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def find_by_id(self, entity_id: GuildId) -> Optional[GuildAggregate]:
        cur = self._conn.execute(
            """
            SELECT guild_id, spot_id, location_area_id, name, description
            FROM game_guilds
            WHERE guild_id = ?
            """,
            (int(entity_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self._build_guild_from_row(row)

    def find_by_ids(self, entity_ids: List[GuildId]) -> List[GuildAggregate]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[GuildAggregate]:
        cur = self._conn.execute(
            """
            SELECT guild_id, spot_id, location_area_id, name, description
            FROM game_guilds
            ORDER BY guild_id ASC
            """
        )
        return [self._build_guild_from_row(row) for row in cur.fetchall()]

    def save(self, entity: GuildAggregate) -> GuildAggregate:
        self._conn.execute(
            """
            INSERT INTO game_guilds (
                guild_id, spot_id, location_area_id, name, description
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                spot_id = excluded.spot_id,
                location_area_id = excluded.location_area_id,
                name = excluded.name,
                description = excluded.description
            """,
            (
                int(entity.guild_id),
                int(entity.spot_id),
                int(entity.location_area_id),
                entity.name,
                entity.description,
            ),
        )
        self._conn.execute(
            "DELETE FROM game_guild_members WHERE guild_id = ?",
            (int(entity.guild_id),),
        )
        self._conn.executemany(
            """
            INSERT INTO game_guild_members (
                guild_id, player_id, role, joined_at, contribution_points
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    int(entity.guild_id),
                    int(player_id),
                    membership.role.value,
                    membership.joined_at.isoformat(),
                    membership.contribution_points,
                )
                for player_id, membership in sorted(entity.members.items(), key=lambda item: int(item[0]))
            ],
        )
        self._finalize_write()
        return entity

    def delete(self, entity_id: GuildId) -> bool:
        self._conn.execute(
            "DELETE FROM game_guild_members WHERE guild_id = ?",
            (int(entity_id),),
        )
        cur = self._conn.execute(
            "DELETE FROM game_guilds WHERE guild_id = ?",
            (int(entity_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0

    def generate_guild_id(self) -> GuildId:
        return GuildId(allocate_sequence_value(self._conn, "guild_id", initial_value=0))

    def find_by_spot_and_location(
        self,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
    ) -> Optional[GuildAggregate]:
        cur = self._conn.execute(
            """
            SELECT guild_id, spot_id, location_area_id, name, description
            FROM game_guilds
            WHERE spot_id = ? AND location_area_id = ?
            """,
            (int(spot_id), int(location_area_id)),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self._build_guild_from_row(row)

    def find_guilds_by_player_id(self, player_id: PlayerId) -> List[GuildAggregate]:
        cur = self._conn.execute(
            """
            SELECT guild.guild_id, guild.spot_id, guild.location_area_id, guild.name, guild.description
            FROM game_guild_members member
            JOIN game_guilds guild ON guild.guild_id = member.guild_id
            WHERE member.player_id = ?
            ORDER BY guild.guild_id ASC
            """,
            (int(player_id),),
        )
        return [self._build_guild_from_row(row) for row in cur.fetchall()]

    def _build_guild_from_row(self, row: sqlite3.Row) -> GuildAggregate:
        member_rows = self._conn.execute(
            """
            SELECT player_id, role, joined_at, contribution_points
            FROM game_guild_members
            WHERE guild_id = ?
            ORDER BY player_id ASC
            """,
            (int(row["guild_id"]),),
        ).fetchall()
        return build_guild(
            guild_id=int(row["guild_id"]),
            spot_id=int(row["spot_id"]),
            location_area_id=int(row["location_area_id"]),
            name=row["name"],
            description=row["description"],
            member_rows=[
                (
                    int(member_row["player_id"]),
                    member_row["role"],
                    member_row["joined_at"],
                    int(member_row["contribution_points"]),
                )
                for member_row in member_rows
            ],
        )


__all__ = ["SqliteGuildRepository"]
