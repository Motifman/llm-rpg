"""SubjectiveEpisode の SQLite 永続化（MVP エピソード記憶ストア）。

Phase 3 Step 3e-1 (Issue #470): being_id 版 API を並走追加。書き込み先は
``subjective_episodes_by_being`` / ``subjective_episode_cues_by_being``
(= schema v2)。legacy テーブルは Step 3e-3 で DROP 予定。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import EpisodicEpisodeRepository
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


def _datetime_to_occurred_at_key(dt: datetime) -> float:
    """``datetime`` を ``occurred_at_key`` の表現 (UTC 秒) に揃える (PR5)。

    返り値は 64-bit float (IEEE 754) で、現在世代 (2026 年付近) では
    マイクロ秒精度を保てる。``.timestamp()`` の戻りは ``occurred_at_key``
    column と同じスケールなので、SQL の ``WHERE occurred_at_key < ?`` 比較は
    insert 時の格納値とビット同一の精度になる。境界 episode 自身は ``<``
    で除外されるので、float 端数によって境界判定がブレるリスクは無視できる。
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).timestamp()
    return dt.astimezone(timezone.utc).timestamp()


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
        # U6 (予測誤差統一設計 / salience): payload は JSON blob (payload_json
        # 列) なので ALTER TABLE 不要。旧行は "salience" キーを持たないため
        # decode 側の data.get("salience", "low") だけで後方互換が成立する。
        "salience": ep.salience,
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
        # U6: 旧行 (salience キー無し) は "low" に倒す。
        salience=str(data.get("salience", "low")),
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


def _init_schema_v3_drop_legacy(connection: sqlite3.Connection) -> None:
    """Phase 3 Step 3e-3: legacy player_id keyed の 2 テーブルを撤去。

    Step 3e-2 で全 caller が ``*_by_being`` API に切り替わったため、player_id
    keyed の旧テーブル/インデックスは参照されなくなった。schema migration で
    DROP して DB ファイル上にも残らないようにする。semantic v3 /
    memory_link v5 / reinterpretation v3 と同型。
    """
    connection.executescript(
        """
        DROP INDEX IF EXISTS idx_subjective_episodes_player_time;
        DROP INDEX IF EXISTS idx_subjective_episode_cues_lookup;
        DROP TABLE IF EXISTS subjective_episode_cues;
        DROP TABLE IF EXISTS subjective_episodes;
        """
    )


def _init_schema_v2_by_being(connection: sqlite3.Connection) -> None:
    """Phase 3 Step 3e-1: being_id keyed の並走テーブルを追加。

    legacy テーブルはそのまま残し、新 API は本 v2 テーブルに書き込む
    (= caller 移行 = Step 3e-2 後、Step 3e-3 で legacy テーブルごと撤去予定)。
    semantic / memory_link / reinterpretation の by_being テーブルと同型。

    ``player_id`` 列を本テーブルにも残す理由は ``payload_json`` の中にも
    ``player_id`` がエンコードされているが、SQL WHERE で player_id 絞り込み
    したい運用 (= 監査・デバッグ) を高速化するため。
    """
    connection.executescript(
        """
        CREATE TABLE subjective_episodes_by_being (
            being_id_value TEXT NOT NULL,
            episode_id TEXT NOT NULL,
            occurred_at_key REAL NOT NULL,
            payload_json TEXT NOT NULL,
            player_id INTEGER NOT NULL,
            PRIMARY KEY (being_id_value, episode_id)
        );
        CREATE INDEX idx_subjective_episodes_by_being_time
            ON subjective_episodes_by_being
                (being_id_value, occurred_at_key DESC, episode_id DESC);

        CREATE TABLE subjective_episode_cues_by_being (
            being_id_value TEXT NOT NULL,
            episode_id TEXT NOT NULL,
            cue_canonical TEXT NOT NULL,
            PRIMARY KEY (being_id_value, episode_id, cue_canonical)
        );
        CREATE INDEX idx_subjective_episode_cues_by_being_lookup
            ON subjective_episode_cues_by_being (being_id_value, cue_canonical);
        """
    )


class SqliteSubjectiveEpisodeStore(EpisodicEpisodeRepository):
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
            migrations=[
                SqliteMigration(1, _init_schema_v1),
                SqliteMigration(2, _init_schema_v2_by_being),
                SqliteMigration(3, _init_schema_v3_drop_legacy),
            ],
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

    def put_by_being(self, being_id: BeingId, episode: SubjectiveEpisode) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(episode, SubjectiveEpisode):
            raise TypeError("episode must be SubjectiveEpisode")
        payload = json.dumps(_episode_to_payload_dict(episode), ensure_ascii=False)
        key = _occurred_at_sort_key(episode)
        eid = episode.episode_id
        canonicals = [c.to_canonical() for c in episode.cues]
        cur = self._conn.cursor()
        cur.execute(
            """
            DELETE FROM subjective_episode_cues_by_being
            WHERE being_id_value = ? AND episode_id = ?
            """,
            (being_id.value, eid),
        )
        cur.execute(
            """
            INSERT OR REPLACE INTO subjective_episodes_by_being
                (being_id_value, episode_id, occurred_at_key, payload_json, player_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (being_id.value, eid, key, payload, episode.player_id),
        )
        for ck in canonicals:
            cur.execute(
                """
                INSERT OR IGNORE INTO subjective_episode_cues_by_being
                    (being_id_value, episode_id, cue_canonical)
                VALUES (?, ?, ?)
                """,
                (being_id.value, eid, ck),
            )
        self._conn.commit()

    def get_by_being(
        self, being_id: BeingId, episode_id: str
    ) -> SubjectiveEpisode | None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        cur = self._conn.execute(
            """
            SELECT payload_json FROM subjective_episodes_by_being
            WHERE being_id_value = ? AND episode_id = ?
            """,
            (being_id.value, episode_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _payload_dict_to_episode(json.loads(str(row[0])))

    def list_recent_by_being(
        self,
        being_id: BeingId,
        limit: int,
        min_occurred_at: datetime | None = None,
    ) -> list[SubjectiveEpisode]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if limit <= 0:
            return []
        if min_occurred_at is None:
            cur = self._conn.execute(
                """
                SELECT payload_json FROM subjective_episodes_by_being
                WHERE being_id_value = ?
                ORDER BY occurred_at_key DESC, episode_id DESC
                LIMIT ?
                """,
                (being_id.value, limit),
            )
        else:
            border_key = _datetime_to_occurred_at_key(min_occurred_at)
            cur = self._conn.execute(
                """
                SELECT payload_json FROM subjective_episodes_by_being
                WHERE being_id_value = ?
                  AND occurred_at_key < ?
                ORDER BY occurred_at_key DESC, episode_id DESC
                LIMIT ?
                """,
                (being_id.value, border_key, limit),
            )
        return [_payload_dict_to_episode(json.loads(str(r[0]))) for r in cur.fetchall()]

    def list_by_cue_by_being(
        self,
        being_id: BeingId,
        cue: EpisodicCue,
        limit: int,
        min_occurred_at: datetime | None = None,
    ) -> list[SubjectiveEpisode]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if limit <= 0:
            return []
        canonical = cue.to_canonical()
        if min_occurred_at is None:
            cur = self._conn.execute(
                """
                SELECT e.payload_json
                FROM subjective_episode_cues_by_being c
                JOIN subjective_episodes_by_being e
                  ON e.being_id_value = c.being_id_value AND e.episode_id = c.episode_id
                WHERE c.being_id_value = ? AND c.cue_canonical = ?
                ORDER BY e.occurred_at_key DESC, e.episode_id DESC
                LIMIT ?
                """,
                (being_id.value, canonical, limit),
            )
        else:
            border_key = _datetime_to_occurred_at_key(min_occurred_at)
            cur = self._conn.execute(
                """
                SELECT e.payload_json
                FROM subjective_episode_cues_by_being c
                JOIN subjective_episodes_by_being e
                  ON e.being_id_value = c.being_id_value AND e.episode_id = c.episode_id
                WHERE c.being_id_value = ? AND c.cue_canonical = ?
                  AND e.occurred_at_key < ?
                ORDER BY e.occurred_at_key DESC, e.episode_id DESC
                LIMIT ?
                """,
                (being_id.value, canonical, border_key, limit),
            )
        return [_payload_dict_to_episode(json.loads(str(r[0]))) for r in cur.fetchall()]

    def list_all_by_being(self, being_id: BeingId) -> list[SubjectiveEpisode]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        cur = self._conn.execute(
            """
            SELECT payload_json FROM subjective_episodes_by_being
            WHERE being_id_value = ?
            ORDER BY occurred_at_key ASC, episode_id ASC
            """,
            (being_id.value,),
        )
        return [
            _payload_dict_to_episode(json.loads(str(r[0])))
            for r in cur.fetchall()
        ]

    def replace_all_by_being(
        self, being_id: BeingId, episodes: list[SubjectiveEpisode]
    ) -> None:
        """being_id 配下を ``episodes`` で完全置換する (single transaction)。

        Phase 4 Step 4-2a: snapshot restore primitive。cue index も整合する
        形で再構築する。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(episodes, list):
            raise TypeError("episodes must be list")
        for ep in episodes:
            if not isinstance(ep, SubjectiveEpisode):
                raise TypeError("episodes elements must be SubjectiveEpisode")
        # 注意: 明示的 BEGIN は打たない (implicit transaction との衝突回避)。
        # 詳細は sqlite_semantic_memory_store.py の同コメント参照。
        try:
            cur = self._conn.cursor()
            cur.execute(
                "DELETE FROM subjective_episode_cues_by_being WHERE being_id_value = ?",
                (being_id.value,),
            )
            cur.execute(
                "DELETE FROM subjective_episodes_by_being WHERE being_id_value = ?",
                (being_id.value,),
            )
            for ep in episodes:
                payload = json.dumps(
                    _episode_to_payload_dict(ep), ensure_ascii=False
                )
                key = _occurred_at_sort_key(ep)
                cur.execute(
                    """
                    INSERT INTO subjective_episodes_by_being
                        (being_id_value, episode_id, occurred_at_key, payload_json, player_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (being_id.value, ep.episode_id, key, payload, ep.player_id),
                )
                for ck in (c.to_canonical() for c in ep.cues):
                    cur.execute(
                        """
                        INSERT OR IGNORE INTO subjective_episode_cues_by_being
                            (being_id_value, episode_id, cue_canonical)
                        VALUES (?, ?, ?)
                        """,
                        (being_id.value, ep.episode_id, ck),
                    )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
