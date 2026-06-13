"""SubjectiveEpisode の SQLite 永続化（MVP エピソード記憶ストア）。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import IEpisodicEpisodeStore
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.infrastructure.repository.sqlite_migration import (
    SqliteMigration,
    apply_migrations,
)

_SUBJECTIVE_EPISODE_SCHEMA_NAMESPACE = "subjective-episodes-mvp-v1"
_PAYLOAD_VERSION = 1


def _occurred_at_sort_key(ep: SubjectiveEpisode) -> float:
    """InMemory ストアの並びと整合する UTC 基準のソートキー（unix 秒・小数）。"""
    dt = ep.occurred_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.timestamp()


def _episode_to_payload_dict(ep: SubjectiveEpisode) -> dict[str, Any]:
    loc = ep.location
    act = ep.action
    return {
        "v": _PAYLOAD_VERSION,
        "episode_id": ep.episode_id,
        "player_id": ep.player_id,
        "occurred_at": ep.occurred_at.isoformat(),
        "game_time_label": ep.game_time_label,
        "source": {"event_ids": list(ep.source.event_ids)},
        "location": {
            "spot_id": loc.spot_id,
            "tile_area_ids": list(loc.tile_area_ids),
            "sub_location_id": loc.sub_location_id,
            "x": loc.x,
            "y": loc.y,
            "z": loc.z,
        },
        "action": None
        if act is None
        else {
            "tool_name": act.tool_name,
            "canonical_arguments_text": act.canonical_arguments_text,
        },
        "who": list(ep.who),
        "what": ep.what,
        "why": ep.why,
        "observed": ep.observed,
        "expected": ep.expected,
        "outcome": ep.outcome,
        "prediction_error": ep.prediction_error,
        "felt": ep.felt,
        "interpreted": ep.interpreted,
        "cues": [
            {"axis": c.axis, "value": c.value, "source": c.source.value} for c in ep.cues
        ],
        "recall_text": ep.recall_text,
        "recall_count": ep.recall_count,
        "last_recalled_at": ep.last_recalled_at.isoformat()
        if ep.last_recalled_at is not None
        else None,
    }


def _payload_dict_to_episode(data: dict[str, Any]) -> SubjectiveEpisode:
    if int(data.get("v", 0)) != _PAYLOAD_VERSION:
        raise ValueError(f"unsupported subjective episode payload v={data.get('v')!r}")
    loc_raw = data["location"]
    loc = EpisodeLocation(
        spot_id=loc_raw.get("spot_id"),
        tile_area_ids=tuple(int(x) for x in loc_raw.get("tile_area_ids", ())),
        sub_location_id=loc_raw.get("sub_location_id"),
        x=loc_raw.get("x"),
        y=loc_raw.get("y"),
        z=loc_raw.get("z"),
    )
    act_raw = data.get("action")
    action: EpisodeAction | None
    if act_raw is None:
        action = None
    else:
        action = EpisodeAction(
            tool_name=str(act_raw["tool_name"]),
            canonical_arguments_text=act_raw.get("canonical_arguments_text"),
        )
    cues_raw = data["cues"]
    cues: list[EpisodicCue] = []
    for item in cues_raw:
        src = EpisodicCueSource(str(item["source"]))
        cues.append(
            EpisodicCue(axis=str(item["axis"]), value=str(item["value"]), source=src)
        )
    occurred_raw = data["occurred_at"]
    if not isinstance(occurred_raw, str):
        raise TypeError("occurred_at must be str in payload")
    occurred_at = datetime.fromisoformat(occurred_raw.replace("Z", "+00:00"))
    return SubjectiveEpisode(
        episode_id=str(data["episode_id"]),
        player_id=int(data["player_id"]),
        occurred_at=occurred_at,
        game_time_label=data.get("game_time_label"),
        source=EpisodeSource(event_ids=tuple(str(x) for x in data["source"]["event_ids"])),
        location=loc,
        action=action,
        who=tuple(str(x) for x in data["who"]),
        what=str(data["what"]),
        why=data.get("why"),
        observed=str(data["observed"]),
        expected=data.get("expected"),
        outcome=str(data["outcome"]),
        prediction_error=data.get("prediction_error"),
        felt=data.get("felt"),
        interpreted=data.get("interpreted"),
        cues=tuple(cues),
        recall_text=data.get("recall_text"),
        recall_count=int(data.get("recall_count", 0)),
        last_recalled_at=(
            datetime.fromisoformat(str(last_raw).replace("Z", "+00:00"))
            if (last_raw := data.get("last_recalled_at")) not in (None, "")
            else None
        ),
    )


def _init_schema_v1(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE subjective_episodes (
            player_id INTEGER NOT NULL,
            episode_id TEXT NOT NULL,
            occurred_at_key REAL NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (player_id, episode_id)
        );
        CREATE INDEX idx_subjective_episodes_player_time
            ON subjective_episodes (player_id, occurred_at_key DESC, episode_id DESC);

        CREATE TABLE subjective_episode_cues (
            player_id INTEGER NOT NULL,
            episode_id TEXT NOT NULL,
            cue_canonical TEXT NOT NULL,
            PRIMARY KEY (player_id, episode_id, cue_canonical)
        );
        CREATE INDEX idx_subjective_episode_cues_lookup
            ON subjective_episode_cues (player_id, cue_canonical);
        """
    )


class SqliteSubjectiveEpisodeStore(IEpisodicEpisodeStore):
    """
    SubjectiveEpisode を JSON 1 行 + cue 逆引きで保持する。
    並びは occurred_at の新しい順（UTC 正規化）・同一キーは episode_id 降順。
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        apply_migrations(
            connection,
            namespace=_SUBJECTIVE_EPISODE_SCHEMA_NAMESPACE,
            migrations=[SqliteMigration(1, _init_schema_v1)],
        )

    @property
    def connection(self) -> sqlite3.Connection:
        """MemoryLink / セマンティック等の同じ SQLite ファイルに同居するストア用の接続。"""
        return self._conn

    @classmethod
    def connect(cls, database_path: str) -> SqliteSubjectiveEpisodeStore:
        conn = sqlite3.connect(database_path, check_same_thread=False)
        store = cls(conn)
        conn.commit()
        return store

    def put(self, episode: SubjectiveEpisode) -> None:
        payload = json.dumps(_episode_to_payload_dict(episode), ensure_ascii=False)
        key = _occurred_at_sort_key(episode)
        pid = episode.player_id
        eid = episode.episode_id
        canonicals = [c.to_canonical() for c in episode.cues]
        cur = self._conn.cursor()
        cur.execute(
            "DELETE FROM subjective_episode_cues WHERE player_id = ? AND episode_id = ?",
            (pid, eid),
        )
        cur.execute(
            """
            INSERT OR REPLACE INTO subjective_episodes
                (player_id, episode_id, occurred_at_key, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (pid, eid, key, payload),
        )
        for ck in canonicals:
            cur.execute(
                """
                INSERT OR IGNORE INTO subjective_episode_cues
                    (player_id, episode_id, cue_canonical)
                VALUES (?, ?, ?)
                """,
                (pid, eid, ck),
            )
        self._conn.commit()

    def get(self, player_id: int, episode_id: str) -> SubjectiveEpisode | None:
        cur = self._conn.execute(
            """
            SELECT payload_json FROM subjective_episodes
            WHERE player_id = ? AND episode_id = ?
            """,
            (player_id, episode_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        data = json.loads(str(row[0]))
        return _payload_dict_to_episode(data)

    def list_recent(self, player_id: int, limit: int) -> list[SubjectiveEpisode]:
        if limit <= 0:
            return []
        cur = self._conn.execute(
            """
            SELECT payload_json FROM subjective_episodes
            WHERE player_id = ?
            ORDER BY occurred_at_key DESC, episode_id DESC
            LIMIT ?
            """,
            (player_id, limit),
        )
        return [_payload_dict_to_episode(json.loads(str(r[0]))) for r in cur.fetchall()]

    def list_by_cue(self, player_id: int, cue: EpisodicCue, limit: int) -> list[SubjectiveEpisode]:
        if limit <= 0:
            return []
        canonical = cue.to_canonical()
        cur = self._conn.execute(
            """
            SELECT e.payload_json
            FROM subjective_episode_cues c
            JOIN subjective_episodes e
              ON e.player_id = c.player_id AND e.episode_id = c.episode_id
            WHERE c.player_id = ? AND c.cue_canonical = ?
            ORDER BY e.occurred_at_key DESC, e.episode_id DESC
            LIMIT ?
            """,
            (player_id, canonical, limit),
        )
        return [_payload_dict_to_episode(json.loads(str(r[0]))) for r in cur.fetchall()]
