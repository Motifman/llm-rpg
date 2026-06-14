"""SqliteSubjectiveEpisodeStore の契約テスト（InMemory と同等の振る舞いの一部）。"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.infrastructure.repository.sqlite_subjective_episode_store import (
    SqliteSubjectiveEpisodeStore,
)


def _episode(
    *,
    episode_id: str = "ep-1",
    player_id: int = 7,
    occurred_at: datetime | None = None,
    cues: tuple[EpisodicCue, ...] | None = None,
    recall_text: str = "r",
) -> SubjectiveEpisode:
    ts = occurred_at or datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)
    cue_list = cues or (
        EpisodicCue(axis="place_spot", value="12", source=EpisodicCueSource.RUNTIME_CONTEXT),
    )
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=player_id,
        occurred_at=ts,
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-a",)),
        location=EpisodeLocation(),
        action=EpisodeAction(tool_name="t"),
        who=("p",),
        what="w",
        why=None,
        observed="o",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=cue_list,
        recall_text=recall_text,
    )


class TestSqliteSubjectiveEpisodeStoreBasics:
    """Phase 3 Step 3e-3: being_id keyed only。"""

    def test_put_get_roundtrip(self) -> None:
        from ai_rpg_world.domain.being.value_object.being_id import BeingId

        being_id = BeingId("being_w1_p7")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "episodes.db")
            store = SqliteSubjectiveEpisodeStore.connect(path)
            ep = _episode()
            store.put_by_being(being_id, ep)
            got = store.get_by_being(being_id, "ep-1")
            assert got is not None
            assert got.episode_id == ep.episode_id
            assert got.player_id == ep.player_id
            assert got.cues == ep.cues
            assert got.recall_text == ep.recall_text

    def test_list_by_cue_after_reopen(self) -> None:
        from ai_rpg_world.domain.being.value_object.being_id import BeingId

        being_id = BeingId("being_w1_p7")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "episodes.db")
            cue = EpisodicCue(
                axis="place_spot", value="12", source=EpisodicCueSource.RUNTIME_CONTEXT
            )
            store = SqliteSubjectiveEpisodeStore.connect(path)
            store.put_by_being(being_id, _episode(episode_id="a"))
            del store
            store2 = SqliteSubjectiveEpisodeStore.connect(path)
            found = store2.list_by_cue_by_being(being_id, cue, limit=5)
            assert len(found) == 1
            assert found[0].episode_id == "a"
