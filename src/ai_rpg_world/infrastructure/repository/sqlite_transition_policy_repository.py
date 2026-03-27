"""SQLite implementation of transition policy read repository and seeding writer."""

from __future__ import annotations

import sqlite3
from typing import List

from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.repository.transition_policy_repository import (
    ITransitionPolicyRepository,
    ITransitionPolicyWriter,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.transition_condition import (
    BlockIfWeather,
    RequireRelation,
    RequireToll,
    TransitionCondition,
)
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import init_game_write_schema


class SqliteTransitionPolicyRepository(ITransitionPolicyRepository):
    """Store per-edge transition conditions in normalized rows."""

    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(cls, connection: sqlite3.Connection) -> "SqliteTransitionPolicyRepository":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(cls, connection: sqlite3.Connection) -> "SqliteTransitionPolicyRepository":
        return cls(connection, _commits_after_write=False)

    def get_conditions(self, from_spot_id: SpotId, to_spot_id: SpotId) -> List[TransitionCondition]:
        edge = self._conn.execute(
            "SELECT 1 FROM game_transition_policies WHERE from_spot_id = ? AND to_spot_id = ?",
            (int(from_spot_id), int(to_spot_id)),
        ).fetchone()
        if edge is None:
            return []
        rows = self._conn.execute(
            """
            SELECT condition_index, condition_type, amount_gold, recipient_type, recipient_id, relation_type
            FROM game_transition_policy_conditions
            WHERE from_spot_id = ? AND to_spot_id = ?
            ORDER BY condition_index ASC
            """,
            (int(from_spot_id), int(to_spot_id)),
        ).fetchall()
        conditions: List[TransitionCondition] = []
        for row in rows:
            condition_type = str(row["condition_type"])
            if condition_type == "require_toll":
                conditions.append(
                    RequireToll(
                        amount_gold=int(row["amount_gold"]),
                        recipient_type=str(row["recipient_type"]),
                        recipient_id=row["recipient_id"],
                    )
                )
            elif condition_type == "block_if_weather":
                weather_rows = self._conn.execute(
                    """
                    SELECT weather_type
                    FROM game_transition_policy_blocked_weather
                    WHERE from_spot_id = ? AND to_spot_id = ? AND condition_index = ?
                    ORDER BY weather_index ASC
                    """,
                    (int(from_spot_id), int(to_spot_id), int(row["condition_index"])),
                ).fetchall()
                conditions.append(
                    BlockIfWeather(
                        blocked_weather_types=tuple(
                            WeatherTypeEnum(str(weather_row["weather_type"])) for weather_row in weather_rows
                        )
                    )
                )
            elif condition_type == "require_relation":
                conditions.append(RequireRelation(relation_type=str(row["relation_type"])))
            else:
                raise ValueError(f"Unknown transition condition type: {condition_type}")
        return conditions


class SqliteTransitionPolicyWriter(ITransitionPolicyWriter):
    """TransitionPolicy 登録専用の SQLite writer。seed とテスト投入を担当する。"""

    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(cls, connection: sqlite3.Connection) -> "SqliteTransitionPolicyWriter":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(cls, connection: sqlite3.Connection) -> "SqliteTransitionPolicyWriter":
        return cls(connection, _commits_after_write=False)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def _assert_shared_transaction_active(self) -> None:
        if self._commits_after_write:
            return
        if not self._conn.in_transaction:
            raise RuntimeError("for_shared_unit_of_work で生成した writer の書き込みは、アクティブなトランザクション内（with uow）で実行してください")

    def replace_conditions(self, from_spot_id: SpotId, to_spot_id: SpotId, conditions: List[TransitionCondition]) -> None:
        self._assert_shared_transaction_active()
        from_id, to_id = int(from_spot_id), int(to_spot_id)
        self._conn.execute(
            "INSERT INTO game_transition_policies (from_spot_id, to_spot_id) VALUES (?, ?) ON CONFLICT(from_spot_id, to_spot_id) DO NOTHING",
            (from_id, to_id),
        )
        self._conn.execute(
            "DELETE FROM game_transition_policy_conditions WHERE from_spot_id = ? AND to_spot_id = ?",
            (from_id, to_id),
        )
        self._conn.execute(
            "DELETE FROM game_transition_policy_blocked_weather WHERE from_spot_id = ? AND to_spot_id = ?",
            (from_id, to_id),
        )
        for idx, condition in enumerate(conditions):
            if isinstance(condition, RequireToll):
                self._conn.execute(
                    """
                    INSERT INTO game_transition_policy_conditions (
                        from_spot_id, to_spot_id, condition_index, condition_type, amount_gold, recipient_type, recipient_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (from_id, to_id, idx, "require_toll", condition.amount_gold, condition.recipient_type, condition.recipient_id),
                )
            elif isinstance(condition, BlockIfWeather):
                self._conn.execute(
                    """
                    INSERT INTO game_transition_policy_conditions (
                        from_spot_id, to_spot_id, condition_index, condition_type
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (from_id, to_id, idx, "block_if_weather"),
                )
                self._conn.executemany(
                    """
                    INSERT INTO game_transition_policy_blocked_weather (
                        from_spot_id, to_spot_id, condition_index, weather_index, weather_type
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    [(from_id, to_id, idx, weather_idx, weather.value) for weather_idx, weather in enumerate(condition.blocked_weather_types)],
                )
            elif isinstance(condition, RequireRelation):
                self._conn.execute(
                    """
                    INSERT INTO game_transition_policy_conditions (
                        from_spot_id, to_spot_id, condition_index, condition_type, relation_type
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (from_id, to_id, idx, "require_relation", condition.relation_type),
                )
            else:
                raise TypeError(f"Unsupported transition condition type: {type(condition)!r}")
        self._finalize_write()


__all__ = ["SqliteTransitionPolicyRepository", "SqliteTransitionPolicyWriter"]
