"""ルールベースの Episode Encoder（LLM 不使用）。テストとベースライン用。"""

from __future__ import annotations

from datetime import datetime
from typing import Tuple
from uuid import uuid4

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionExperienceTrace,
    EpisodeCandidate,
    EpisodeEncodingContextDto,
    ObservationExperienceTrace,
    SubjectiveEpisode,
    SubjectiveFelt,
    SubjectivePredictionError,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    ExperienceTraceUnion,
    IEpisodeEncoder,
)
from ai_rpg_world.application.llm.services.episodic_cue_extraction import episodic_cues_from_traces


class StubEpisodeEncoder(IEpisodeEncoder):
    """trace 本文を連結・要約した主観エピソードを決定的に生成する。"""

    def encode(
        self,
        context: EpisodeEncodingContextDto,
        candidate: EpisodeCandidate,
        traces: Tuple[ExperienceTraceUnion, ...],
    ) -> SubjectiveEpisode:
        if not isinstance(context, EpisodeEncodingContextDto):
            raise TypeError("context must be EpisodeEncodingContextDto")
        if not isinstance(candidate, EpisodeCandidate):
            raise TypeError("candidate must be EpisodeCandidate")
        if not isinstance(traces, tuple):
            raise TypeError("traces must be tuple")
        if len(traces) != len(candidate.source_trace_ids):
            raise ValueError("traces length must match candidate.source_trace_ids")

        obs_lines: list[str] = []
        interp_lines: list[str] = []
        last_action: ActionExperienceTrace | None = None
        for t in traces:
            if isinstance(t, ActionExperienceTrace):
                obs_lines.append(
                    f"[行動] {t.tool_name}: {t.tool_result.strip()[:400]}"
                )
                interp_lines.append(
                    f"{t.inner_thought.strip()}（意図: {t.intention.strip()}）"
                )
                last_action = t
            elif isinstance(t, ObservationExperienceTrace):
                obs_lines.append(
                    f"[観測/{t.observation_kind}] {t.observation_summary.strip()[:400]}"
                )
            else:
                raise TypeError("traces must be ActionExperienceTrace or ObservationExperienceTrace")

        observed = "\n".join(obs_lines) if obs_lines else "（材料なし）"
        interpreted = "\n".join(interp_lines) if interp_lines else "（観測中心の区間）"

        if last_action is not None:
            expected = last_action.expected_result.strip()
            intended = last_action.intention.strip()
            felt = SubjectiveFelt(
                primary_emotion=last_action.emotion_hint,
                secondary_emotions=(),
                emotion_note="",
            )
            if last_action.result_success:
                pred = SubjectivePredictionError(
                    level="none",
                    reason="ツール実行は成功として記録されている。",
                )
            else:
                pred = SubjectivePredictionError(
                    level="medium",
                    reason="ツール実行が失敗として記録されている。",
                )
        else:
            expected = "（このチャンクに該当する行動予測は無い）"
            intended = "（観測の受容）"
            felt = SubjectiveFelt(primary_emotion="neutral", secondary_emotions=(), emotion_note="")
            pred = SubjectivePredictionError(level="none", reason="観測のみのチャンク。")

        salience = tuple(candidate.boundary_reasons)
        importance = "high" if candidate.boundary_score >= 100 or "action_failure" in salience else "medium"

        narrative_cues = episodic_cues_from_traces(traces)

        episode = SubjectiveEpisode(
            episode_id=f"subjective-episode-{uuid4().hex}",
            agent_id=candidate.agent_id,
            created_at=datetime.now(),
            started_at_tick=None,
            ended_at_tick=None,
            source_trace_ids=candidate.source_trace_ids,
            observed=observed,
            interpreted=interpreted,
            felt=felt,
            intended=intended,
            expected=expected,
            prediction_error=pred,
            belief_at_encoding=context.current_beliefs.strip(),
            belief_update_candidates=(),
            relationship_deltas=(),
            cue_keys=(),
            cues=narrative_cues,
            importance=importance,
            salience_reasons=salience,
            recall_count=0,
            last_recalled_at=None,
            reflections=(),
            reconsolidation_history=(),
            memory_reflection_journal=(),
            confidence="medium",
            candidate_id=candidate.candidate_id,
        )
        return episode
