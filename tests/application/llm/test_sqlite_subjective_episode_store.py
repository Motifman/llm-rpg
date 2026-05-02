"""v2 SubjectiveEpisode SQLite 永続化（episode_cues / memory_links）のテスト。"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    EpisodicCue,
    SubjectiveEpisode,
    SubjectiveFelt,
    SubjectivePredictionError,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.llm.sqlite_subjective_episode_store import (
    SqliteSubjectiveEpisodeStore,
)


def _episode(
    *,
    episode_id: str,
    agent_id: int = 1,
    cue_keys: tuple[str, ...] = (),
    cues: tuple[EpisodicCue, ...] = (),
    created_at: datetime | None = None,
) -> SubjectiveEpisode:
    t0 = created_at or datetime.now()
    return SubjectiveEpisode(
        episode_id=episode_id,
        agent_id=agent_id,
        created_at=t0,
        started_at_tick=None,
        ended_at_tick=None,
        source_trace_ids=("action:a1",),
        observed="obs",
        interpreted="interp",
        felt=SubjectiveFelt(primary_emotion="neutral", secondary_emotions=(), emotion_note=""),
        intended="i",
        expected="e",
        prediction_error=SubjectivePredictionError(level="none", reason="x"),
        cue_keys=cue_keys,
        cues=cues,
        importance="medium",
        salience_reasons=(),
        candidate_id="cand-1",
    )


@pytest.fixture
def db_path() -> str:
    with tempfile.NamedTemporaryFile(suffix=".sqlite") as f:
        yield f.name


def test_put_get_roundtrip(db_path: str) -> None:
    store = SqliteSubjectiveEpisodeStore(db_path)
    pid = PlayerId(1)
    ep = _episode(episode_id="e1", cue_keys=("tool:open",))
    store.put(pid, ep)
    got = store.get_by_episode_id(pid, "e1")
    assert got is not None
    assert got.episode_id == "e1"
    assert got.cue_keys == ("tool:open",)
    assert got.observed == "obs"


def test_episode_cues_merge_cue_keys_and_typed_cues(db_path: str) -> None:
    store = SqliteSubjectiveEpisodeStore(db_path)
    pid = PlayerId(1)
    ep = _episode(
        episode_id="e-merge",
        cue_keys=("legacy:extra",),
        cues=(
            EpisodicCue(axis="place_spot", value="99"),
        ),
    )
    store.put(pid, ep)
    ids_place = store.list_episode_ids_by_cue_keys(pid, ("place_spot:99",))
    ids_legacy = store.list_episode_ids_by_cue_keys(pid, ("legacy:extra",))
    assert "e-merge" in ids_place
    assert "e-merge" in ids_legacy


def test_cue_index_updates_on_overwrite(db_path: str) -> None:
    store = SqliteSubjectiveEpisodeStore(db_path)
    pid = PlayerId(1)
    store.put(pid, _episode(episode_id="same", cue_keys=("oldkey",)))
    assert store.list_episode_ids_by_cue_keys(pid, ("oldkey",)) == ["same"]
    assert store.list_episode_ids_by_cue_keys(pid, ("newkey",)) == []
    store.put(pid, _episode(episode_id="same", cue_keys=("newkey",)))
    assert store.list_episode_ids_by_cue_keys(pid, ("oldkey",)) == []
    assert store.list_episode_ids_by_cue_keys(pid, ("newkey",)) == ["same"]


def test_memory_link_spatial_on_cue_overlap(db_path: str) -> None:
    store = SqliteSubjectiveEpisodeStore(db_path, max_links_per_episode=5)
    pid = PlayerId(1)
    t0 = datetime(2026, 5, 1, 12, 0, 0)
    store.put(
        pid,
        _episode(episode_id="e-a", cue_keys=("tile_area:7",), created_at=t0),
    )
    store.put(
        pid,
        _episode(
            episode_id="e-b",
            cue_keys=("tile_area:7",),
            created_at=t0 + timedelta(hours=1),
        ),
    )
    links = store.list_memory_links_from(pid, "e-b")
    types = {row["link_type"] for row in links}
    assert "spatial" in types or "co_recalled" in types
    target_ids = {row["target_id"] for row in links}
    assert "e-a" in target_ids


def test_memory_link_co_recalled_when_target_recalled_before(db_path: str) -> None:
    store = SqliteSubjectiveEpisodeStore(db_path, max_links_per_episode=5)
    pid = PlayerId(1)
    t0 = datetime(2026, 5, 2, 8, 0, 0)
    store.put(
        pid,
        _episode(episode_id="e-old", cue_keys=("sub_loc:3",), created_at=t0),
    )
    store.record_passive_recall(pid, "e-old")
    store.put(
        pid,
        _episode(
            episode_id="e-new",
            cue_keys=("sub_loc:3",),
            created_at=t0 + timedelta(minutes=30),
        ),
    )
    links = store.list_memory_links_from(pid, "e-new")
    assert any(r["link_type"] == "co_recalled" and r["target_id"] == "e-old" for r in links)


def test_max_entries_eviction(db_path: str) -> None:
    store = SqliteSubjectiveEpisodeStore(db_path, max_entries_per_player=2)
    pid = PlayerId(1)
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    store.put(
        pid,
        _episode(episode_id="first", cue_keys=("k:1",), created_at=t0),
    )
    store.put(
        pid,
        _episode(episode_id="second", cue_keys=("k:2",), created_at=t0 + timedelta(days=1)),
    )
    store.put(
        pid,
        _episode(episode_id="third", cue_keys=("k:3",), created_at=t0 + timedelta(days=2)),
    )
    all_ids = {ep.episode_id for ep in store.list_all_episodes(pid)}
    assert all_ids == {"second", "third"}
    assert store.get_by_episode_id(pid, "first") is None


def test_list_recent_order(db_path: str) -> None:
    store = SqliteSubjectiveEpisodeStore(db_path)
    pid = PlayerId(1)
    t0 = datetime(2026, 3, 1, 0, 0, 0)
    store.put(pid, _episode(episode_id="older", created_at=t0))
    store.put(pid, _episode(episode_id="newer", created_at=t0 + timedelta(days=1)))
    recent = store.list_recent(pid, 1)
    assert len(recent) == 1
    assert recent[0].episode_id == "newer"
