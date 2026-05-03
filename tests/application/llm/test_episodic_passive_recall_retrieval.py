"""EpisodicPassiveRecallRetrievalService の和集合・round-robin・軸デバッグの検証。"""

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
    PASSIVE_RECALL_AXIS_TEMPORAL,
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


class TestEpisodicPassiveRecallRetrievalTemporalOnly:
    """時間軸だけで候補が取れること"""

    def test_temporal_axis_only_when_no_situation_cues(self) -> None:
        """situation_cues が空なら temporal のみがソースとなり、debug に temporal が載る。"""
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
        assert all(PASSIVE_RECALL_AXIS_TEMPORAL in c.source_axes for c in result.candidates)
        assert result.debug.raw_row_count_by_axis == ((PASSIVE_RECALL_AXIS_TEMPORAL, 2),)
        assert result.debug.final_episode_count_by_source_axis == ((PASSIVE_RECALL_AXIS_TEMPORAL, 2),)


class TestEpisodicPassiveRecallRetrievalCueOnly:
    """cue 軸だけで temporal に入らない古い episode を拾えること"""

    def test_cue_axis_retrieves_old_episode_not_in_temporal_window(self) -> None:
        """temporal の limit で切り落とされる古い件が、cue 照合で和集合に入る。"""
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
        assert passive_recall_cue_axis_label(trap) == "cue:schema_hint"
        assert passive_recall_cue_axis_label(trap) in by_id["trap-old"].source_axes
        assert (passive_recall_cue_axis_label(trap), 1) in result.debug.final_episode_count_by_source_axis


class TestEpisodicPassiveRecallRetrievalUnionDedupe:
    """temporal と cue の重複が和集合で 1 件になること"""

    def test_same_episode_from_temporal_and_cue_has_single_row_and_merged_axes(self) -> None:
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
        assert PASSIVE_RECALL_AXIS_TEMPORAL in axes
        assert passive_recall_cue_axis_label(shared) == "cue:object"
        assert passive_recall_cue_axis_label(shared) in axes
        assert result.debug.union_episode_count_before_max_cap == 1
        assert result.debug.candidate_episode_sources == (
            ("both", ("cue:object", PASSIVE_RECALL_AXIS_TEMPORAL)),
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
        temporal_count = dict(result.debug.raw_row_count_by_axis)[PASSIVE_RECALL_AXIS_TEMPORAL]
        cue_count = dict(result.debug.raw_row_count_by_axis)["cue:action"]
        assert temporal_count == 2
        assert cue_count == 2

    def test_max_candidates_uses_round_robin_not_global_recency(self) -> None:
        """max_candidates 件は全体時刻順の先頭ではなく、軸巡回で選ばれる。"""
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
        assert [c.episode.episode_id for c in result.candidates] == ["p1", "p3"]
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
        assert counts[PASSIVE_RECALL_AXIS_TEMPORAL] == 2
        assert counts["cue:outcome"] == 1


class TestEpisodicPassiveRecallRetrievalRoundRobinFairness:
    """round-robin で cue 軸が時間に押し流されないこと"""

    def test_old_cue_match_surfaces_despite_many_recent_in_temporal(self) -> None:
        """古いが cue に一致する episode が、直近だけの temporal 先頭に独占されず採用される。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 5, 1, tzinfo=timezone.utc)
        filler = EpisodicCue(axis="place", value="99", source=EpisodicCueSource.RUNTIME_CONTEXT)
        trap = EpisodicCue(axis="schema_hint", value="trap", source=EpisodicCueSource.TOOL)
        for i in range(4):
            store.put(
                _episode(
                    episode_id=f"f{i}",
                    occurred_at=base + timedelta(days=i + 1),
                    cues=(filler,),
                )
            )
        store.put(_episode(episode_id="trap-old", occurred_at=base, cues=(trap,)))
        svc = EpisodicPassiveRecallRetrievalService(store)
        result = svc.retrieve(
            player_id=7,
            situation_cues=(trap,),
            limit_per_axis=3,
            max_candidates=2,
        )
        assert [c.episode.episode_id for c in result.candidates] == ["f3", "trap-old"]

    def test_round_robin_interleaves_temporal_and_distinct_cue_axes(self) -> None:
        """temporal, cue:place_spot, cue:entity, cue:object を巡回して採用する。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
        c_place = EpisodicCue(axis="place_spot", value="12", source=EpisodicCueSource.RUNTIME_CONTEXT)
        c_entity = EpisodicCue(axis="entity", value="alice", source=EpisodicCueSource.TOOL)
        c_object = EpisodicCue(axis="object", value="box", source=EpisodicCueSource.TOOL)
        store.put(_episode(episode_id="T", occurred_at=base + timedelta(days=10), cues=()))
        store.put(_episode(episode_id="P", occurred_at=base + timedelta(days=5), cues=(c_place,)))
        store.put(_episode(episode_id="E", occurred_at=base + timedelta(days=4), cues=(c_entity,)))
        store.put(_episode(episode_id="O", occurred_at=base + timedelta(days=3), cues=(c_object,)))
        svc = EpisodicPassiveRecallRetrievalService(store)
        result = svc.retrieve(
            player_id=7,
            situation_cues=(c_place, c_entity, c_object),
            limit_per_axis=1,
            max_candidates=4,
        )
        assert [c.episode.episode_id for c in result.candidates] == ["T", "P", "E", "O"]
        axes_by_id = {c.episode.episode_id: set(c.source_axes) for c in result.candidates}
        assert axes_by_id["T"] == {PASSIVE_RECALL_AXIS_TEMPORAL}
        assert axes_by_id["P"] == {"cue:place_spot"}
        assert axes_by_id["E"] == {"cue:entity"}
        assert axes_by_id["O"] == {"cue:object"}

    def test_small_max_candidates_does_not_fill_only_from_temporal(self) -> None:
        """max_candidates が小さくても temporal だけで枠を埋めない。"""
        store = InMemorySubjectiveEpisodeStore()
        base = datetime(2026, 7, 1, tzinfo=timezone.utc)
        c_place = EpisodicCue(axis="place_spot", value="1", source=EpisodicCueSource.RUNTIME_CONTEXT)
        c_entity = EpisodicCue(axis="entity", value="z", source=EpisodicCueSource.TOOL)
        for i in range(3):
            store.put(
                _episode(
                    episode_id=f"t{i}",
                    occurred_at=base + timedelta(hours=i),
                    cues=(),
                )
            )
        store.put(_episode(episode_id="place-only", occurred_at=base - timedelta(days=1), cues=(c_place,)))
        store.put(_episode(episode_id="entity-only", occurred_at=base - timedelta(days=2), cues=(c_entity,)))
        svc = EpisodicPassiveRecallRetrievalService(store)
        result = svc.retrieve(
            player_id=7,
            situation_cues=(c_place, c_entity),
            limit_per_axis=5,
            max_candidates=3,
        )
        ids = [c.episode.episode_id for c in result.candidates]
        assert ids == ["t2", "place-only", "entity-only"]
        assert "entity-only" in ids
        assert ids.count("t2") == 1
