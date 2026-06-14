"""``SqliteEpisodicReinterpretationStore`` の being_id 版 API テスト
(Phase 3 Step 3d-1)。

schema v2 で追加した ``*_by_being`` テーブル経由で各 API が動作すること、
および legacy テーブルと独立していることを確認する。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
    EpisodicRecallObservation,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import (
    EpisodicReinterpretationEntry,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_status import (
    EpisodicReinterpretationStatus,
)
from ai_rpg_world.infrastructure.repository.sqlite_episodic_reinterpretation_store import (
    SqliteEpisodicReinterpretationStore,
)


_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _obs(
    *,
    recall_id: str,
    episode_id: str,
    player_id: int = 1,
    recalled_at: datetime = _NOW,
) -> EpisodicRecallObservation:
    return EpisodicRecallObservation(
        recall_id=recall_id,
        player_id=player_id,
        episode_id=episode_id,
        recalled_at=recalled_at,
        source_axes=("temporal",),
        current_state_snapshot="state",
        recent_events_snapshot="events",
        persona_snapshot="persona",
        situation_cues=("cue",),
        turn_index=1,
    )


def _entry(
    *,
    entry_id: str,
    episode_id: str,
    player_id: int = 1,
    created_at: datetime = _NOW,
    status: EpisodicReinterpretationStatus = EpisodicReinterpretationStatus.ACTIVE,
) -> EpisodicReinterpretationEntry:
    return EpisodicReinterpretationEntry(
        entry_id=entry_id,
        player_id=player_id,
        episode_id=episode_id,
        created_at=created_at,
        turn_index=1,
        current_interpretation="reinterp",
        current_recall_text="recall",
        source_recall_ids=("r-1",),
        status=status,
        superseded_at=None,
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "reinterp.db"


@pytest.fixture
def store(db_path: Path) -> SqliteEpisodicReinterpretationStore:
    return SqliteEpisodicReinterpretationStore.connect(str(db_path))


@pytest.fixture
def being() -> BeingId:
    return BeingId("being_w1_p1")


class TestSqliteRecallBufferByBeing:
    """SQLite recall buffer の by_being API。"""

    def test_append_と_pending_count(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        store.append_by_being(being, _obs(recall_id="r1", episode_id="e1"))
        store.append_by_being(being, _obs(recall_id="r2", episode_id="e2"))
        assert store.pending_count_by_being(being) == 2

    def test_peek_batch_は_episode_batched(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        store.append_by_being(being, _obs(recall_id="r1", episode_id="e1"))
        store.append_by_being(
            being,
            _obs(recall_id="r2", episode_id="e2", recalled_at=_NOW + timedelta(seconds=1)),
        )
        result = store.peek_batch_by_being(
            being, batch_size=2, max_contexts_per_episode=5
        )
        assert len(result) == 2
        assert result[0].recall_id == "r1"
        assert result[1].recall_id == "r2"

    def test_mark_processed_は_pending_から_除く(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        store.append_by_being(being, _obs(recall_id="r1", episode_id="e1"))
        store.append_by_being(being, _obs(recall_id="r2", episode_id="e2"))
        store.mark_processed_by_being(being, ("r1",))
        assert store.pending_count_by_being(being) == 1

    def test_batch_size_0_は_空_tuple(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        """``batch_size <= 0`` は早期 return で空 tuple。"""
        store.append_by_being(being, _obs(recall_id="r1", episode_id="e1"))
        assert (
            store.peek_batch_by_being(
                being, batch_size=0, max_contexts_per_episode=5
            )
            == ()
        )

    def test_max_contexts_per_episode_0_は_空_tuple(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        """``max_contexts_per_episode <= 0`` も早期 return で空 tuple。"""
        store.append_by_being(being, _obs(recall_id="r1", episode_id="e1"))
        assert (
            store.peek_batch_by_being(
                being, batch_size=5, max_contexts_per_episode=0
            )
            == ()
        )


class TestSqliteJournalByBeing:
    """SQLite journal の by_being API。"""

    def test_put_active_と_get_active(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        e1 = _entry(entry_id="ent-1", episode_id="ep-1")
        store.put_active_by_being(being, e1)
        got = store.get_active_by_being(being, "ep-1")
        assert got is not None and got.entry_id == "ent-1"

    def test_新しい_active_を_保存すると_旧_active_は_SUPERSEDED(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        e1 = _entry(entry_id="old", episode_id="ep-1")
        e2 = _entry(
            entry_id="new",
            episode_id="ep-1",
            created_at=_NOW + timedelta(minutes=1),
        )
        store.put_active_by_being(being, e1)
        store.put_active_by_being(being, e2)
        got = store.get_active_by_being(being, "ep-1")
        assert got is not None and got.entry_id == "new"
        hist = store.list_by_episode_by_being(being, "ep-1")
        assert len(hist) == 2
        assert any(
            e.status == EpisodicReinterpretationStatus.SUPERSEDED for e in hist
        )


class TestSqliteReinterpretationIsolation:
    """SQLite: 新旧テーブルが独立。"""

    def test_player_id_経由_recall_は_being_id_経由では見えない(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        store.append(_obs(recall_id="legacy-r", episode_id="e1"))
        assert store.pending_count_by_being(being) == 0

    def test_being_id_経由_recall_は_player_id_経由では見えない(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        store.append_by_being(being, _obs(recall_id="new-r", episode_id="e1"))
        assert store.pending_count(1) == 0

    def test_player_id_経由_journal_は_being_id_経由では見えない(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        store.put_active(_entry(entry_id="legacy", episode_id="ep-1"))
        assert store.get_active_by_being(being, "ep-1") is None

    def test_being_id_経由_journal_は_player_id_経由では見えない(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        store.put_active_by_being(being, _entry(entry_id="new", episode_id="ep-1"))
        assert store.get_active(1, "ep-1") is None
