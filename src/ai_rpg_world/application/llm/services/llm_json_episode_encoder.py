"""LLM が返す JSON から SubjectiveEpisode を組み立てる Encoder。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Tuple
from uuid import uuid4

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionExperienceTrace,
    BeliefUpdateCandidateEntry,
    EpisodeCandidate,
    EpisodeEncodingContextDto,
    ObservationExperienceTrace,
    RelationshipDeltaEntry,
    SubjectiveEpisode,
    SubjectiveFelt,
    SubjectivePredictionError,
)
from ai_rpg_world.application.llm.contracts.subjective_emotion_label import (
    SubjectiveEmotionLabel,
    subjective_emotion_label_values,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    ExperienceTraceUnion,
    IEpisodeEncoder,
    IEpisodeEncodingLlmPort,
)
from ai_rpg_world.application.llm.exceptions import EpisodeEncodingException

_EMOTION_VALUES_PROMPT = ", ".join(subjective_emotion_label_values())

_SYSTEM = f"""あなたは Episode Encoder である。入力 JSON の traces_digest（行動・観測の要約）と context（ペルソナ・目標・信念・同一性）を根拠に、当該エピソード区切りの「主観的エピソード」を 1 件だけ JSON で返す。
返答は **有効な JSON オブジェクト 1 つだけ**（前後に説明文やマークダウンを付けない）。

【各フィールドの役割】
- observed: エージェントが trace に書かれた範囲で**実際に知覚・確認できたこと**だけ。trace に無い事実の補完・推測は書かない。
- interpreted: **当時**その知覚をどう意味づけたか。世界の真実として断定せず、「〜と考えた」に留める。
- intended: trace の intention（行動目的）と整合する、**そのとき**向かおうとしていた方針。
- expected: trace の expected_result（行動前予測）に整合。**結果を見た後に予測を書き換えない**。
- felt:
  - primary_emotion と secondary_emotions の**各要素**は、次の英語小文字だけから選ぶ: {_EMOTION_VALUES_PROMPT}
  - emotion_note は短文（口語可）。
- prediction_error: expected と実結果（tool_result / observation 要約）を比較し、level は none|small|medium|large、reason は日本語可。
- belief_update_candidates: 信念の**更新候補**（まだ確定事実ではない）。各 summary / note は簡潔に。confidence は low|medium|high。
- relationship_deltas: **他者・団体など、trace または context に名前・呼称・役割として現れた具体的な相手**に対する「印象・関係の変化候補」だけ。抽象的な存在や雰囲気のみ（例: 霧の向こうの気配、不明な何か、世界全体）を target にしない。該当する相手がいなければ空配列 []。
- cue_keys: **想起・検索インデックス用**の短いキー。検索が日本語クエリ中心なら **短い日本語の名詞句**（例: 鍵穴, 鐘の音, 蝋燭）を混ぜてよい。ツール名・安定IDは **ASCII snake_case**（例: spot_graph_look）も併用可。3〜12 個を目安に、場所・物体・行動・他者・異常フラグなど**少なくとも 2 タイプ**を含める。1 キー 1 概念。**felt の enum 名（curiosity 等）をキーに載せない**（感情は felt に任せる）。セリフ全文や長い説明文は避ける。
- importance / confidence: low|medium|high
- source_trace_ids: 省略可。出す場合は入力の source_trace_ids と**同じ順・同じ値**。

【キー一覧】
observed, interpreted, intended, expected (各 string)
felt: {{primary_emotion, secondary_emotions: string[], emotion_note}}
prediction_error: {{level: none|small|medium|large, reason}}
belief_update_candidates: [{{summary, confidence: low|medium|high, note}}]
relationship_deltas: [{{target, delta_summary, confidence: low|medium|high}}]
cue_keys: string[]
importance, confidence: low|medium|high
"""


def episode_encoder_llm_output_json_schema() -> Dict[str, Any]:
    """vLLM / OpenAI 互換の chat.completions response_format (json_schema) 用。"""
    conf = ["low", "medium", "high"]
    pe = ["none", "small", "medium", "large"]
    emotion_list = list(subjective_emotion_label_values())
    felt_obj: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "primary_emotion": {"type": "string", "enum": emotion_list},
            "secondary_emotions": {"type": "array", "items": {"type": "string", "enum": emotion_list}},
            "emotion_note": {"type": "string"},
        },
        "required": ["primary_emotion", "secondary_emotions", "emotion_note"],
    }
    return {
        "type": "object",
        "properties": {
            "observed": {"type": "string"},
            "interpreted": {"type": "string"},
            "intended": {"type": "string"},
            "expected": {"type": "string"},
            "felt": felt_obj,
            "prediction_error": {
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": pe},
                    "reason": {"type": "string"},
                },
                "required": ["level", "reason"],
            },
            "belief_update_candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "confidence": {"type": "string", "enum": conf},
                        "note": {"type": "string"},
                    },
                    "required": ["summary", "confidence", "note"],
                },
            },
            "relationship_deltas": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string"},
                        "delta_summary": {"type": "string"},
                        "confidence": {"type": "string", "enum": conf},
                    },
                    "required": ["target", "delta_summary", "confidence"],
                },
            },
            "cue_keys": {"type": "array", "items": {"type": "string"}},
            "importance": {"type": "string", "enum": conf},
            "confidence": {"type": "string", "enum": conf},
            "source_trace_ids": {"type": "array", "items": {"type": "string"}},
            "salience_reasons": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "observed",
            "interpreted",
            "intended",
            "expected",
            "felt",
            "prediction_error",
            "belief_update_candidates",
            "relationship_deltas",
            "cue_keys",
            "importance",
            "confidence",
        ],
    }


def episode_encoder_openai_response_format() -> Dict[str, Any]:
    """OpenAI / vLLM の chat.completions `response_format` 引数用（json_schema）。"""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "subjective_episode_encoding",
            "schema": episode_encoder_llm_output_json_schema(),
        },
    }


def _raise_invalid_emotion(field_label: str, got: str) -> None:
    raise EpisodeEncodingException(
        f"{field_label} must be one of {list(subjective_emotion_label_values())}, got {got!r}"
    )


def _dict_to_felt(raw: Any) -> SubjectiveFelt:
    if not isinstance(raw, dict):
        raise EpisodeEncodingException("felt must be an object")
    primary_raw = str(raw.get("primary_emotion") or "")
    try:
        primary = SubjectiveEmotionLabel(primary_raw.strip()).value
    except ValueError:
        _raise_invalid_emotion("felt.primary_emotion", primary_raw)
    sec_raw = raw.get("secondary_emotions") or []
    if not isinstance(sec_raw, list):
        raise EpisodeEncodingException("felt.secondary_emotions must be a list")
    secondary_list: List[str] = []
    for x in sec_raw:
        if not isinstance(x, str):
            continue
        label_raw = x.strip()
        if not label_raw:
            continue
        try:
            secondary_list.append(SubjectiveEmotionLabel(label_raw).value)
        except ValueError:
            _raise_invalid_emotion("felt.secondary_emotions element", label_raw)
    secondary = tuple(secondary_list)
    note = str(raw.get("emotion_note") or "")
    return SubjectiveFelt(
        primary_emotion=primary, secondary_emotions=secondary, emotion_note=note
    )


def _dict_to_prediction_error(raw: Any) -> SubjectivePredictionError:
    if not isinstance(raw, dict):
        raise EpisodeEncodingException("prediction_error must be an object")
    level = str(raw.get("level") or "none")
    if level not in ("none", "small", "medium", "large"):
        raise EpisodeEncodingException(f"invalid prediction_error.level: {level!r}")
    reason = str(raw.get("reason") or "")
    return SubjectivePredictionError(level=level, reason=reason)  # type: ignore[arg-type]


def _belief_list(raw: Any) -> Tuple[BeliefUpdateCandidateEntry, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise EpisodeEncodingException("belief_update_candidates must be a list")
    out: List[BeliefUpdateCandidateEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            raise EpisodeEncodingException("belief_update_candidates items must be objects")
        summary = str(item.get("summary") or "").strip()
        if not summary:
            raise EpisodeEncodingException("belief summary must not be empty")
        conf = str(item.get("confidence") or "medium")
        if conf not in ("low", "medium", "high"):
            raise EpisodeEncodingException(f"invalid belief confidence: {conf!r}")
        note = str(item.get("note") or "")
        out.append(
            BeliefUpdateCandidateEntry(
                summary=summary,
                confidence=conf,  # type: ignore[arg-type]
                note=note,
            )
        )
    return tuple(out)


def _relationship_list(raw: Any) -> Tuple[RelationshipDeltaEntry, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise EpisodeEncodingException("relationship_deltas must be a list")
    out: List[RelationshipDeltaEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            raise EpisodeEncodingException("relationship_deltas items must be objects")
        target = str(item.get("target") or "").strip()
        delta = str(item.get("delta_summary") or "").strip()
        if not target or not delta:
            raise EpisodeEncodingException("relationship target/delta_summary required")
        conf = str(item.get("confidence") or "medium")
        if conf not in ("low", "medium", "high"):
            raise EpisodeEncodingException(f"invalid relationship confidence: {conf!r}")
        out.append(
            RelationshipDeltaEntry(
                target=target,
                delta_summary=delta,
                confidence=conf,  # type: ignore[arg-type]
            )
        )
    return tuple(out)


def subjective_episode_from_llm_dict(
    data: Dict[str, Any],
    candidate: EpisodeCandidate,
) -> SubjectiveEpisode:
    if not isinstance(data, dict):
        raise EpisodeEncodingException(
            "LLM output root must be object", candidate_id=candidate.candidate_id
        )
    stid = data.get("source_trace_ids")
    if stid is not None:
        if not isinstance(stid, list):
            raise EpisodeEncodingException(
                "source_trace_ids must be array if present",
                candidate_id=candidate.candidate_id,
            )
        got = tuple(str(x) for x in stid)
        if got != candidate.source_trace_ids:
            raise EpisodeEncodingException(
                "source_trace_ids must match candidate when provided",
                candidate_id=candidate.candidate_id,
            )

    def req_str(key: str) -> str:
        v = data.get(key)
        if v is None or not str(v).strip():
            raise EpisodeEncodingException(
                f"missing or empty {key}", candidate_id=candidate.candidate_id
            )
        return str(v).strip()

    observed = req_str("observed")
    interpreted = req_str("interpreted")
    intended = req_str("intended")
    expected = req_str("expected")
    felt = _dict_to_felt(data.get("felt"))
    pred = _dict_to_prediction_error(
        data.get("prediction_error") or {"level": "none", "reason": ""}
    )
    cue_raw = data.get("cue_keys") or []
    if not isinstance(cue_raw, list):
        raise EpisodeEncodingException("cue_keys must be list")
    cue_keys = tuple(str(x) for x in cue_raw if isinstance(x, str))

    imp = str(data.get("importance") or "medium")
    if imp not in ("low", "medium", "high"):
        raise EpisodeEncodingException("invalid importance")
    conf = str(data.get("confidence") or "medium")
    if conf not in ("low", "medium", "high"):
        raise EpisodeEncodingException("invalid confidence")

    sal_raw = data.get("salience_reasons") or ()
    if sal_raw in (None, ()):
        salience: Tuple[str, ...] = tuple(candidate.boundary_reasons)
    elif isinstance(sal_raw, list):
        salience = tuple(str(x) for x in sal_raw if isinstance(x, str))
    else:
        raise EpisodeEncodingException("salience_reasons must be list")

    return SubjectiveEpisode(
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
        belief_at_encoding="",
        belief_update_candidates=_belief_list(data.get("belief_update_candidates")),
        relationship_deltas=_relationship_list(data.get("relationship_deltas")),
        cue_keys=cue_keys,
        cues=(),
        importance=imp,  # type: ignore[arg-type]
        salience_reasons=salience,
        recall_count=0,
        last_recalled_at=None,
        reflections=(),
        reconsolidation_history=(),
        memory_reflection_journal=(),
        confidence=conf,  # type: ignore[arg-type]
        candidate_id=candidate.candidate_id,
    )


def _traces_digest(traces: Tuple[ExperienceTraceUnion, ...]) -> str:
    """LLM プロンプト用の trace 要約（現状はツール名・結果/要約のみ）。

    trace の `context_*` はここでは使わない。P2 でルールベース cue 化するまでの蓄積フェーズ（_encoder 外で消費）。
    """
    lines: List[str] = []
    for t in traces:
        if isinstance(t, ActionExperienceTrace):
            lines.append(f"action {t.tool_name}: {t.tool_result[:300]}")
        elif isinstance(t, ObservationExperienceTrace):
            lines.append(
                f"observation {t.observation_kind}: {t.observation_summary[:300]}"
            )
        else:
            lines.append("(unknown trace)")
    return "\n".join(lines)


class LlmJsonEpisodeEncoder(IEpisodeEncoder):
    """IEpisodeEncodingLlmPort 経由で JSON を取得し SubjectiveEpisode を構築する。"""

    def __init__(
        self,
        llm_port: IEpisodeEncodingLlmPort,
        *,
        structured_json_output: bool = True,
    ) -> None:
        if not isinstance(llm_port, IEpisodeEncodingLlmPort):
            raise TypeError("llm_port must be IEpisodeEncodingLlmPort")
        self._llm = llm_port
        self._structured_json_output = bool(structured_json_output)

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
        if len(traces) != len(candidate.source_trace_ids):
            raise ValueError("traces length must match candidate.source_trace_ids")

        payload = {
            "candidate_id": candidate.candidate_id,
            "source_trace_ids": list(candidate.source_trace_ids),
            "boundary_reasons": list(candidate.boundary_reasons),
            "context": {
                "persona_summary": context.persona_summary,
                "current_goals": context.current_goals,
                "current_beliefs": context.current_beliefs,
                "identity_summary": context.identity_summary,
            },
            "traces_digest": _traces_digest(traces),
        }
        user = json.dumps(payload, ensure_ascii=False, indent=2)
        rf = episode_encoder_openai_response_format() if self._structured_json_output else None
        raw = self._llm.complete(
            system_prompt=_SYSTEM,
            user_prompt=user,
            response_format=rf,
        )
        if not isinstance(raw, str) or not raw.strip():
            raise EpisodeEncodingException(
                "empty LLM output", candidate_id=candidate.candidate_id
            )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise EpisodeEncodingException(
                f"invalid JSON: {e}",
                candidate_id=candidate.candidate_id,
                cause=e,
            ) from e
        try:
            return subjective_episode_from_llm_dict(data, candidate)
        except EpisodeEncodingException:
            raise
        except (TypeError, ValueError) as e:
            raise EpisodeEncodingException(
                str(e), candidate_id=candidate.candidate_id, cause=e
            ) from e
