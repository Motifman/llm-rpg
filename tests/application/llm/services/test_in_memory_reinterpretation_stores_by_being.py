"""``InMemoryEpisodicRecallBufferStore`` / ``InMemoryEpisodicReinterpretationJournalStore``
の being_id 版 API テスト (Phase 3 Step 3d-1)。

並走追加された ``*_by_being`` メソッド群が legacy player_id 版と互いに見え
ないことと、各メソッドが期待通り動くことを確認する。memo / semantic /
memory_link と同じパターン。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
    InMemoryEpisodicRecallBufferStore,
    InMemoryEpisodicReinterpretationJournalStore,
)
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
def being() -> BeingId:
    return BeingId("being_w1_p1")


class TestRecallBufferByBeing:
    """``InMemoryEpisodicRecallBufferStore`` の by_being API。"""

    def test_append_と_pending_count(self, being: BeingId) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(being, _obs(recall_id="r1", episode_id="e1"))
        store.append_by_being(being, _obs(recall_id="r2", episode_id="e2"))
        assert store.pending_count_by_being(being) == 2

    def test_peek_batch_は_episode_batched_順序を保つ(self, being: BeingId) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(
            being, _obs(recall_id="r1", episode_id="e1", recalled_at=_NOW)
        )
        store.append_by_being(
            being,
            _obs(
                recall_id="r2",
                episode_id="e2",
                recalled_at=_NOW + timedelta(seconds=1),
            ),
        )
        result = store.peek_batch_by_being(
            being, batch_size=2, max_contexts_per_episode=5
        )
        assert len(result) == 2
        assert result[0].recall_id == "r1"
        assert result[1].recall_id == "r2"

    def test_peek_batch_は_batch_size_を_守る(self, being: BeingId) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        for i in range(5):
            store.append_by_being(
                being,
                _obs(
                    recall_id=f"r{i}",
                    episode_id=f"e{i}",
                    recalled_at=_NOW + timedelta(seconds=i),
                ),
            )
        result = store.peek_batch_by_being(
            being, batch_size=2, max_contexts_per_episode=5
        )
        episodes = {r.episode_id for r in result}
        assert len(episodes) == 2

    def test_mark_processed_は_pending_から_除く(self, being: BeingId) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(being, _obs(recall_id="r1", episode_id="e1"))
        store.append_by_being(being, _obs(recall_id="r2", episode_id="e2"))
        store.mark_processed_by_being(being, ("r1",))
        assert store.pending_count_by_being(being) == 1

    def test_型違反は_TypeError(self) -> None:
        store = InMemoryEpisodicRecallBufferStore()
        with pytest.raises(TypeError, match="being_id"):
            store.append_by_being("not-being", _obs(recall_id="r", episode_id="e"))  # type: ignore[arg-type]

    def test_batch_size_0_は_空_tuple(self, being: BeingId) -> None:
        """``batch_size <= 0`` は早期 return で空 tuple (= disabled 経路)。"""
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(being, _obs(recall_id="r1", episode_id="e1"))
        assert (
            store.peek_batch_by_being(
                being, batch_size=0, max_contexts_per_episode=5
            )
            == ()
        )

    def test_max_contexts_per_episode_0_は_空_tuple(self, being: BeingId) -> None:
        """``max_contexts_per_episode <= 0`` も早期 return で空 tuple。"""
        store = InMemoryEpisodicRecallBufferStore()
        store.append_by_being(being, _obs(recall_id="r1", episode_id="e1"))
        assert (
            store.peek_batch_by_being(
                being, batch_size=5, max_contexts_per_episode=0
            )
            == ()
        )


# Phase 3 Step 3d-3 (Issue #470): legacy player_id 版 API が撤去されたため、
# 旧/新 API の独立性を検証していたテストクラス ``TestRecallBufferIsolation``
# は削除された。新 API のみが残り、being_id を一次キーとして扱う設計に統一。


class TestJournalByBeing:
    """``InMemoryEpisodicReinterpretationJournalStore`` の by_being API。"""

    def test_put_active_と_get_active(self, being: BeingId) -> None:
        store = InMemoryEpisodicReinterpretationJournalStore()
        e1 = _entry(entry_id="ent-1", episode_id="ep-1")
        store.put_active_by_being(being, e1)
        got = store.get_active_by_being(being, "ep-1")
        assert got is not None
        assert got.entry_id == "ent-1"

    def test_新しい_active_を_保存すると_旧_active_は_superseded(
        self, being: BeingId
    ) -> None:
        store = InMemoryEpisodicReinterpretationJournalStore()
        e1 = _entry(entry_id="old", episode_id="ep-1")
        e2 = _entry(
            entry_id="new",
            episode_id="ep-1",
            created_at=_NOW + timedelta(minutes=1),
        )
        store.put_active_by_being(being, e1)
        store.put_active_by_being(being, e2)
        # 新しい active のみ get_active で返る
        got = store.get_active_by_being(being, "ep-1")
        assert got is not None and got.entry_id == "new"
        # 履歴には 2 件
        hist = store.list_by_episode_by_being(being, "ep-1")
        assert len(hist) == 2
        # 1 件は SUPERSEDED
        assert any(
            e.status == EpisodicReinterpretationStatus.SUPERSEDED for e in hist
        )

    def test_put_active_に_非_ACTIVE_を_渡すと_ValueError(self, being: BeingId) -> None:
        store = InMemoryEpisodicReinterpretationJournalStore()
        bad = _entry(
            entry_id="bad",
            episode_id="ep-1",
            status=EpisodicReinterpretationStatus.SUPERSEDED,
        )
        with pytest.raises(ValueError, match="active"):
            store.put_active_by_being(being, bad)

    def test_型違反は_TypeError(self) -> None:
        store = InMemoryEpisodicReinterpretationJournalStore()
        with pytest.raises(TypeError, match="being_id"):
            store.put_active_by_being(
                "not-being",  # type: ignore[arg-type]
                _entry(entry_id="x", episode_id="ep"),
            )


# Phase 3 Step 3d-3 (Issue #470): legacy player_id 版 API 撤去に伴い
# ``TestJournalIsolation`` も削除済。新 API only に統一。
