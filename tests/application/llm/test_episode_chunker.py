"""RuleBasedEpisodeChunker のテスト。"""

from datetime import datetime, timedelta

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionExperienceTrace,
    EpisodeCandidate,
    ObservationExperienceTrace,
)
from ai_rpg_world.application.llm.services.episode_chunker import (
    RuleBasedEpisodeChunker,
)
from ai_rpg_world.application.llm.services.in_memory_action_experience_trace_store import (
    InMemoryActionExperienceTraceStore,
)
from ai_rpg_world.application.llm.services.in_memory_episode_candidate_store import (
    InMemoryEpisodeCandidateStore,
)
from ai_rpg_world.application.llm.services.in_memory_observation_experience_trace_store import (
    InMemoryObservationExperienceTraceStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _action_trace(
    trace_id: str,
    at: datetime,
    *,
    success: bool = True,
    emotion_hint: str = "curiosity",
    current_state_snapshot: str = "",
) -> ActionExperienceTrace:
    return ActionExperienceTrace(
        trace_id=trace_id,
        agent_id=1,
        occurred_at=at,
        tool_name="move_to_destination",
        tool_args={"destination_label": "S1"},
        inner_thought="進んでみよう。",
        intention="移動する。",
        expected_result="隣の場所が分かる。",
        attention="通路",
        emotion_hint=emotion_hint,  # type: ignore[arg-type]
        tool_result="移動しました。",
        result_success=success,
        error_code=None if success else "FAILED",
        current_state_snapshot=current_state_snapshot,
    )


def _observation_trace(
    trace_id: str,
    at: datetime,
    *,
    kind: str = "world_event",
    salience: str = "normal",
    location_snapshot: str = "",
) -> ObservationExperienceTrace:
    return ObservationExperienceTrace(
        trace_id=trace_id,
        agent_id=1,
        occurred_at=at,
        observation_summary="何かが起きた。",
        observation_kind=kind,  # type: ignore[arg-type]
        structured={"type": kind},
        perceived_salience=salience,
        location_snapshot=location_snapshot,
    )


def _chunker():
    action_store = InMemoryActionExperienceTraceStore()
    observation_store = InMemoryObservationExperienceTraceStore()
    candidate_store = InMemoryEpisodeCandidateStore()
    chunker = RuleBasedEpisodeChunker(
        action_trace_store=action_store,
        observation_trace_store=observation_store,
        candidate_store=candidate_store,
        max_traces_per_episode=5,
    )
    return chunker, action_store, observation_store, candidate_store


def test_candidate_store_add_get_recent_and_contains_source_trace() -> None:
    store = InMemoryEpisodeCandidateStore()
    player_id = PlayerId(1)
    now = datetime.now()
    candidate = EpisodeCandidate(
        candidate_id="c1",
        agent_id=1,
        created_at=now,
        source_trace_ids=("action:a1",),
        started_at=now,
        ended_at=now,
        trace_count=1,
        boundary_score=100,
        boundary_reasons=("hard_limit",),
    )

    store.add(player_id, candidate)

    assert store.get_recent(player_id, 10) == [candidate]
    assert store.contains_source_trace(player_id, "action:a1") is True
    assert store.contains_source_trace(player_id, "action:missing") is False


def test_evaluate_returns_false_without_unprocessed_traces() -> None:
    chunker, _, _, _ = _chunker()

    decision = chunker.evaluate(PlayerId(1))

    assert decision.should_create_candidate is False
    assert decision.source_trace_ids == ()


def test_hard_limit_creates_candidate_from_oldest_five_unprocessed_traces() -> None:
    chunker, action_store, _, candidate_store = _chunker()
    player_id = PlayerId(1)
    base = datetime.now()
    for i in range(6):
        action_store.append(
            player_id,
            _action_trace(f"a{i}", base + timedelta(seconds=i)),
        )

    decision = chunker.evaluate(player_id)
    candidate = chunker.create_candidate_if_ready(player_id)

    assert decision.should_create_candidate is True
    assert "hard_limit" in decision.boundary_reasons
    assert candidate is not None
    assert candidate.source_trace_ids == (
        "action:a0",
        "action:a1",
        "action:a2",
        "action:a3",
        "action:a4",
    )
    assert candidate.trace_count == 5
    assert candidate_store.contains_source_trace(player_id, "action:a0") is True


def test_create_candidate_if_ready_does_not_duplicate_processed_traces() -> None:
    chunker, action_store, _, _ = _chunker()
    player_id = PlayerId(1)
    base = datetime.now()
    for i in range(5):
        action_store.append(
            player_id,
            _action_trace(f"a{i}", base + timedelta(seconds=i)),
        )

    first = chunker.create_candidate_if_ready(player_id)
    second = chunker.create_candidate_if_ready(player_id)

    assert first is not None
    assert second is None


def test_high_salience_observation_can_cut_before_hard_limit() -> None:
    chunker, _, observation_store, _ = _chunker()
    player_id = PlayerId(1)
    observation_store.append(
        player_id,
        _observation_trace(
            "o1",
            datetime.now(),
            kind="environment_change",
            salience="high",
        ),
    )

    candidate = chunker.create_candidate_if_ready(player_id)

    assert candidate is not None
    assert candidate.source_trace_ids == ("observation:o1",)
    assert "high_salience_observation" in candidate.boundary_reasons


def test_failed_action_can_cut_before_hard_limit() -> None:
    chunker, action_store, _, _ = _chunker()
    player_id = PlayerId(1)
    action_store.append(
        player_id,
        _action_trace("a1", datetime.now(), success=False),
    )

    candidate = chunker.create_candidate_if_ready(player_id)

    assert candidate is not None
    assert "action_failure" in candidate.boundary_reasons


def test_low_salience_short_trace_sequence_is_not_ready() -> None:
    chunker, action_store, observation_store, _ = _chunker()
    player_id = PlayerId(1)
    now = datetime.now()
    action_store.append(player_id, _action_trace("a1", now))
    observation_store.append(
        player_id,
        _observation_trace("o1", now + timedelta(seconds=1), kind="world_event"),
    )

    decision = chunker.evaluate(player_id)
    candidate = chunker.create_candidate_if_ready(player_id)

    assert decision.should_create_candidate is False
    assert candidate is None
