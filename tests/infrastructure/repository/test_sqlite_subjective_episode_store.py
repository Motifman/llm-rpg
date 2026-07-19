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
    co_present: tuple[str, ...] = (),
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
        co_present=co_present,
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

    def test_co_present_round_trips_through_sqlite(self) -> None:
        """PR-M: co_present (= chunk 時点の同席プレイヤー名) が sqlite の
        payload_json を経由して保存・復元される (再開で共在情報を失わない)。"""
        from ai_rpg_world.domain.being.value_object.being_id import BeingId

        being_id = BeingId("being_w1_p7")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "episodes.db")
            store = SqliteSubjectiveEpisodeStore.connect(path)
            ep = _episode(co_present=("ノア", "カイ"))
            store.put_by_being(being_id, ep)
            del store
            store2 = SqliteSubjectiveEpisodeStore.connect(path)
            got = store2.get_by_being(being_id, "ep-1")
            assert got is not None
            assert got.co_present == ("ノア", "カイ")

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


class TestSqliteSubjectiveEpisodeReplaceAll:
    """Phase 4 Step 4-2a: list_all_by_being / replace_all_by_being。"""

    def test_replace_all_cue_index(self) -> None:
        """replace all で全置換と cue index 再構築。"""
        from ai_rpg_world.domain.being.value_object.being_id import BeingId

        being_id = BeingId("being_w1_p7")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "episodes.db")
            store = SqliteSubjectiveEpisodeStore.connect(path)
            store.put_by_being(being_id, _episode(episode_id="old"))
            new_cue = EpisodicCue(
                axis="place_spot", value="999", source=EpisodicCueSource.RUNTIME_CONTEXT
            )
            new = _episode(episode_id="new", cues=(new_cue,))
            store.replace_all_by_being(being_id, [new])
            ids = [e.episode_id for e in store.list_all_by_being(being_id)]
            assert ids == ["new"]
            hits = store.list_by_cue_by_being(being_id, new_cue, limit=5)
            assert [e.episode_id for e in hits] == ["new"]

    def test_other_being_does_not_affect(self) -> None:
        """他 being は影響しない。"""
        from ai_rpg_world.domain.being.value_object.being_id import BeingId

        a = BeingId("being_w1_p1")
        b = BeingId("being_w1_p2")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "episodes.db")
            store = SqliteSubjectiveEpisodeStore.connect(path)
            store.put_by_being(a, _episode(episode_id="a"))
            store.put_by_being(b, _episode(episode_id="b"))
            store.replace_all_by_being(a, [])
            assert [e.episode_id for e in store.list_all_by_being(b)] == ["b"]
