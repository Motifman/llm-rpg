"""LLM 向け表示・記憶層の DTO"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple

from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier


# 再スケジュール対象とする error_code（1起動1ツール前提で次tickで再試行する）
# LLM_AUTHENTICATION_ERROR は恒久障害のため除外
_RESCHEDULE_ERROR_CODES = frozenset({
    "NO_TOOL_CALL",           # LLM がツールを返さなかった
    "LLM_API_CALL_FAILED",    # 一時的 API 失敗
    "LLM_RATE_LIMIT",         # レート制限
    "INVALID_DESTINATION_LABEL",  # ラベル未解決（次 tick で解消の可能性）
})


def should_reschedule_for_next_tick(dto: "LlmCommandResultDto") -> bool:
    """
    LlmCommandResultDto から次 tick で再スケジュールすべきか判定する。
    1起動1ツール前提の保守的継続契約に従う。
    """
    if dto.success:
        return False
    return is_reschedulable_error_code(dto.error_code)


def is_reschedulable_error_code(error_code: Optional[str]) -> bool:
    """error_code が再スケジュール対象かどうか。1起動1ツール前提の継続契約用。"""
    return error_code is not None and error_code in _RESCHEDULE_ERROR_CODES


@dataclass(frozen=True)
class LlmCommandResultDto:
    """
    オーケストレータがツール実行結果を IActionResultStore に渡す際の標準形。
    成功時は message に成功メッセージ、失敗時は message にエラー内容、remediation に対処ヒントを入れる。
    should_reschedule: 次 tick で再スケジュールすべきか（1起動1ツール前提の継続契約用）。
    """

    success: bool
    message: str
    error_code: Optional[str] = None
    remediation: Optional[str] = None
    should_reschedule: bool = False
    was_no_op: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.success, bool):
            raise TypeError("success must be bool")
        if not isinstance(self.message, str):
            raise TypeError("message must be str")
        if self.error_code is not None and not isinstance(self.error_code, str):
            raise TypeError("error_code must be str or None")
        if self.remediation is not None and not isinstance(self.remediation, str):
            raise TypeError("remediation must be str or None")
        if not isinstance(self.should_reschedule, bool):
            raise TypeError("should_reschedule must be bool")
        if not isinstance(self.was_no_op, bool):
            raise TypeError("was_no_op must be bool")


@dataclass(frozen=True)
class SystemPromptPlayerInfoDto:
    """システムプロンプト生成用のプレイヤー情報 DTO"""

    player_name: str
    role: str
    race: str
    element: str
    game_description: str
    persona_block: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.player_name, str):
            raise TypeError("player_name must be str")
        if not isinstance(self.role, str):
            raise TypeError("role must be str")
        if not isinstance(self.race, str):
            raise TypeError("race must be str")
        if not isinstance(self.element, str):
            raise TypeError("element must be str")
        if not isinstance(self.game_description, str):
            raise TypeError("game_description must be str")
        if not isinstance(self.persona_block, str):
            raise TypeError("persona_block must be str")


@dataclass(frozen=True)
class ActionResultEntry:
    """行動結果 1 件（直近の出来事のマージ用）"""

    occurred_at: datetime
    action_summary: str
    result_summary: str
    success: bool = True
    error_code: Optional[str] = None
    tool_name: Optional[str] = None
    argument_fingerprint: Optional[str] = None
    should_reschedule: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.occurred_at, datetime):
            raise TypeError("occurred_at must be datetime")
        if not isinstance(self.action_summary, str):
            raise TypeError("action_summary must be str")
        if not isinstance(self.result_summary, str):
            raise TypeError("result_summary must be str")
        if not isinstance(self.success, bool):
            raise TypeError("success must be bool")
        if self.error_code is not None and not isinstance(self.error_code, str):
            raise TypeError("error_code must be str or None")
        if self.tool_name is not None and not isinstance(self.tool_name, str):
            raise TypeError("tool_name must be str or None")
        if self.argument_fingerprint is not None and not isinstance(
            self.argument_fingerprint, str
        ):
            raise TypeError("argument_fingerprint must be str or None")
        if not isinstance(self.should_reschedule, bool):
            raise TypeError("should_reschedule must be bool")


EmotionHint = Literal[
    "curiosity",
    "caution",
    "fear",
    "anxiety",
    "urgency",
    "relief",
    "hope",
    "frustration",
    "confusion",
    "trust",
    "distrust",
    "determination",
    "regret",
    "surprise",
    "neutral",
]

ObservationTraceKind = Literal[
    "world_event",
    "other_agent_action",
    "speech",
    "environment_change",
    "intervention_to_self",
    "system_notice",
]

EpisodeCandidateStatus = Literal["pending_encoding", "encoded", "encoding_failed"]


EMOTION_HINT_VALUES: Tuple[str, ...] = (
    "curiosity",
    "caution",
    "fear",
    "anxiety",
    "urgency",
    "relief",
    "hope",
    "frustration",
    "confusion",
    "trust",
    "distrust",
    "determination",
    "regret",
    "surprise",
    "neutral",
)


@dataclass(frozen=True)
class ActionExperienceTrace:
    """能動的な tool 実行から作る、主観的 episode 生成前の体験材料。"""

    trace_id: str
    agent_id: int
    occurred_at: datetime
    tool_name: str
    tool_args: Dict[str, Any]
    inner_thought: str
    intention: str
    expected_result: str
    attention: str
    emotion_hint: EmotionHint
    tool_result: str
    result_success: bool
    error_code: Optional[str] = None
    current_state_snapshot: str = ""
    current_goals_snapshot: str = ""
    current_beliefs_snapshot: str = ""
    identity_snapshot: str = ""
    persona_snapshot: str = ""
    working_memory_snapshot: Tuple[str, ...] = ()
    action_result_ref: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.trace_id, str):
            raise TypeError("trace_id must be str")
        if not isinstance(self.agent_id, int):
            raise TypeError("agent_id must be int")
        if not isinstance(self.occurred_at, datetime):
            raise TypeError("occurred_at must be datetime")
        if not isinstance(self.tool_name, str):
            raise TypeError("tool_name must be str")
        if not isinstance(self.tool_args, dict):
            raise TypeError("tool_args must be dict")
        for field_name in (
            "inner_thought",
            "intention",
            "expected_result",
            "attention",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be str")
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.emotion_hint not in EMOTION_HINT_VALUES:
            raise ValueError("emotion_hint must be one of EMOTION_HINT_VALUES")
        if not isinstance(self.tool_result, str):
            raise TypeError("tool_result must be str")
        if not isinstance(self.result_success, bool):
            raise TypeError("result_success must be bool")
        if self.error_code is not None and not isinstance(self.error_code, str):
            raise TypeError("error_code must be str or None")
        for field_name in (
            "current_state_snapshot",
            "current_goals_snapshot",
            "current_beliefs_snapshot",
            "identity_snapshot",
            "persona_snapshot",
        ):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be str")
        if not isinstance(self.working_memory_snapshot, tuple):
            raise TypeError("working_memory_snapshot must be tuple")
        if not all(isinstance(item, str) for item in self.working_memory_snapshot):
            raise TypeError("working_memory_snapshot must contain only str")
        if self.action_result_ref is not None and not isinstance(
            self.action_result_ref, str
        ):
            raise TypeError("action_result_ref must be str or None")


@dataclass(frozen=True)
class ObservationExperienceTrace:
    """Observation pipeline 由来の受動観測から作る体験材料。"""

    trace_id: str
    agent_id: int
    occurred_at: datetime
    observation_summary: str
    observation_kind: ObservationTraceKind
    structured: Dict[str, Any]
    game_time_label: Optional[str] = None
    location_snapshot: str = ""
    visible_context_summary: str = ""
    attention_context: str = ""
    perceived_salience: str = "normal"
    source_observation_ids: Tuple[str, ...] = ()
    world_event_refs: Tuple[str, ...] = ()
    visible_agents: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.trace_id, str):
            raise TypeError("trace_id must be str")
        if not isinstance(self.agent_id, int):
            raise TypeError("agent_id must be int")
        if not isinstance(self.occurred_at, datetime):
            raise TypeError("occurred_at must be datetime")
        if not isinstance(self.observation_summary, str):
            raise TypeError("observation_summary must be str")
        if not self.observation_summary.strip():
            raise ValueError("observation_summary must not be empty")
        if self.observation_kind not in (
            "world_event",
            "other_agent_action",
            "speech",
            "environment_change",
            "intervention_to_self",
            "system_notice",
        ):
            raise ValueError("observation_kind must be a known observation trace kind")
        if not isinstance(self.structured, dict):
            raise TypeError("structured must be dict")
        if self.game_time_label is not None and not isinstance(
            self.game_time_label, str
        ):
            raise TypeError("game_time_label must be str or None")
        for field_name in (
            "location_snapshot",
            "visible_context_summary",
            "attention_context",
            "perceived_salience",
        ):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be str")
        for field_name in (
            "source_observation_ids",
            "world_event_refs",
            "visible_agents",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                raise TypeError(f"{field_name} must be tuple")
            if not all(isinstance(item, str) for item in value):
                raise TypeError(f"{field_name} must contain only str")


@dataclass(frozen=True)
class EpisodeChunkDecision:
    """未処理 trace 群を今 episode candidate として切るべきかの判定結果。"""

    should_create_candidate: bool
    boundary_score: int
    boundary_reasons: Tuple[str, ...]
    source_trace_ids: Tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.should_create_candidate, bool):
            raise TypeError("should_create_candidate must be bool")
        if not isinstance(self.boundary_score, int):
            raise TypeError("boundary_score must be int")
        if not isinstance(self.boundary_reasons, tuple):
            raise TypeError("boundary_reasons must be tuple")
        if not all(isinstance(item, str) for item in self.boundary_reasons):
            raise TypeError("boundary_reasons must contain only str")
        if not isinstance(self.source_trace_ids, tuple):
            raise TypeError("source_trace_ids must be tuple")
        if not all(isinstance(item, str) for item in self.source_trace_ids):
            raise TypeError("source_trace_ids must contain only str")


@dataclass(frozen=True)
class EpisodeCandidate:
    """Episode Encoder に渡す前の trace chunk。"""

    candidate_id: str
    agent_id: int
    created_at: datetime
    source_trace_ids: Tuple[str, ...]
    started_at: datetime
    ended_at: datetime
    trace_count: int
    boundary_score: int
    boundary_reasons: Tuple[str, ...]
    status: EpisodeCandidateStatus = "pending_encoding"
    subjective_episode_id: Optional[str] = None
    encoding_error: Optional[str] = None
    encoding_retry_count: int = 0
    last_encoding_failure_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str):
            raise TypeError("candidate_id must be str")
        if not isinstance(self.agent_id, int):
            raise TypeError("agent_id must be int")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be datetime")
        if not isinstance(self.source_trace_ids, tuple):
            raise TypeError("source_trace_ids must be tuple")
        if not self.source_trace_ids:
            raise ValueError("source_trace_ids must not be empty")
        if not all(isinstance(item, str) for item in self.source_trace_ids):
            raise TypeError("source_trace_ids must contain only str")
        if not isinstance(self.started_at, datetime):
            raise TypeError("started_at must be datetime")
        if not isinstance(self.ended_at, datetime):
            raise TypeError("ended_at must be datetime")
        if self.ended_at < self.started_at:
            raise ValueError("ended_at must be greater than or equal to started_at")
        if not isinstance(self.trace_count, int):
            raise TypeError("trace_count must be int")
        if self.trace_count <= 0:
            raise ValueError("trace_count must be greater than 0")
        if self.trace_count != len(self.source_trace_ids):
            raise ValueError("trace_count must match source_trace_ids length")
        if not isinstance(self.boundary_score, int):
            raise TypeError("boundary_score must be int")
        if not isinstance(self.boundary_reasons, tuple):
            raise TypeError("boundary_reasons must be tuple")
        if not all(isinstance(item, str) for item in self.boundary_reasons):
            raise TypeError("boundary_reasons must contain only str")
        if self.status not in ("pending_encoding", "encoded", "encoding_failed"):
            raise ValueError("status must be pending_encoding, encoded, or encoding_failed")
        if self.subjective_episode_id is not None and not isinstance(
            self.subjective_episode_id, str
        ):
            raise TypeError("subjective_episode_id must be str or None")
        if self.encoding_error is not None and not isinstance(self.encoding_error, str):
            raise TypeError("encoding_error must be str or None")
        if not isinstance(self.encoding_retry_count, int):
            raise TypeError("encoding_retry_count must be int")
        if self.encoding_retry_count < 0:
            raise ValueError("encoding_retry_count must be non-negative")
        if self.last_encoding_failure_at is not None and not isinstance(
            self.last_encoding_failure_at, datetime
        ):
            raise TypeError("last_encoding_failure_at must be datetime or None")
        if self.status == "encoded":
            if (
                not self.subjective_episode_id
                or not str(self.subjective_episode_id).strip()
            ):
                raise ValueError("encoded candidate must have non-empty subjective_episode_id")
            if self.encoding_error is not None:
                raise ValueError("encoded candidate must have encoding_error None")
        if self.status == "pending_encoding":
            if self.subjective_episode_id is not None:
                raise ValueError("pending_encoding candidate must have subjective_episode_id None")
            if self.encoding_error is not None:
                raise ValueError("pending_encoding candidate must have encoding_error None")
        if self.status == "encoding_failed":
            if self.subjective_episode_id is not None:
                raise ValueError("encoding_failed candidate must have subjective_episode_id None")
            if not self.encoding_error or not self.encoding_error.strip():
                raise ValueError("encoding_failed candidate must have non-empty encoding_error")


PredictionErrorLevel = Literal["none", "small", "medium", "large"]
SubjectiveImportance = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class SubjectiveFelt:
    """主観エピソード上の感情表現。"""

    primary_emotion: str
    secondary_emotions: Tuple[str, ...] = ()
    emotion_note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.primary_emotion, str):
            raise TypeError("primary_emotion must be str")
        if not self.primary_emotion.strip():
            raise ValueError("primary_emotion must not be empty")
        if not isinstance(self.secondary_emotions, tuple):
            raise TypeError("secondary_emotions must be tuple")
        if not all(isinstance(item, str) for item in self.secondary_emotions):
            raise TypeError("secondary_emotions must contain only str")
        if not isinstance(self.emotion_note, str):
            raise TypeError("emotion_note must be str")


@dataclass(frozen=True)
class SubjectivePredictionError:
    level: PredictionErrorLevel
    reason: str = ""

    def __post_init__(self) -> None:
        if self.level not in ("none", "small", "medium", "large"):
            raise ValueError("level must be none, small, medium, or large")
        if not isinstance(self.reason, str):
            raise TypeError("reason must be str")


@dataclass(frozen=True)
class MemoryReflectionEpisodePatchDto:
    """Memory Reflection がエピソードに追記する差分（§10 episode_patch）。"""

    emphasized: str = ""
    faded: str = ""
    new_meaning: str = ""
    emotional_tone_shift: str = ""

    def __post_init__(self) -> None:
        for n in ("emphasized", "faded", "new_meaning", "emotional_tone_shift"):
            if not isinstance(getattr(self, n), str):
                raise TypeError(f"{n} must be str")


@dataclass(frozen=True)
class MemoryReflectionSemanticCandidateDto:
    summary: str
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.summary, str):
            raise TypeError("summary must be str")
        if not isinstance(self.note, str):
            raise TypeError("note must be str")


@dataclass(frozen=True)
class MemoryReflectionIdentityCandidateDto:
    summary: str
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.summary, str):
            raise TypeError("summary must be str")
        if not isinstance(self.note, str):
            raise TypeError("note must be str")


@dataclass(frozen=True)
class MemoryReflectionJournalEntry:
    """エピソードへの Memory Reflection 結果の追記レコード（元 encoding / source trace は変更しない）。"""

    entry_id: str
    created_at: datetime
    correlation_id: str
    trigger: str
    recall_trigger: str
    current_interpretation: str
    effect_on_decision: str
    episode_patch: MemoryReflectionEpisodePatchDto
    semantic_update_candidates: Tuple[MemoryReflectionSemanticCandidateDto, ...] = ()
    identity_update_candidates: Tuple[MemoryReflectionIdentityCandidateDto, ...] = ()
    raw_payload_digest: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.entry_id, str) or not self.entry_id.strip():
            raise ValueError("entry_id must be non-empty str")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be datetime")
        if not isinstance(self.correlation_id, str):
            raise TypeError("correlation_id must be str")
        if not isinstance(self.trigger, str) or not self.trigger.strip():
            raise ValueError("trigger must be non-empty str")
        for n in ("recall_trigger", "current_interpretation", "effect_on_decision"):
            if not isinstance(getattr(self, n), str):
                raise TypeError(f"{n} must be str")
        if not isinstance(self.episode_patch, MemoryReflectionEpisodePatchDto):
            raise TypeError("episode_patch must be MemoryReflectionEpisodePatchDto")
        if not isinstance(self.semantic_update_candidates, tuple):
            raise TypeError("semantic_update_candidates must be tuple")
        if not all(
            isinstance(x, MemoryReflectionSemanticCandidateDto)
            for x in self.semantic_update_candidates
        ):
            raise TypeError(
                "semantic_update_candidates must contain MemoryReflectionSemanticCandidateDto"
            )
        if not isinstance(self.identity_update_candidates, tuple):
            raise TypeError("identity_update_candidates must be tuple")
        if not all(
            isinstance(x, MemoryReflectionIdentityCandidateDto)
            for x in self.identity_update_candidates
        ):
            raise TypeError(
                "identity_update_candidates must contain MemoryReflectionIdentityCandidateDto"
            )
        if not isinstance(self.raw_payload_digest, str):
            raise TypeError("raw_payload_digest must be str")


@dataclass(frozen=True)
class BeliefUpdateCandidateEntry:
    summary: str
    confidence: SubjectiveImportance = "medium"
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.summary, str):
            raise TypeError("summary must be str")
        if not self.summary.strip():
            raise ValueError("summary must not be empty")
        if self.confidence not in ("low", "medium", "high"):
            raise ValueError("confidence must be low, medium, or high")
        if not isinstance(self.note, str):
            raise TypeError("note must be str")


@dataclass(frozen=True)
class RelationshipDeltaEntry:
    target: str
    delta_summary: str
    confidence: SubjectiveImportance = "medium"

    def __post_init__(self) -> None:
        if not isinstance(self.target, str):
            raise TypeError("target must be str")
        if not self.target.strip():
            raise ValueError("target must not be empty")
        if not isinstance(self.delta_summary, str):
            raise TypeError("delta_summary must be str")
        if not self.delta_summary.strip():
            raise ValueError("delta_summary must not be empty")
        if self.confidence not in ("low", "medium", "high"):
            raise ValueError("confidence must be low, medium, or high")


@dataclass(frozen=True)
class EpisodeEncodingContextDto:
    """Episode Encoder に渡すエージェント文脈（Phase 3 はプロンプト由来の薄い文字列から組み立て可能）。"""

    persona_summary: str = ""
    current_goals: str = ""
    current_beliefs: str = ""
    identity_summary: str = ""

    def __post_init__(self) -> None:
        for name in (
            "persona_summary",
            "current_goals",
            "current_beliefs",
            "identity_summary",
        ):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be str")


@dataclass(frozen=True)
class SubjectiveEpisode:
    """主観的エピソード（v2）。既存 EpisodeMemoryEntry とは独立した DTO。"""

    episode_id: str
    agent_id: int
    created_at: datetime
    started_at_tick: Optional[int]
    ended_at_tick: Optional[int]
    source_trace_ids: Tuple[str, ...]
    observed: str
    interpreted: str
    felt: SubjectiveFelt
    intended: str
    expected: str
    prediction_error: SubjectivePredictionError
    belief_at_encoding: str = ""
    belief_update_candidates: Tuple[BeliefUpdateCandidateEntry, ...] = ()
    relationship_deltas: Tuple[RelationshipDeltaEntry, ...] = ()
    cue_keys: Tuple[str, ...] = ()
    importance: SubjectiveImportance = "medium"
    salience_reasons: Tuple[str, ...] = ()
    recall_count: int = 0
    last_recalled_at: Optional[datetime] = None
    reflections: Tuple[str, ...] = ()
    reconsolidation_history: Tuple[str, ...] = ()
    memory_reflection_journal: Tuple[MemoryReflectionJournalEntry, ...] = ()
    confidence: SubjectiveImportance = "medium"
    candidate_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.episode_id, str):
            raise TypeError("episode_id must be str")
        if not self.episode_id.strip():
            raise ValueError("episode_id must not be empty")
        if not isinstance(self.agent_id, int):
            raise TypeError("agent_id must be int")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be datetime")
        if self.started_at_tick is not None and not isinstance(self.started_at_tick, int):
            raise TypeError("started_at_tick must be int or None")
        if self.ended_at_tick is not None and not isinstance(self.ended_at_tick, int):
            raise TypeError("ended_at_tick must be int or None")
        if not isinstance(self.source_trace_ids, tuple):
            raise TypeError("source_trace_ids must be tuple")
        if not self.source_trace_ids:
            raise ValueError("source_trace_ids must not be empty")
        if not all(isinstance(s, str) for s in self.source_trace_ids):
            raise TypeError("source_trace_ids must contain only str")
        for name in ("observed", "interpreted", "intended", "expected", "belief_at_encoding"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be str")
        if not isinstance(self.felt, SubjectiveFelt):
            raise TypeError("felt must be SubjectiveFelt")
        if not isinstance(self.prediction_error, SubjectivePredictionError):
            raise TypeError("prediction_error must be SubjectivePredictionError")
        if not isinstance(self.belief_update_candidates, tuple):
            raise TypeError("belief_update_candidates must be tuple")
        if not all(isinstance(x, BeliefUpdateCandidateEntry) for x in self.belief_update_candidates):
            raise TypeError("belief_update_candidates must contain BeliefUpdateCandidateEntry")
        if not isinstance(self.relationship_deltas, tuple):
            raise TypeError("relationship_deltas must be tuple")
        if not all(isinstance(x, RelationshipDeltaEntry) for x in self.relationship_deltas):
            raise TypeError("relationship_deltas must contain RelationshipDeltaEntry")
        if not isinstance(self.cue_keys, tuple):
            raise TypeError("cue_keys must be tuple")
        if not all(isinstance(x, str) for x in self.cue_keys):
            raise TypeError("cue_keys must contain only str")
        if self.importance not in ("low", "medium", "high"):
            raise ValueError("importance must be low, medium, or high")
        if not isinstance(self.salience_reasons, tuple):
            raise TypeError("salience_reasons must be tuple")
        if not all(isinstance(x, str) for x in self.salience_reasons):
            raise TypeError("salience_reasons must contain only str")
        if not isinstance(self.recall_count, int) or self.recall_count < 0:
            raise TypeError("recall_count must be a non-negative int")
        if self.last_recalled_at is not None and not isinstance(
            self.last_recalled_at, datetime
        ):
            raise TypeError("last_recalled_at must be datetime or None")
        if not isinstance(self.reflections, tuple):
            raise TypeError("reflections must be tuple")
        if not all(isinstance(x, str) for x in self.reflections):
            raise TypeError("reflections must contain only str")
        if not isinstance(self.reconsolidation_history, tuple):
            raise TypeError("reconsolidation_history must be tuple")
        if not all(isinstance(x, str) for x in self.reconsolidation_history):
            raise TypeError("reconsolidation_history must contain only str")
        if not isinstance(self.memory_reflection_journal, tuple):
            raise TypeError("memory_reflection_journal must be tuple")
        if not all(
            isinstance(x, MemoryReflectionJournalEntry)
            for x in self.memory_reflection_journal
        ):
            raise TypeError(
                "memory_reflection_journal must contain MemoryReflectionJournalEntry"
            )
        if self.confidence not in ("low", "medium", "high"):
            raise ValueError("confidence must be low, medium, or high")
        if not isinstance(self.candidate_id, str):
            raise TypeError("candidate_id must be str")


@dataclass(frozen=True)
class ToolDefinitionDto:
    """1 つのツール定義（OpenAI tools 形式の name / description / parameters 用）。"""

    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("name must be str")
        if not isinstance(self.description, str):
            raise TypeError("description must be str")
        if not isinstance(self.parameters, dict):
            raise TypeError("parameters must be dict")


@dataclass(frozen=True)
class ToolRuntimeTargetDto:
    """一時ラベルから内部IDへ解決するためのターゲット情報。"""

    label: str
    kind: str
    display_name: str
    player_id: Optional[int] = None
    world_object_id: Optional[int] = None
    spot_id: Optional[int] = None
    location_area_id: Optional[int] = None
    destination_type: Optional[str] = None
    distance: Optional[int] = None
    direction: Optional[str] = None
    target_x: Optional[int] = None
    target_y: Optional[int] = None
    target_z: Optional[int] = None
    relative_dx: Optional[int] = None
    relative_dy: Optional[int] = None
    relative_dz: Optional[int] = None
    interaction_type: Optional[str] = None
    available_interactions: Tuple[str, ...] = ()
    item_instance_id: Optional[int] = None
    inventory_slot_id: Optional[int] = None
    chest_world_object_id: Optional[int] = None
    conversation_choice_index: Optional[int] = None
    skill_loadout_id: Optional[int] = None
    skill_slot_index: Optional[int] = None
    skill_id: Optional[int] = None
    deck_tier: Optional[DeckTier] = None
    progress_id: Optional[int] = None
    proposal_id: Optional[int] = None
    target_slot_index: Optional[int] = None
    target_slot_display_name: Optional[str] = None
    attention_level_value: Optional[str] = None
    quest_id: Optional[int] = None
    guild_id: Optional[int] = None
    shop_id: Optional[int] = None
    trade_id: Optional[int] = None
    listing_id: Optional[int] = None

    def __post_init__(self) -> None:
        if not isinstance(self.label, str):
            raise TypeError("label must be str")
        if not isinstance(self.kind, str):
            raise TypeError("kind must be str")
        if not isinstance(self.display_name, str):
            raise TypeError("display_name must be str")
        if self.player_id is not None and not isinstance(self.player_id, int):
            raise TypeError("player_id must be int or None")
        if self.world_object_id is not None and not isinstance(self.world_object_id, int):
            raise TypeError("world_object_id must be int or None")
        if self.spot_id is not None and not isinstance(self.spot_id, int):
            raise TypeError("spot_id must be int or None")
        if self.location_area_id is not None and not isinstance(self.location_area_id, int):
            raise TypeError("location_area_id must be int or None")
        if self.destination_type is not None and not isinstance(self.destination_type, str):
            raise TypeError("destination_type must be str or None")
        if self.distance is not None and not isinstance(self.distance, int):
            raise TypeError("distance must be int or None")
        if self.direction is not None and not isinstance(self.direction, str):
            raise TypeError("direction must be str or None")
        if self.target_x is not None and not isinstance(self.target_x, int):
            raise TypeError("target_x must be int or None")
        if self.target_y is not None and not isinstance(self.target_y, int):
            raise TypeError("target_y must be int or None")
        if self.target_z is not None and not isinstance(self.target_z, int):
            raise TypeError("target_z must be int or None")
        if self.relative_dx is not None and not isinstance(self.relative_dx, int):
            raise TypeError("relative_dx must be int or None")
        if self.relative_dy is not None and not isinstance(self.relative_dy, int):
            raise TypeError("relative_dy must be int or None")
        if self.relative_dz is not None and not isinstance(self.relative_dz, int):
            raise TypeError("relative_dz must be int or None")
        if self.interaction_type is not None and not isinstance(self.interaction_type, str):
            raise TypeError("interaction_type must be str or None")
        if self.item_instance_id is not None and not isinstance(self.item_instance_id, int):
            raise TypeError("item_instance_id must be int or None")
        if self.inventory_slot_id is not None and not isinstance(self.inventory_slot_id, int):
            raise TypeError("inventory_slot_id must be int or None")
        if self.chest_world_object_id is not None and not isinstance(self.chest_world_object_id, int):
            raise TypeError("chest_world_object_id must be int or None")
        if self.conversation_choice_index is not None and not isinstance(
            self.conversation_choice_index, int
        ):
            raise TypeError("conversation_choice_index must be int or None")
        if self.skill_loadout_id is not None and not isinstance(self.skill_loadout_id, int):
            raise TypeError("skill_loadout_id must be int or None")
        if self.skill_slot_index is not None and not isinstance(self.skill_slot_index, int):
            raise TypeError("skill_slot_index must be int or None")
        if self.skill_id is not None and not isinstance(self.skill_id, int):
            raise TypeError("skill_id must be int or None")
        if self.deck_tier is not None and not isinstance(self.deck_tier, DeckTier):
            raise TypeError("deck_tier must be DeckTier or None")
        if self.progress_id is not None and not isinstance(self.progress_id, int):
            raise TypeError("progress_id must be int or None")
        if self.proposal_id is not None and not isinstance(self.proposal_id, int):
            raise TypeError("proposal_id must be int or None")
        if self.target_slot_index is not None and not isinstance(self.target_slot_index, int):
            raise TypeError("target_slot_index must be int or None")
        if self.target_slot_display_name is not None and not isinstance(
            self.target_slot_display_name, str
        ):
            raise TypeError("target_slot_display_name must be str or None")
        if self.attention_level_value is not None and not isinstance(
            self.attention_level_value, str
        ):
            raise TypeError("attention_level_value must be str or None")
        if self.quest_id is not None and not isinstance(self.quest_id, int):
            raise TypeError("quest_id must be int or None")
        if self.guild_id is not None and not isinstance(self.guild_id, int):
            raise TypeError("guild_id must be int or None")
        if self.shop_id is not None and not isinstance(self.shop_id, int):
            raise TypeError("shop_id must be int or None")
        if self.trade_id is not None and not isinstance(self.trade_id, int):
            raise TypeError("trade_id must be int or None")
        if self.listing_id is not None and not isinstance(self.listing_id, int):
            raise TypeError("listing_id must be int or None")
        if not isinstance(self.available_interactions, tuple):
            raise TypeError("available_interactions must be tuple")
        for value in self.available_interactions:
            if not isinstance(value, str):
                raise TypeError("available_interactions must contain only str")


@dataclass(frozen=True)
class VisibleToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """視界内対象用の runtime target。"""


@dataclass(frozen=True)
class PlayerToolRuntimeTargetDto(VisibleToolRuntimeTargetDto):
    """プレイヤー対象用の runtime target。"""


@dataclass(frozen=True)
class NpcToolRuntimeTargetDto(VisibleToolRuntimeTargetDto):
    """NPC 対象用の runtime target。"""


@dataclass(frozen=True)
class MonsterToolRuntimeTargetDto(VisibleToolRuntimeTargetDto):
    """モンスター対象用の runtime target。"""


@dataclass(frozen=True)
class ChestToolRuntimeTargetDto(VisibleToolRuntimeTargetDto):
    """チェスト対象用の runtime target。"""


@dataclass(frozen=True)
class ResourceToolRuntimeTargetDto(VisibleToolRuntimeTargetDto):
    """採集対象用の runtime target。"""


@dataclass(frozen=True)
class ActiveHarvestToolRuntimeTargetDto(ResourceToolRuntimeTargetDto):
    """進行中採集対象用の runtime target。"""


@dataclass(frozen=True)
class WorldObjectToolRuntimeTargetDto(VisibleToolRuntimeTargetDto):
    """一般的な相互作用対象用の runtime target。"""


@dataclass(frozen=True)
class DestinationToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """移動先用の runtime target。"""


@dataclass(frozen=True)
class InventoryToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """インベントリアイテム用の runtime target。"""

    is_placeable: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.is_placeable, bool):
            raise TypeError("is_placeable must be bool")


@dataclass(frozen=True)
class ChestItemToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """チェスト内アイテム用の runtime target。"""


@dataclass(frozen=True)
class ConversationChoiceToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """会話選択肢用の runtime target。"""


@dataclass(frozen=True)
class SkillToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """スキル用の runtime target。"""


@dataclass(frozen=True)
class SkillEquipCandidateToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """装備候補スキル用の runtime target。"""


@dataclass(frozen=True)
class SkillEquipSlotToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """装備先スロット用の runtime target。"""


@dataclass(frozen=True)
class SkillProposalToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """スキル提案用の runtime target。"""


@dataclass(frozen=True)
class AwakenedActionToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """覚醒モード発動用の runtime target。"""


@dataclass(frozen=True)
class AttentionLevelToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """注意レベル用の runtime target。"""


@dataclass(frozen=True)
class QuestToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """クエスト用の runtime target。quest_id を持つ。"""


@dataclass(frozen=True)
class GuildToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """ギルド用の runtime target。guild_id を持つ。"""


@dataclass(frozen=True)
class ShopToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """ショップ用の runtime target。shop_id を持つ。"""


@dataclass(frozen=True)
class ShopListingToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """ショップ出品用の runtime target。shop_id と listing_id を持つ。"""


@dataclass(frozen=True)
class TradeToolRuntimeTargetDto(ToolRuntimeTargetDto):
    """取引用の runtime target。trade_id を持つ。"""


@dataclass(frozen=True)
class ToolRuntimeContextDto:
    """LLM UIのそのターン限定ラベル解決コンテキスト。"""

    targets: Dict[str, ToolRuntimeTargetDto]
    current_x: Optional[int] = None
    current_y: Optional[int] = None
    current_z: Optional[int] = None
    current_spot_id: Optional[int] = None
    current_area_ids: Optional[Tuple[int, ...]] = None

    def __post_init__(self) -> None:
        if not isinstance(self.targets, dict):
            raise TypeError("targets must be dict")
        for label, target in self.targets.items():
            if not isinstance(label, str):
                raise TypeError("targets keys must be str")
            if not isinstance(target, ToolRuntimeTargetDto):
                raise TypeError("targets values must be ToolRuntimeTargetDto")
        for name, value in (
            ("current_x", self.current_x),
            ("current_y", self.current_y),
            ("current_z", self.current_z),
            ("current_spot_id", self.current_spot_id),
        ):
            if value is not None and not isinstance(value, int):
                raise TypeError(f"{name} must be int or None")
        if self.current_area_ids is not None and not isinstance(self.current_area_ids, tuple):
            raise TypeError("current_area_ids must be tuple or None")
        if self.current_area_ids is not None:
            for x in self.current_area_ids:
                if not isinstance(x, int):
                    raise TypeError("current_area_ids must contain only int")

    @classmethod
    def empty(cls) -> "ToolRuntimeContextDto":
        return cls(targets={})


@dataclass(frozen=True)
class LlmUiContextDto:
    """LLM に見せる現在状態テキストと、内部用のツール実行コンテキスト。"""

    current_state_text: str
    tool_runtime_context: ToolRuntimeContextDto

    def __post_init__(self) -> None:
        if not isinstance(self.current_state_text, str):
            raise TypeError("current_state_text must be str")
        if not isinstance(self.tool_runtime_context, ToolRuntimeContextDto):
            raise TypeError("tool_runtime_context must be ToolRuntimeContextDto")


# ToolAvailabilityContext は PlayerCurrentStateDto をそのまま利用する。
# ツールの利用可否判定に必要な現在地・接続先・視界・移動先等はすべて PlayerCurrentStateDto に含まれる。

# --- 記憶モジュール（Phase 4）---

EpisodeImportance = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class MemoryRetrievalQueryDto:
    """
    予測記憶検索用のクエリ DTO。
    PlayerCurrentStateDto 由来の spot/notable/actionable と tool_names を渡すことで、
    current_state_text の文字面依存を弱める。
    検索優先度: world_object_ids > scope_keys > spot_ids > entity_ids > location_ids
    > actionable/notable > action_names > free_text_keywords
    scope_keys: 関係性メモリ用。例: quest:12, guild:3, shop:9, conversation:npc:42
    """

    entity_ids: Tuple[str, ...] = ()
    location_ids: Tuple[str, ...] = ()
    notable_labels: Tuple[str, ...] = ()
    actionable_labels: Tuple[str, ...] = ()
    action_names: Tuple[str, ...] = ()
    free_text_keywords: Tuple[str, ...] = ()
    world_object_ids: Tuple[int, ...] = ()
    spot_ids: Tuple[int, ...] = ()
    scope_keys: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, val in [
            ("entity_ids", self.entity_ids),
            ("location_ids", self.location_ids),
            ("notable_labels", self.notable_labels),
            ("actionable_labels", self.actionable_labels),
            ("action_names", self.action_names),
            ("free_text_keywords", self.free_text_keywords),
            ("scope_keys", self.scope_keys),
        ]:
            if not isinstance(val, tuple):
                raise TypeError(f"{name} must be tuple")
            for x in val:
                if not isinstance(x, str):
                    raise TypeError(f"{name} must contain only str")
        if not isinstance(self.world_object_ids, tuple):
            raise TypeError("world_object_ids must be tuple")
        for x in self.world_object_ids:
            if not isinstance(x, int):
                raise TypeError("world_object_ids must contain only int")
        if not isinstance(self.spot_ids, tuple):
            raise TypeError("spot_ids must be tuple")
        for x in self.spot_ids:
            if not isinstance(x, int):
                raise TypeError("spot_ids must contain only int")


@dataclass(frozen=True)
class EpisodeMemoryEntry:
    """エピソード記憶 1 件（記憶抽出の出力・ストアの保存単位）。
    world_object_ids, spot_id_value は stable id 検索用。display name は entity_ids, location_id に保持。
    scope_keys は関係性メモリ用。例: quest:12, guild:3, shop:9, conversation:npc:42
    """

    id: str
    context_summary: str
    action_taken: str
    outcome_summary: str
    entity_ids: Tuple[str, ...]
    location_id: Optional[str]
    timestamp: datetime
    importance: EpisodeImportance
    surprise: bool
    recall_count: int
    world_object_ids: Tuple[int, ...] = ()
    spot_id_value: Optional[int] = None
    scope_keys: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be str")
        if not isinstance(self.context_summary, str):
            raise TypeError("context_summary must be str")
        if not isinstance(self.action_taken, str):
            raise TypeError("action_taken must be str")
        if not isinstance(self.outcome_summary, str):
            raise TypeError("outcome_summary must be str")
        if not isinstance(self.entity_ids, tuple):
            raise TypeError("entity_ids must be tuple")
        for x in self.entity_ids:
            if not isinstance(x, str):
                raise TypeError("entity_ids must contain only str")
        if self.location_id is not None and not isinstance(self.location_id, str):
            raise TypeError("location_id must be str or None")
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be datetime")
        if self.importance not in ("low", "medium", "high"):
            raise TypeError("importance must be 'low', 'medium', or 'high'")
        if not isinstance(self.surprise, bool):
            raise TypeError("surprise must be bool")
        if not isinstance(self.recall_count, int) or self.recall_count < 0:
            raise TypeError("recall_count must be non-negative int")
        if not isinstance(self.world_object_ids, tuple):
            raise TypeError("world_object_ids must be tuple")
        for x in self.world_object_ids:
            if not isinstance(x, int):
                raise TypeError("world_object_ids must contain only int")
        if self.spot_id_value is not None and not isinstance(self.spot_id_value, int):
            raise TypeError("spot_id_value must be int or None")
        if not isinstance(self.scope_keys, tuple):
            raise TypeError("scope_keys must be tuple")
        for x in self.scope_keys:
            if not isinstance(x, str):
                raise TypeError("scope_keys must contain only str")


@dataclass(frozen=True)
class LongTermFactEntry:
    """長期記憶（事実・教訓）1 件。"""

    id: str
    content: str
    player_id: int
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be str")
        if not isinstance(self.content, str):
            raise TypeError("content must be str")
        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")
        if not isinstance(self.updated_at, datetime):
            raise TypeError("updated_at must be datetime")


@dataclass(frozen=True)
class MemoryLawEntry:
    """長期記憶（法則・共起）1 件。主体–関係–対象＋強度。"""

    id: str
    subject: str
    relation: str
    target: str  # 対象
    strength: float
    player_id: int

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be str")
        if not isinstance(self.subject, str):
            raise TypeError("subject must be str")
        if not isinstance(self.relation, str):
            raise TypeError("relation must be str")
        if not isinstance(self.target, str):
            raise TypeError("target must be str")
        if not isinstance(self.strength, (int, float)):
            raise TypeError("strength must be int or float")
        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")


@dataclass(frozen=True)
class SubagentEvidenceEntry:
    """subagent の evidence 1 件。"""

    binding_name: str
    source_var: str
    entry_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.binding_name, str):
            raise TypeError("binding_name must be str")
        if not isinstance(self.source_var, str):
            raise TypeError("source_var must be str")
        if not isinstance(self.entry_ids, tuple):
            raise TypeError("entry_ids must be tuple")
        for x in self.entry_ids:
            if not isinstance(x, str):
                raise TypeError("entry_ids must contain only str")


@dataclass(frozen=True)
class SubagentResultDto:
    """subagent の返却値。"""

    answer_summary: str
    evidence: Tuple[SubagentEvidenceEntry, ...]
    used_bindings: Tuple[str, ...]
    truncation_note: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.answer_summary, str):
            raise TypeError("answer_summary must be str")
        if not isinstance(self.evidence, tuple):
            raise TypeError("evidence must be tuple")
        if not isinstance(self.used_bindings, tuple):
            raise TypeError("used_bindings must be tuple")
        for x in self.used_bindings:
            if not isinstance(x, str):
                raise TypeError("used_bindings must contain only str")
        if self.truncation_note is not None and not isinstance(
            self.truncation_note, str
        ):
            raise TypeError("truncation_note must be str or None")


@dataclass(frozen=True)
class TodoEntry:
    """TODO 1 件。LLM が管理するタスクリスト用。"""

    id: str
    content: str
    added_at: datetime
    completed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be str")
        if not isinstance(self.content, str):
            raise TypeError("content must be str")
        if not isinstance(self.added_at, datetime):
            raise TypeError("added_at must be datetime")
        if not isinstance(self.completed, bool):
            raise TypeError("completed must be bool")
