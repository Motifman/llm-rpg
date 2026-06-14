"""``SqliteSubjectiveEpisodeStore`` の being_id 版 API テスト
(Phase 3 Step 3e-1)。

schema v2 で追加した ``*_by_being`` テーブル経由で各 API が動作すること、
および legacy テーブルと独立していることを確認する。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import (
    EpisodicCueSource,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
from ai_rpg_world.infrastructure.repository.sqlite_subjective_episode_store import (
    SqliteSubjectiveEpisodeStore,
)


_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _episode(
    *,
    episode_id: str,
    player_id: int = 1,
    occurred_at: datetime = _NOW,
    cues: tuple[EpisodicCue, ...] = (),
) -> SubjectiveEpisode:
    if not cues:
        cues = (
            EpisodicCue(
                axis="place_spot", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT
            ),
        )
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=player_id,
        occurred_at=occurred_at,
        game_time_label="12:00",
        source=EpisodeSource(event_ids=("e1",)),
        location=EpisodeLocation(spot_id=1),
        action=EpisodeAction(tool_name="x"),
        who=(),
        what="w",
        why=None,
        observed="o",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted="i",
        cues=cues,
        recall_text="r",
        recall_count=0,
        last_recalled_at=None,
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "ep.db"


@pytest.fixture
def store(db_path: Path) -> SqliteSubjectiveEpisodeStore:
    return SqliteSubjectiveEpisodeStore.connect(str(db_path))


@pytest.fixture
def being() -> BeingId:
    return BeingId("being_w1_p1")


class TestSqliteByBeingBasic:
    """put / get / list_recent / list_by_cue の SQLite 永続化挙動。"""

    def test_put_と_get(
        self, store: SqliteSubjectiveEpisodeStore, being: BeingId
    ) -> None:
        ep = _episode(episode_id="e1")
        store.put_by_being(being, ep)
        got = store.get_by_being(being, "e1")
        assert got is not None and got.episode_id == "e1"

    def test_list_recent_は_occurred_at_降順(
        self, store: SqliteSubjectiveEpisodeStore, being: BeingId
    ) -> None:
        store.put_by_being(being, _episode(episode_id="old", occurred_at=_NOW - timedelta(hours=1)))
        store.put_by_being(being, _episode(episode_id="new", occurred_at=_NOW))
        result = store.list_recent_by_being(being, limit=10)
        assert [ep.episode_id for ep in result] == ["new", "old"]

    def test_list_by_cue_は_canonical_一致(
        self, store: SqliteSubjectiveEpisodeStore, being: BeingId
    ) -> None:
        cue_a = EpisodicCue(
            axis="entity", value="alice", source=EpisodicCueSource.RUNTIME_CONTEXT
        )
        cue_b = EpisodicCue(
            axis="entity", value="bob", source=EpisodicCueSource.RUNTIME_CONTEXT
        )
        store.put_by_being(being, _episode(episode_id="ea", cues=(cue_a,)))
        store.put_by_being(being, _episode(episode_id="eb", cues=(cue_b,)))
        result = store.list_by_cue_by_being(being, cue_a, limit=10)
        assert [ep.episode_id for ep in result] == ["ea"]

    def test_cue_index_は_put_で_更新される(
        self, store: SqliteSubjectiveEpisodeStore, being: BeingId
    ) -> None:
        cue_old = EpisodicCue(
            axis="entity", value="old", source=EpisodicCueSource.RUNTIME_CONTEXT
        )
        cue_new = EpisodicCue(
            axis="entity", value="new", source=EpisodicCueSource.RUNTIME_CONTEXT
        )
        store.put_by_being(being, _episode(episode_id="e1", cues=(cue_old,)))
        store.put_by_being(being, _episode(episode_id="e1", cues=(cue_new,)))
        assert store.list_by_cue_by_being(being, cue_old, limit=10) == []
        assert len(store.list_by_cue_by_being(being, cue_new, limit=10)) == 1

    def test_limit_0_以下は_空_list(
        self, store: SqliteSubjectiveEpisodeStore, being: BeingId
    ) -> None:
        """``limit <= 0`` は SQL 発行前に早期 return (= InMemory 側と挙動一致)。"""
        ep = _episode(episode_id="e1")
        store.put_by_being(being, ep)
        cue = ep.cues[0]
        assert store.list_recent_by_being(being, limit=0) == []
        assert store.list_recent_by_being(being, limit=-1) == []
        assert store.list_by_cue_by_being(being, cue, limit=0) == []


# Phase 3 Step 3e-3 (Issue #470): legacy player_id 版 API + テーブル撤去に
# 伴い、独立性検証は不要 (schema v3 で legacy 2 テーブルが DROP されたこと
# は別途回帰テストで確認)。


class TestSqliteV3DropLegacy:
    """schema v3 で legacy 2 テーブルが DROP されている回帰防止。"""

    def test_legacy_subjective_episodes_table_is_dropped(
        self, store: SqliteSubjectiveEpisodeStore
    ) -> None:
        rows = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row["name"] for row in rows}
        assert "subjective_episodes" not in table_names

    def test_legacy_subjective_episode_cues_table_is_dropped(
        self, store: SqliteSubjectiveEpisodeStore
    ) -> None:
        rows = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row["name"] for row in rows}
        assert "subjective_episode_cues" not in table_names


class TestSqliteByBeingPersistence:
    """SQLite を再接続しても being_id 経路のデータが残る。"""

    def test_再接続後も_episode_が_残る(
        self, db_path: Path, being: BeingId
    ) -> None:
        store = SqliteSubjectiveEpisodeStore.connect(str(db_path))
        store.put_by_being(being, _episode(episode_id="persistent"))
        del store

        reopened = SqliteSubjectiveEpisodeStore.connect(str(db_path))
        got = reopened.get_by_being(being, "persistent")
        assert got is not None
        assert got.episode_id == "persistent"
