"""SqliteEpisodicReinterpretationStore の roundtrip 検証。"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile

from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import EpisodicRecallObservation
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import EpisodicReinterpretationEntry
from ai_rpg_world.infrastructure.repository.sqlite_episodic_reinterpretation_store import (
    SqliteEpisodicReinterpretationStore,
)


def _recall(recall_id: str, episode_id: str, at: datetime) -> EpisodicRecallObservation:
    return EpisodicRecallObservation(
        recall_id=recall_id,
        player_id=7,
        episode_id=episode_id,
        recalled_at=at,
        source_axes=("temporal",),
        current_state_snapshot="state",
        recent_events_snapshot="events",
        persona_snapshot="persona",
        situation_cues=("place_spot:1",),
        turn_index=3,
    )


class TestSqliteEpisodicReinterpretationStore:
    """recall buffer と active journal の SQLite 永続化。"""

    def test_recall_buffer_roundtrip_and_mark_processed(self) -> None:
        """Phase 3 Step 3d-3: being_id keyed only。"""
        from ai_rpg_world.domain.being.value_object.being_id import BeingId

        being_id = BeingId("being_w1_p7")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "memory.db")
            base = datetime(2026, 5, 4, tzinfo=timezone.utc)
            store = SqliteEpisodicReinterpretationStore.connect(path)
            store.append_by_being(being_id, _recall("r1", "ep-a", base))
            store.append_by_being(
                being_id, _recall("r2", "ep-a", base + timedelta(minutes=1))
            )
            del store

            reopened = SqliteEpisodicReinterpretationStore.connect(path)
            batch = reopened.peek_batch_by_being(
                being_id, batch_size=8, max_contexts_per_episode=1
            )
            assert [r.recall_id for r in batch] == ["r1"]
            assert reopened.pending_count_by_being(being_id) == 2
            reopened.mark_processed_by_being(being_id, ("r1",))
            assert reopened.pending_count_by_being(being_id) == 1

    def test_put_active_supersedes_previous_after_reopen(self) -> None:
        """Phase 3 Step 3d-3: being_id keyed only。"""
        from ai_rpg_world.domain.being.value_object.being_id import BeingId

        being_id = BeingId("being_w1_p7")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "memory.db")
            base = datetime(2026, 5, 4, tzinfo=timezone.utc)
            store = SqliteEpisodicReinterpretationStore.connect(path)
            store.put_active_by_being(
                being_id,
                EpisodicReinterpretationEntry(
                    entry_id="j1",
                    player_id=7,
                    episode_id="ep-a",
                    created_at=base,
                    turn_index=1,
                    current_interpretation="古い意味。",
                    current_recall_text="古い回想。",
                    source_recall_ids=("r1",),
                ),
            )
            store.put_active_by_being(
                being_id,
                EpisodicReinterpretationEntry(
                    entry_id="j2",
                    player_id=7,
                    episode_id="ep-a",
                    created_at=base + timedelta(minutes=1),
                    turn_index=2,
                    current_interpretation="新しい意味。",
                    current_recall_text="新しい回想。",
                    source_recall_ids=("r2",),
                ),
            )
            del store

            reopened = SqliteEpisodicReinterpretationStore.connect(path)
            active = reopened.get_active_by_being(being_id, "ep-a")
            assert active is not None
            assert active.entry_id == "j2"
            history = reopened.list_by_episode_by_being(being_id, "ep-a")
            assert [entry.entry_id for entry in history] == ["j2", "j1"]
            assert history[1].status.value == "superseded"
