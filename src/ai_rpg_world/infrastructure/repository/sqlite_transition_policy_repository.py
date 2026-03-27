"""SQLite implementation of transition policy read repository and seeding writer."""

from __future__ import annotations

import json
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
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)


def _condition_to_payload(condition: TransitionCondition) -> dict:
    if isinstance(condition, RequireToll):
        return {
            "type": "require_toll",
            "amount_gold": condition.amount_gold,
            "recipient_type": condition.recipient_type,
            "recipient_id": condition.recipient_id,
        }
    if isinstance(condition, BlockIfWeather):
        return {
            "type": "block_if_weather",
            "blocked_weather_types": [
                weather.value for weather in condition.blocked_weather_types
            ],
        }
    if isinstance(condition, RequireRelation):
        return {
            "type": "require_relation",
            "relation_type": condition.relation_type,
        }
    raise TypeError(f"Unsupported transition condition type: {type(condition)!r}")


def _payload_to_condition(payload: dict) -> TransitionCondition:
    condition_type = payload["type"]
    if condition_type == "require_toll":
        return RequireToll(
            amount_gold=int(payload["amount_gold"]),
            recipient_type=str(payload.get("recipient_type", "spot")),
            recipient_id=payload.get("recipient_id"),
        )
    if condition_type == "block_if_weather":
        values = payload.get("blocked_weather_types", [])
        return BlockIfWeather(
            blocked_weather_types=tuple(WeatherTypeEnum(value) for value in values)
        )
    if condition_type == "require_relation":
        return RequireRelation(relation_type=str(payload["relation_type"]))
    raise ValueError(f"Unknown transition condition type: {condition_type}")


class SqliteTransitionPolicyRepository(ITransitionPolicyRepository):
    """Store per-edge transition conditions in JSON."""

    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls, connection: sqlite3.Connection
    ) -> "SqliteTransitionPolicyRepository":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls, connection: sqlite3.Connection
    ) -> "SqliteTransitionPolicyRepository":
        return cls(connection, _commits_after_write=False)

    def get_conditions(
        self, from_spot_id: SpotId, to_spot_id: SpotId
    ) -> List[TransitionCondition]:
        cur = self._conn.execute(
            """
            SELECT payload_json
            FROM game_transition_policies
            WHERE from_spot_id = ? AND to_spot_id = ?
            """,
            (int(from_spot_id), int(to_spot_id)),
        )
        row = cur.fetchone()
        if row is None:
            return []
        payload = json.loads(str(row["payload_json"]))
        return [_payload_to_condition(item) for item in payload]

class SqliteTransitionPolicyWriter(ITransitionPolicyWriter):
    """TransitionPolicy 登録専用の SQLite writer。seed とテスト投入を担当する。"""

    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls, connection: sqlite3.Connection
    ) -> "SqliteTransitionPolicyWriter":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls, connection: sqlite3.Connection
    ) -> "SqliteTransitionPolicyWriter":
        return cls(connection, _commits_after_write=False)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def _assert_shared_transaction_active(self) -> None:
        if self._commits_after_write:
            return
        if not self._conn.in_transaction:
            raise RuntimeError(
                "for_shared_unit_of_work で生成した writer の書き込みは、"
                "アクティブなトランザクション内（with uow）で実行してください"
            )

    def replace_conditions(
        self,
        from_spot_id: SpotId,
        to_spot_id: SpotId,
        conditions: List[TransitionCondition],
    ) -> None:
        self._assert_shared_transaction_active()
        payload_json = json.dumps(
            [_condition_to_payload(condition) for condition in conditions],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        self._conn.execute(
            """
            INSERT INTO game_transition_policies (from_spot_id, to_spot_id, payload_json)
            VALUES (?, ?, ?)
            ON CONFLICT(from_spot_id, to_spot_id) DO UPDATE SET
                payload_json = excluded.payload_json
            """,
            (int(from_spot_id), int(to_spot_id), payload_json),
        )
        self._finalize_write()


__all__ = [
    "SqliteTransitionPolicyRepository",
    "SqliteTransitionPolicyWriter",
]
