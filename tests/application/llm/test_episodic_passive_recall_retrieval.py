"""EpisodicPassiveRecallRetrievalService の和集合・上限・軸デバッグの検証。"""

from datetime import datetime, timedelta, timezone

from ai_rpg_world.application.llm.contracts.episodic_memory import (
    EpisodicCue,
    EpisodicCueSource,
    EpisodeAction,
    EpisodeLocation,
    EpisodeSource,
    SubjectiveEpisode,
)
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    PASSIVE_RECALL_AXIS_RECENT,
    EpisodicPassiveRecallRetrievalService,
    passive_recall_cue_axis_label,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)


def _episode(
    *,
    episode_id: str,
    player_id: int = 7,
    occurred_at: datetime,
    cues: tuple[EpisodicCue, ...],
) -> SubjectiveEpisode:
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=player_id,
        occurred_at=occurred_at,
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
        cues=cues,
        recall_text="r",
    )


class TestEpisodicPassiveRecallRetrievalRecentOnly:
    """時間軸だけで候補が取れること"""

    def test_recent_axis_only_when_no_situation_cues(self) -> None:
        """situation_cues が空なら list_recent のみがソースとなり、debug に recent が載る。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
        cue = EpisodicCue(axis="place", value="x", source=EpisodicCueSource.RUNTIME_CONTEXT)
        store.put(_episode(episode_id="old", occurred_at=base, cues=(cue,)))
        store.put(_episode(episode_id="new", occurred_at=base + timedelta(days=1), cues=(cue,)))
        svc = EpisodicPassiveRecallRetrievalService(store)
        result = svc.retrieve(
            player_id=7,
            situation_cues=(),
            limit_per_axis=10,
            max_candidates=10,
        )
        ids = [c.episode.episode_id for c in result.candidates]
        assert ids == ["new", "old"]
        assert all(PASSIVE_RECALL_AXIS_RECENT in c.source_axes for c in result.candidates)
        assert result.debug.raw_row_count_by_axis == ((PASSIVE_RECALL_AXIS_RECENT, 2),)
        assert result.debug.final_episode_count_by_source_axis == ((PASSIVE_RECALL_AXIS_RECENT, 2),)


class TestEpisodicPassiveRecallRetrievalCueOnly:
    """cue 軸だけで recent に入らない古い episode を拾えること"""

    def test_cue_axis_retrieves_old_episode_not_in_recent_window(self) -> None:
        """recent の limit で切り落とされる古い件が、cue 照合で和集合に入る。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
        trap = EpisodicCue(axis="schema_hint", value="trap", source=EpisodicCueSource.TOOL)
        other = EpisodicCue(axis="place", value="99", source=EpisodicCueSource.RUNTIME_CONTEXT)
        for i in range(3):
            store.put(
                _episode(
                    episode_id=f"recent-{i}",
                    occurred_at=base + timedelta(days=10 + i),
                    cues=(other,),
                )
            )
        old = _episode(episode_id="trap-old", occurred_at=base, cues=(trap,))
        store.put(old)
        svc = EpisodicPassiveRecallRetrievalService(store)
        result = svc.retrieve(
            player_id=7,
            situation_cues=(trap,),
            limit_per_axis=2,
            max_candidates=20,
        )
        by_id = {c.episode.episode_id: c for c in result.candidates}
        assert "trap-old" in by_id
        assert passive_recall_cue_axis_label(trap) in by_id["trap-old"].source_axes
        cue_label = passive_recall_cue_axis_label(trap)
        assert (cue_label, 1) in result.debug.final_episode_count_by_source_axis


class TestEpisodicPassiveRecallRetrievalUnionDedupe:
    """時間と cue の重複が和集合で 1 件になること"""

    def test_same_episode_from_recent_and_cue_has_single_row_and_merged_axes(self) -> None:
        """同一 episode_id が両軸から来たとき候補は 1 行、source_axes に両方が残る。"""
        store = InMemorySubjectiveEpisodeStore()
        ts = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)
        shared = EpisodicCue(axis="object", value="box", source=EpisodicCueSource.RUNTIME_CONTEXT)
        ep = _episode(episode_id="both", occurred_at=ts, cues=(shared,))
        store.put(ep)
        svc = EpisodicPassiveRecallRetrievalService(store)
        result = svc.retrieve(
            player_id=7,
            situation_cues=(shared,),
            limit_per_axis=5,
            max_candidates=10,
        )
        assert len(result.candidates) == 1
        axes = result.candidates[0].source_axes
        assert PASSIVE_RECALL_AXIS_RECENT in axes
        assert passive_recall_cue_axis_label(shared) in axes
        assert result.debug.union_episode_count_before_max_cap == 1
        assert result.debug.candidate_episode_sources == (
            ("both", (passive_recall_cue_axis_label(shared), PASSIVE_RECALL_AXIS_RECENT)),
        )


class TestEpisodicPassiveRecallRetrievalLimits:
    """limit_per_axis / max_candidates が効くこと"""

    def test_limit_per_axis_caps_each_axis_fetch(self) -> None:
        """list_recent / list_by_cue それぞれが limit_per_axis で打ち切られる。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 5, 1, tzinfo=timezone.utc)
        k = EpisodicCue(axis="action", value="open", source=EpisodicCueSource.TOOL)
        for i in range(5):
            store.put(
                _episode(
                    episode_id=f"e{i}",
                    occurred_at=base + timedelta(hours=i),
                    cues=(k,),
                )
            )
        svc = EpisodicPassiveRecallRetrievalService(store)
        result = svc.retrieve(
            player_id=7,
            situation_cues=(k,),
            limit_per_axis=2,
            max_candidates=20,
        )
        recent_count = dict(result.debug.raw_row_count_by_axis)[PASSIVE_RECALL_AXIS_RECENT]
        cue_count = dict(result.debug.raw_row_count_by_axis)[passive_recall_cue_axis_label(k)]
        assert recent_count == 2
        assert cue_count == 2

    def test_max_candidates_trims_after_union(self) -> None:
        """和集合後の全体を occurred_at 順に並べ、先頭 max_candidates 件だけ返す。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 5, 1, tzinfo=timezone.utc)
        a = EpisodicCue(axis="a", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT)
        b = EpisodicCue(axis="b", value="2", source=EpisodicCueSource.RUNTIME_CONTEXT)
        store.put(_episode(episode_id="p1", occurred_at=base + timedelta(days=3), cues=(a,)))
        store.put(_episode(episode_id="p2", occurred_at=base + timedelta(days=2), cues=(b,)))
        store.put(_episode(episode_id="p3", occurred_at=base + timedelta(days=1), cues=(a, b)))
        svc = EpisodicPassiveRecallRetrievalService(store)
        result = svc.retrieve(
            player_id=7,
            situation_cues=(a, b),
            limit_per_axis=10,
            max_candidates=2,
        )
        assert len(result.candidates) == 2
        assert [c.episode.episode_id for c in result.candidates] == ["p1", "p2"]
        assert result.debug.union_episode_count_before_max_cap == 3


class TestEpisodicPassiveRecallRetrievalDebugAxes:
    """debug に source axis の集計が残ること"""

    def test_final_episode_count_by_source_axis_reflects_overlap(self) -> None:
        """重複 episode は各軸のカウントに二重に効かない（episode あたり 1）。"""
        store = InMemorySubjectiveEpisodeStore()
        ts = datetime(2026, 5, 2, tzinfo=timezone.utc)
        c = EpisodicCue(axis="outcome", value="failure", source=EpisodicCueSource.TOOL)
        store.put(_episode(episode_id="solo-recent", occurred_at=ts + timedelta(days=1), cues=()))
        store.put(_episode(episode_id="overlap", occurred_at=ts, cues=(c,)))
        svc = EpisodicPassiveRecallRetrievalService(store)
        result = svc.retrieve(player_id=7, situation_cues=(c,), limit_per_axis=5, max_candidates=10)
        counts = dict(result.debug.final_episode_count_by_source_axis)
        assert counts[PASSIVE_RECALL_AXIS_RECENT] == 2
        assert counts[passive_recall_cue_axis_label(c)] == 1
