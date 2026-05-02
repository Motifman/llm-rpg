"""v2 SubjectiveEpisode SQLite 永続化（episode_cues / memory_links）のテスト。"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    EpisodicCue,
    MemoryReflectionEpisodePatchDto,
    MemoryReflectionJournalEntry,
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
    memory_reflection_journal: tuple[MemoryReflectionJournalEntry, ...] = (),
    observed: str = "obs",
) -> SubjectiveEpisode:
    t0 = created_at or datetime.now()
    return SubjectiveEpisode(
        episode_id=episode_id,
        agent_id=agent_id,
        created_at=t0,
        started_at_tick=None,
        ended_at_tick=None,
        source_trace_ids=("action:a1",),
        observed=observed,
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
        memory_reflection_journal=memory_reflection_journal,
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
    assert "spatial" in types
    target_ids = {row["target_id"] for row in links}
    assert "e-a" in target_ids


def test_memory_link_temporal_without_shared_cue(db_path: str) -> None:
    store = SqliteSubjectiveEpisodeStore(db_path, max_links_per_episode=5)
    pid = PlayerId(1)
    t0 = datetime(2026, 5, 10, 10, 0, 0)
    store.put(
        pid,
        _episode(episode_id="e-first", cue_keys=("only:a",), created_at=t0),
    )
    store.put(
        pid,
        _episode(
            episode_id="e-second",
            cue_keys=("other:b",),
            created_at=t0 + timedelta(hours=2),
        ),
    )
    links = store.list_memory_links_from(pid, "e-second")
    assert any(r["link_type"] == "temporal" and r["target_id"] == "e-first" for r in links)


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


def test_count_reflection_journal_entries_uses_json_not_full_decode(db_path: str) -> None:
    store = SqliteSubjectiveEpisodeStore(db_path)
    pid = PlayerId(1)
    entry = MemoryReflectionJournalEntry(
        entry_id="j1",
        created_at=datetime.now(timezone.utc),
        correlation_id="c",
        trigger="t",
        recall_trigger="r",
        current_interpretation="i",
        effect_on_decision="d",
        episode_patch=MemoryReflectionEpisodePatchDto(),
    )
    store.put(
        pid,
        _episode(
            episode_id="e-j",
            cue_keys=("k:1",),
            memory_reflection_journal=(entry,),
        ),
    )
    assert store.count_reflection_journal_entries(pid) == 1
    store.put(
        pid,
        _episode(
            episode_id="e-j2",
            cue_keys=("k:2",),
            memory_reflection_journal=(),
        ),
    )
    assert store.count_reflection_journal_entries(pid) == 1


def test_list_recent_order(db_path: str) -> None:
    store = SqliteSubjectiveEpisodeStore(db_path)
    pid = PlayerId(1)
    t0 = datetime(2026, 3, 1, 0, 0, 0)
    store.put(pid, _episode(episode_id="older", created_at=t0))
    store.put(pid, _episode(episode_id="newer", created_at=t0 + timedelta(days=1)))
    recent = store.list_recent(pid, 1)
    assert len(recent) == 1
    assert recent[0].episode_id == "newer"


def test_agent_id_isolation_same_episode_id_different_players(db_path: str) -> None:
    """同一 episode_id 文字列でも agent_id が違えば別行として保存され、取得が混ざらない。"""
    store = SqliteSubjectiveEpisodeStore(db_path)
    p1 = PlayerId(1)
    p2 = PlayerId(2)
    t0 = datetime(2026, 7, 1, 0, 0, 0)
    store.put(
        p1,
        _episode(
            episode_id="dup-id",
            agent_id=1,
            cue_keys=("spot:1",),
            observed="player1",
            created_at=t0,
        ),
    )
    store.put(
        p2,
        _episode(
            episode_id="dup-id",
            agent_id=2,
            cue_keys=("spot:1",),
            observed="player2",
            created_at=t0 + timedelta(minutes=1),
        ),
    )
    g1 = store.get_by_episode_id(p1, "dup-id")
    g2 = store.get_by_episode_id(p2, "dup-id")
    assert g1 is not None and g1.observed == "player1" and g1.agent_id == 1
    assert g2 is not None and g2.observed == "player2" and g2.agent_id == 2
    assert {e.agent_id for e in store.list_all_episodes(p1)} == {1}
    assert {e.agent_id for e in store.list_all_episodes(p2)} == {2}


def test_agent_id_isolation_cue_reverse_lookup(db_path: str) -> None:
    """episode_cues の逆引きは agent_id でスコープされ、他プレイヤーの id が返らない。"""
    store = SqliteSubjectiveEpisodeStore(db_path)
    p1 = PlayerId(1)
    p2 = PlayerId(2)
    t0 = datetime(2026, 7, 2, 0, 0, 0)
    store.put(
        p1,
        _episode(episode_id="e-p1", agent_id=1, cue_keys=("shared_cue:x",), created_at=t0),
    )
    store.put(
        p2,
        _episode(episode_id="e-p2", agent_id=2, cue_keys=("shared_cue:x",), created_at=t0),
    )
    ids1 = store.list_episode_ids_by_cue_keys(p1, ("shared_cue:x",))
    ids2 = store.list_episode_ids_by_cue_keys(p2, ("shared_cue:x",))
    assert ids1 == ["e-p1"]
    assert ids2 == ["e-p2"]
    assert "e-p2" not in ids1
    assert "e-p1" not in ids2


def test_agent_id_isolation_memory_links(db_path: str) -> None:
    """memory_links は同一 agent 内の episode_id のみを指す。"""
    store = SqliteSubjectiveEpisodeStore(db_path, max_links_per_episode=5)
    p1 = PlayerId(1)
    p2 = PlayerId(2)
    t0 = datetime(2026, 7, 3, 0, 0, 0)
    store.put(
        p1,
        _episode(episode_id="alpha-1", agent_id=1, cue_keys=("tile:99",), created_at=t0),
    )
    store.put(
        p1,
        _episode(
            episode_id="beta-1",
            agent_id=1,
            cue_keys=("tile:99",),
            created_at=t0 + timedelta(hours=1),
        ),
    )
    store.put(
        p2,
        _episode(episode_id="alpha-2", agent_id=2, cue_keys=("tile:99",), created_at=t0),
    )
    store.put(
        p2,
        _episode(
            episode_id="beta-2",
            agent_id=2,
            cue_keys=("tile:99",),
            created_at=t0 + timedelta(hours=1),
        ),
    )
    targets_p1 = {r["target_id"] for r in store.list_memory_links_from(p1, "beta-1")}
    targets_p2 = {r["target_id"] for r in store.list_memory_links_from(p2, "beta-2")}
    assert "alpha-1" in targets_p1
    assert "alpha-2" not in targets_p1
    assert "alpha-2" in targets_p2
    assert "alpha-1" not in targets_p2
    assert "beta-2" not in targets_p1


def test_agent_id_isolation_eviction_does_not_touch_other_player(db_path: str) -> None:
    """max_entries の掃除は当該 agent の行だけ。他プレイヤーのエピソードは残る。"""
    store = SqliteSubjectiveEpisodeStore(db_path, max_entries_per_player=2)
    p1 = PlayerId(1)
    p2 = PlayerId(2)
    t0 = datetime(2026, 7, 4, 0, 0, 0)
    store.put(
        p1,
        _episode(episode_id="p1-old", agent_id=1, cue_keys=("a:1",), created_at=t0),
    )
    store.put(
        p1,
        _episode(episode_id="p1-mid", agent_id=1, cue_keys=("a:2",), created_at=t0 + timedelta(days=1)),
    )
    store.put(
        p1,
        _episode(episode_id="p1-new", agent_id=1, cue_keys=("a:3",), created_at=t0 + timedelta(days=2)),
    )
    store.put(
        p2,
        _episode(episode_id="p2-only", agent_id=2, cue_keys=("b:1",), created_at=t0),
    )
    assert store.get_by_episode_id(p1, "p1-old") is None
    assert {e.episode_id for e in store.list_all_episodes(p1)} == {"p1-mid", "p1-new"}
    assert store.get_by_episode_id(p2, "p2-only") is not None


def test_agent_id_isolation_recall_and_journal_count(db_path: str) -> None:
    """Passive recall 加算とジャーナル件数集計が agent_id 境界を越えない。"""
    store = SqliteSubjectiveEpisodeStore(db_path)
    p1 = PlayerId(1)
    p2 = PlayerId(2)
    entry = MemoryReflectionJournalEntry(
        entry_id="jx",
        created_at=datetime.now(timezone.utc),
        correlation_id="c",
        trigger="t",
        recall_trigger="r",
        current_interpretation="i",
        effect_on_decision="d",
        episode_patch=MemoryReflectionEpisodePatchDto(),
    )
    store.put(
        p1,
        _episode(
            episode_id="ep1",
            agent_id=1,
            cue_keys=("z:1",),
            memory_reflection_journal=(entry,),
        ),
    )
    store.put(
        p2,
        _episode(episode_id="ep2", agent_id=2, cue_keys=("z:2",)),
    )
    store.record_passive_recall(p1, "ep1")
    g1_after = store.get_by_episode_id(p1, "ep1")
    assert g1_after is not None and g1_after.recall_count == 1
    store.record_passive_recall(p2, "nonexistent-should-noop")
    g2 = store.get_by_episode_id(p2, "ep2")
    assert g2 is not None and g2.recall_count == 0
    assert store.count_reflection_journal_entries(p1) == 1
    assert store.count_reflection_journal_entries(p2) == 0
