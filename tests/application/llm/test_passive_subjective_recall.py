"""Phase 4: Passive Subjective Recall（ルールベース想起）のテスト。"""

from dataclasses import replace
from datetime import datetime, timedelta

from ai_rpg_world.application.llm.contracts.dtos import (
    SubjectiveEpisode,
    SubjectiveFelt,
    SubjectivePredictionError,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.passive_subjective_recall_composer import (
    PassiveSubjectiveRecallComposer,
    score_episode_for_recall,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _episode(
    *,
    episode_id: str,
    cue_keys: tuple[str, ...] = (),
    observed: str = "扉を調べた。",
    importance: str = "medium",
    created_at: datetime | None = None,
) -> SubjectiveEpisode:
    t0 = created_at or datetime.now()
    return SubjectiveEpisode(
        episode_id=episode_id,
        agent_id=1,
        created_at=t0,
        started_at_tick=None,
        ended_at_tick=None,
        source_trace_ids=("action:a1",),
        observed=observed,
        interpreted="緊張していた。",
        felt=SubjectiveFelt(primary_emotion="curiosity", secondary_emotions=(), emotion_note=""),
        intended="確認する",
        expected="手がかり",
        prediction_error=SubjectivePredictionError(level="none", reason="x"),
        cue_keys=cue_keys,
        cues=(),
        importance=importance,  # type: ignore[arg-type]
        salience_reasons=(),
        candidate_id="cand-1",
    )


def test_score_episode_prefers_cue_overlap() -> None:
    now = datetime(2026, 4, 29, 15, 0, 0)
    ep = _episode(
        episode_id="e1",
        cue_keys=("鐘", "霧"),
        created_at=now - timedelta(days=10),
    )
    s = score_episode_for_recall(
        ep,
        situation_text="広場で鐘の音がした。霧が薄い。",
        goal_tokens=set(),
        now=now,
    )
    assert s >= 26.0


def test_compose_user_block_includes_header_and_bumps_recall() -> None:
    store = InMemorySubjectiveEpisodeStore()
    pid = PlayerId(1)
    ep = _episode(
        episode_id="subjective-episode-fixture",
        cue_keys=("鐘",),
        observed="鐘が鳴った記憶がある。",
    )
    store.put(pid, ep)
    composer = PassiveSubjectiveRecallComposer(
        subjective_episode_store=store,
        min_score=0.0,
        max_hits=2,
    )
    block = composer.compose_user_block(
        pid,
        situation_text="広場の鐘が聞こえる。",
        current_goals_hint="",
    )
    assert "【ふと思い出したこと】" in block.user_block
    assert "鐘が鳴った記憶" in block.user_block
    assert "[medium]" in block.user_block
    assert block.episode_ids_for_reflection == ("subjective-episode-fixture",)
    updated = store.get_by_episode_id(pid, "subjective-episode-fixture")
    assert updated is not None
    assert updated.recall_count == 1
    assert updated.last_recalled_at is not None


def test_compose_returns_empty_when_no_match() -> None:
    store = InMemorySubjectiveEpisodeStore()
    pid = PlayerId(1)
    ep = _episode(episode_id="e2", cue_keys=("unused_tag",), importance="low")
    old_time = datetime(2020, 1, 1, 0, 0, 0)
    store.put(pid, replace(ep, created_at=old_time))
    composer = PassiveSubjectiveRecallComposer(
        subjective_episode_store=store,
        max_hits=1,
    )
    block = composer.compose_user_block(
        pid,
        situation_text="まったく無関係な状況だけが続く。",
        current_goals_hint="",
    )
    assert block.user_block == ""


def test_record_passive_recall_noop_when_missing() -> None:
    store = InMemorySubjectiveEpisodeStore()
    store.record_passive_recall(PlayerId(1), "nope")
