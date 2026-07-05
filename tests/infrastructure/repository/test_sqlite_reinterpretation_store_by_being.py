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
    prediction_context_id: str | None = None,
    prediction_outcome_error: str | None = None,
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
        prediction_context_id=prediction_context_id,
        prediction_outcome_error=prediction_outcome_error,
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


class TestSqliteRecallBufferStampPredictionOutcome:
    """U9a: SQLite 版 ``stamp_prediction_outcome_by_being``。"""

    def test_一致する_prediction_context_id_の未処理_obs_に誤差が載る(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        store.append_by_being(
            being,
            _obs(recall_id="r1", episode_id="e1", prediction_context_id="pc-1"),
        )
        store.stamp_prediction_outcome_by_being(being, "pc-1", "外れた")
        got = store.list_pending_by_being(being)[0]
        assert got.prediction_outcome_error == "外れた"

    def test_別の_prediction_context_id_の_obs_には載らない(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        store.append_by_being(
            being,
            _obs(recall_id="r1", episode_id="e1", prediction_context_id="pc-1"),
        )
        store.append_by_being(
            being,
            _obs(recall_id="r2", episode_id="e2", prediction_context_id="pc-2"),
        )
        store.stamp_prediction_outcome_by_being(being, "pc-1", "外れた")
        rows = {o.recall_id: o for o in store.list_pending_by_being(being)}
        assert rows["r1"].prediction_outcome_error == "外れた"
        assert rows["r2"].prediction_outcome_error is None

    def test_既に誤差が刻まれた_obs_は上書きしない(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        store.append_by_being(
            being,
            _obs(
                recall_id="r1",
                episode_id="e1",
                prediction_context_id="pc-1",
                prediction_outcome_error="最初の誤差",
            ),
        )
        store.stamp_prediction_outcome_by_being(being, "pc-1", "二度目の誤差")
        got = store.list_pending_by_being(being)[0]
        assert got.prediction_outcome_error == "最初の誤差"


class TestSqliteListEpisodeIdsByPredictionContext:
    """U9b: SQLite 版 ``list_episode_ids_by_prediction_context_by_being``。"""

    def test_一致する_prediction_context_id_の_episode_id_を返す(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        store.append_by_being(
            being,
            _obs(recall_id="r1", episode_id="e1", prediction_context_id="pc-1"),
        )
        got = store.list_episode_ids_by_prediction_context_by_being(being, "pc-1")
        assert got == ("e1",)

    def test_複数_episode_が_同じ_prediction_context_id_に紐づく場合は全件返す(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        store.append_by_being(
            being,
            _obs(recall_id="r1", episode_id="e1", prediction_context_id="pc-1"),
        )
        store.append_by_being(
            being,
            _obs(recall_id="r2", episode_id="e2", prediction_context_id="pc-1"),
        )
        got = store.list_episode_ids_by_prediction_context_by_being(being, "pc-1")
        assert set(got) == {"e1", "e2"}

    def test_同じ_episode_を複数_recall_しても重複排除される(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        store.append_by_being(
            being,
            _obs(recall_id="r1", episode_id="e1", prediction_context_id="pc-1"),
        )
        store.append_by_being(
            being,
            _obs(recall_id="r2", episode_id="e1", prediction_context_id="pc-1"),
        )
        got = store.list_episode_ids_by_prediction_context_by_being(being, "pc-1")
        assert got == ("e1",)

    def test_一致するものが無ければ空tuple(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        store.append_by_being(
            being,
            _obs(recall_id="r1", episode_id="e1", prediction_context_id="pc-1"),
        )
        got = store.list_episode_ids_by_prediction_context_by_being(
            being, "pc-nonexistent"
        )
        assert got == ()


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


# Phase 3 Step 3d-3 (Issue #470): legacy player_id 版テーブルは schema v3 で
# DROP され、対応する API も撤去された。新旧テーブル独立性検証はもはや意味を
# 持たない。schema v3 で legacy テーブルが消えていることは下記テストでカバー。


class TestSqliteV3DropLegacy:
    """schema v3 で legacy 2 テーブルが DROP されている回帰防止。"""

    def test_legacy_recall_observations_table_is_dropped(
        self, store: SqliteEpisodicReinterpretationStore
    ) -> None:
        rows = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row["name"] for row in rows}
        assert "episodic_recall_observations" not in table_names

    def test_legacy_journal_table_is_dropped(
        self, store: SqliteEpisodicReinterpretationStore
    ) -> None:
        rows = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row["name"] for row in rows}
        assert "episodic_reinterpretation_journal" not in table_names


class TestSqliteRecallBufferReplaceAll:
    """Phase 4 Step 4-2a: list_pending_by_being / replace_all_pending_by_being。"""

    def test_replace_all_pending_で全置換(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        store.append_by_being(being, _obs(recall_id="old", episode_id="e1"))
        store.replace_all_pending_by_being(
            being, [_obs(recall_id="new", episode_id="e2")]
        )
        listed = store.list_pending_by_being(being)
        assert [o.recall_id for o in listed] == ["new"]

    def test_他_being_は影響しない(
        self, store: SqliteEpisodicReinterpretationStore
    ) -> None:
        ada = BeingId("being_w1_p1")
        ben = BeingId("being_w1_p2")
        store.append_by_being(ada, _obs(recall_id="r-ada", episode_id="e1"))
        store.append_by_being(ben, _obs(recall_id="r-ben", episode_id="e2"))
        store.replace_all_pending_by_being(ada, [])
        ids = [o.recall_id for o in store.list_pending_by_being(ben)]
        assert ids == ["r-ben"]


class TestSqliteJournalReplaceAll:
    """Phase 4 Step 4-2a: list_all_by_being / replace_all_by_being。"""

    def test_list_all_by_being_は全episode横断(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        store.put_active_by_being(being, _entry(entry_id="a", episode_id="ep-1"))
        store.put_active_by_being(being, _entry(entry_id="b", episode_id="ep-2"))
        ids = [e.entry_id for e in store.list_all_by_being(being)]
        assert set(ids) == {"a", "b"}

    def test_replace_all_で_active_get_に整合する(
        self, store: SqliteEpisodicReinterpretationStore, being: BeingId
    ) -> None:
        """status=ACTIVE の entry を replace で持ち込めば get_active_by_being で引ける。"""
        store.put_active_by_being(being, _entry(entry_id="old", episode_id="ep-1"))
        new = _entry(entry_id="new", episode_id="ep-1")
        store.replace_all_by_being(being, [new])
        got = store.get_active_by_being(being, "ep-1")
        assert got is not None
        assert got.entry_id == "new"
