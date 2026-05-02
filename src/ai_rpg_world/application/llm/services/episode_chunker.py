"""ExperienceTrace 群から EpisodeCandidate を作るルールベース chunker。

現時点の Phase 2 実装では **LLM を使わない**（system prompt も JSON 生成もない）。
境界判定は件数・失敗・salience などの **決定的な score** のみ。
出力は常に `EpisodeCandidate` / `EpisodeChunkDecision` の dataclass（LLM の JSON ではない）。

将来 LLM chunker を足す場合も、本クラスはベースラインとして残す想定。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Tuple
from uuid import uuid4

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionExperienceTrace,
    EpisodeCandidate,
    EpisodeChunkDecision,
    ObservationExperienceTrace,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionExperienceTraceStore,
    IEpisodeCandidateStore,
    IEpisodeChunkCoordinator,
    IObservationExperienceTraceStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_DEFAULT_MAX_TRACES_PER_EPISODE = 5
_DEFAULT_LOOKBACK_LIMIT = 100
_DEFAULT_BOUNDARY_THRESHOLD = 70
_STRONG_EMOTIONS = frozenset({
    "fear",
    "urgency",
    "frustration",
    "regret",
    "surprise",
})


@dataclass(frozen=True)
class _TraceRef:
    source_id: str
    occurred_at: datetime
    trace: ActionExperienceTrace | ObservationExperienceTrace


class RuleBasedEpisodeChunker(IEpisodeChunkCoordinator):
    """未処理 trace 群を評価し、今が区切り時なら EpisodeCandidate を保存する。

    LLM 不使用。将来 LLM chunker を足す場合も、この class は deterministic な
    baseline として残す。
    """

    def __init__(
        self,
        *,
        action_trace_store: IActionExperienceTraceStore,
        observation_trace_store: IObservationExperienceTraceStore,
        candidate_store: IEpisodeCandidateStore,
        max_traces_per_episode: int = _DEFAULT_MAX_TRACES_PER_EPISODE,
        lookback_limit: int = _DEFAULT_LOOKBACK_LIMIT,
        boundary_threshold: int = _DEFAULT_BOUNDARY_THRESHOLD,
    ) -> None:
        if not isinstance(action_trace_store, IActionExperienceTraceStore):
            raise TypeError("action_trace_store must be IActionExperienceTraceStore")
        if not isinstance(observation_trace_store, IObservationExperienceTraceStore):
            raise TypeError(
                "observation_trace_store must be IObservationExperienceTraceStore"
            )
        if not isinstance(candidate_store, IEpisodeCandidateStore):
            raise TypeError("candidate_store must be IEpisodeCandidateStore")
        if max_traces_per_episode <= 0:
            raise ValueError("max_traces_per_episode must be greater than 0")
        if lookback_limit <= 0:
            raise ValueError("lookback_limit must be greater than 0")
        if boundary_threshold <= 0:
            raise ValueError("boundary_threshold must be greater than 0")
        self._action_trace_store = action_trace_store
        self._observation_trace_store = observation_trace_store
        self._candidate_store = candidate_store
        self._max_traces = max_traces_per_episode
        self._lookback_limit = lookback_limit
        self._boundary_threshold = boundary_threshold

    def evaluate(self, player_id: PlayerId) -> EpisodeChunkDecision:
        """未処理 trace を見て、今 episode candidate を作るべきか判定する。"""
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        traces = self._collect_unprocessed_traces(player_id)
        if not traces:
            return EpisodeChunkDecision(False, 0, (), ())

        selected = traces[: self._max_traces]
        source_ids = tuple(t.source_id for t in selected)
        score, reasons = self._score(selected, truncated=len(traces) > len(selected))
        return EpisodeChunkDecision(
            should_create_candidate=score >= self._boundary_threshold,
            boundary_score=score,
            boundary_reasons=reasons,
            source_trace_ids=source_ids,
        )

    def create_candidate_if_ready(self, player_id: PlayerId) -> EpisodeCandidate | None:
        """区切り時なら EpisodeCandidate を作成して保存する。"""
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        traces = self._collect_unprocessed_traces(player_id)
        if not traces:
            return None
        selected = traces[: self._max_traces]
        score, reasons = self._score(selected, truncated=len(traces) > len(selected))
        if score < self._boundary_threshold:
            return None

        candidate = EpisodeCandidate(
            candidate_id=f"episode-candidate-{uuid4().hex}",
            agent_id=player_id.value,
            created_at=datetime.now(),
            source_trace_ids=tuple(t.source_id for t in selected),
            started_at=selected[0].occurred_at,
            ended_at=selected[-1].occurred_at,
            trace_count=len(selected),
            boundary_score=score,
            boundary_reasons=reasons,
        )
        self._candidate_store.add(player_id, candidate)
        return candidate

    def _collect_unprocessed_traces(self, player_id: PlayerId) -> Tuple[_TraceRef, ...]:
        actions = self._action_trace_store.get_recent(player_id, self._lookback_limit)
        observations = self._observation_trace_store.get_recent(
            player_id, self._lookback_limit
        )
        refs = []
        for trace in actions:
            refs.append(_TraceRef(f"action:{trace.trace_id}", trace.occurred_at, trace))
        for trace in observations:
            refs.append(
                _TraceRef(f"observation:{trace.trace_id}", trace.occurred_at, trace)
            )
        refs.sort(key=lambda item: item.occurred_at)
        return tuple(
            ref
            for ref in refs
            if not self._candidate_store.contains_source_trace(player_id, ref.source_id)
        )

    def _score(
        self,
        traces: Tuple[_TraceRef, ...],
        *,
        truncated: bool,
    ) -> Tuple[int, Tuple[str, ...]]:
        score = 0
        reasons = []

        if len(traces) >= self._max_traces or truncated:
            score += 100
            reasons.append("hard_limit")

        if any(
            isinstance(ref.trace, ActionExperienceTrace)
            and not ref.trace.result_success
            for ref in traces
        ):
            score += 70
            reasons.append("action_failure")

        if any(
            isinstance(ref.trace, ObservationExperienceTrace)
            and ref.trace.perceived_salience == "high"
            for ref in traces
        ):
            score += 70
            reasons.append("high_salience_observation")

        if any(
            isinstance(ref.trace, ObservationExperienceTrace)
            and ref.trace.observation_kind == "intervention_to_self"
            for ref in traces
        ):
            score += 60
            reasons.append("self_intervention")

        if any(
            isinstance(ref.trace, ActionExperienceTrace)
            and ref.trace.emotion_hint in _STRONG_EMOTIONS
            for ref in traces
        ):
            score += 30
            reasons.append("strong_emotion")

        if self._has_location_context_change(traces):
            score += 40
            reasons.append("location_context_changed")

        if self._has_activity_change(traces):
            score += 20
            reasons.append("activity_changed")

        return score, tuple(dict.fromkeys(reasons))

    def _has_location_context_change(self, traces: Tuple[_TraceRef, ...]) -> bool:
        values = []
        for ref in traces:
            trace = ref.trace
            if isinstance(trace, ActionExperienceTrace):
                value = trace.current_state_snapshot.strip()
            else:
                value = trace.location_snapshot.strip()
            if value:
                values.append(value)
        return len(set(values)) > 1

    def _has_activity_change(self, traces: Tuple[_TraceRef, ...]) -> bool:
        values = []
        for ref in traces:
            trace = ref.trace
            if isinstance(trace, ActionExperienceTrace):
                values.append(trace.tool_name.split("_", 1)[0])
            else:
                values.append(trace.observation_kind)
        return len(set(values)) > 1
