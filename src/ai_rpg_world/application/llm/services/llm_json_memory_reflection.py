"""Memory Reflection（§10）用: LLM JSON の schema・プロンプト・パース。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Tuple
from uuid import uuid4

from ai_rpg_world.application.llm.contracts.dtos import (
    EpisodeEncodingContextDto,
    MemoryReflectionEpisodePatchDto,
    MemoryReflectionIdentityCandidateDto,
    MemoryReflectionJournalEntry,
    MemoryReflectionSemanticCandidateDto,
    SubjectiveEpisode,
)
from ai_rpg_world.application.llm.exceptions import MemoryReflectionException

_MAX_TEXT_FIELD = 4000

_SYSTEM = """あなたは Memory Reflection（再解釈 / Reconsolidation）モジュールである。
与えられた「主観エピソード（初回 encoding の内容）」と「現在のエージェント文脈・状況メモ」を根に、
いまの視点からその記憶がどう意味を持つかを述べよ。元の observed / interpreted / source trace を改変してはならない。

返答は **有効な JSON オブジェクト 1 つだけ**（前後に説明文やマークダウンを付けない）。

【各フィールド】
- recall_trigger: なぜこの記憶がいま再考に値するか（短く）。
- current_interpretation: 今の文脈から見た意味づけ。
- effect_on_decision: 次の判断にどう影響しそうか。
- episode_patch: 流動的な意味の差分のみ（当時の事実は書き換えない）
  - emphasized: いま強調されそうな点
  - faded: いま薄れそうな点
  - new_meaning: 新しく付与されそうな意味
  - emotional_tone_shift: 感情のトーンの変化（短文）
- semantic_update_candidates: 長期に渡す**候補**のみ（Array of {summary, note}）。適用は別処理。
- identity_update_candidates: アイデンティティに関する**候補**のみ（Array of {summary, note}）。
"""


def memory_reflection_response_json_schema() -> Dict[str, Any]:
    cand_item = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "note": {"type": "string"},
        },
        "required": ["summary", "note"],
    }
    return {
        "type": "object",
        "properties": {
            "recall_trigger": {"type": "string"},
            "current_interpretation": {"type": "string"},
            "effect_on_decision": {"type": "string"},
            "episode_patch": {
                "type": "object",
                "properties": {
                    "emphasized": {"type": "string"},
                    "faded": {"type": "string"},
                    "new_meaning": {"type": "string"},
                    "emotional_tone_shift": {"type": "string"},
                },
                "required": [
                    "emphasized",
                    "faded",
                    "new_meaning",
                    "emotional_tone_shift",
                ],
            },
            "semantic_update_candidates": {"type": "array", "items": cand_item},
            "identity_update_candidates": {"type": "array", "items": cand_item},
        },
        "required": [
            "recall_trigger",
            "current_interpretation",
            "effect_on_decision",
            "episode_patch",
            "semantic_update_candidates",
            "identity_update_candidates",
        ],
    }


def memory_reflection_system_prompt() -> str:
    return _SYSTEM


def _clip(s: str, max_len: int = _MAX_TEXT_FIELD) -> str:
    s = s if isinstance(s, str) else ""
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def build_memory_reflection_user_prompt(
    episode: SubjectiveEpisode,
    context: EpisodeEncodingContextDto,
    *,
    situation_text: str,
) -> str:
    if not isinstance(episode, SubjectiveEpisode):
        raise TypeError("episode must be SubjectiveEpisode")
    if not isinstance(context, EpisodeEncodingContextDto):
        raise TypeError("context must be EpisodeEncodingContextDto")
    if not isinstance(situation_text, str):
        raise TypeError("situation_text must be str")
    ep_payload = {
        "episode_id": episode.episode_id,
        "observed": episode.observed[:6000],
        "interpreted": episode.interpreted[:6000],
        "intended": episode.intended[:2000],
        "expected": episode.expected[:2000],
        "felt": {
            "primary_emotion": episode.felt.primary_emotion,
            "secondary_emotions": list(episode.felt.secondary_emotions),
            "emotion_note": episode.felt.emotion_note,
        },
        "prediction_error": {
            "level": episode.prediction_error.level,
            "reason": episode.prediction_error.reason,
        },
        "importance": episode.importance,
        "cue_keys": list(episode.cue_keys),
        "source_trace_ids": list(episode.source_trace_ids),
    }
    ctx_payload = {
        "persona_summary": context.persona_summary[:4000],
        "current_goals": context.current_goals[:4000],
        "current_beliefs": context.current_beliefs[:8000],
        "identity_summary": context.identity_summary[:4000],
    }
    return json.dumps(
        {
            "subjective_episode": ep_payload,
            "current_agent_context": ctx_payload,
            "situation_text": situation_text[:8000],
        },
        ensure_ascii=False,
        indent=2,
    )


def _cand_list_sem(raw: Any) -> Tuple[MemoryReflectionSemanticCandidateDto, ...]:
    if raw in (None, []):
        return ()
    if not isinstance(raw, list):
        raise MemoryReflectionException("semantic_update_candidates must be list")
    out: List[MemoryReflectionSemanticCandidateDto] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        summary = str(item.get("summary") or "").strip()
        note = str(item.get("note") or "")
        if not summary and not note.strip():
            continue
        out.append(MemoryReflectionSemanticCandidateDto(summary=summary, note=note))
    return tuple(out)


def _cand_list_id(raw: Any) -> Tuple[MemoryReflectionIdentityCandidateDto, ...]:
    if raw in (None, []):
        return ()
    if not isinstance(raw, list):
        raise MemoryReflectionException("identity_update_candidates must be list")
    out: List[MemoryReflectionIdentityCandidateDto] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        summary = str(item.get("summary") or "").strip()
        note = str(item.get("note") or "")
        if not summary and not note.strip():
            continue
        out.append(MemoryReflectionIdentityCandidateDto(summary=summary, note=note))
    return tuple(out)


def journal_entry_from_llm_dict(
    data: Dict[str, Any],
    *,
    correlation_id: str,
    trigger: str,
    created_at: datetime,
    entry_id: str | None = None,
    raw_payload_digest: str = "",
) -> MemoryReflectionJournalEntry:
    if not isinstance(data, dict):
        raise MemoryReflectionException("LLM output must be object")

    def req_str(k: str) -> str:
        v = data.get(k)
        if v is None or not str(v).strip():
            raise MemoryReflectionException(f"missing or empty {k}")
        return _clip(str(v).strip())

    rt = req_str("recall_trigger")
    ci = req_str("current_interpretation")
    ed = req_str("effect_on_decision")

    patch_raw = data.get("episode_patch") or {}
    if not isinstance(patch_raw, dict):
        raise MemoryReflectionException("episode_patch must be object")
    patch = MemoryReflectionEpisodePatchDto(
        emphasized=_clip(str(patch_raw.get("emphasized") or "")),
        faded=_clip(str(patch_raw.get("faded") or "")),
        new_meaning=_clip(str(patch_raw.get("new_meaning") or "")),
        emotional_tone_shift=_clip(str(patch_raw.get("emotional_tone_shift") or "")),
    )

    sem = _cand_list_sem(data.get("semantic_update_candidates"))
    ident = _cand_list_id(data.get("identity_update_candidates"))

    eid = entry_id or f"refl-{uuid4().hex}"
    return MemoryReflectionJournalEntry(
        entry_id=eid,
        created_at=created_at,
        correlation_id=correlation_id,
        trigger=trigger,
        recall_trigger=rt,
        current_interpretation=ci,
        effect_on_decision=ed,
        episode_patch=patch,
        semantic_update_candidates=sem,
        identity_update_candidates=ident,
        raw_payload_digest=raw_payload_digest[:128],
    )


def parse_memory_reflection_llm_text(
    text: str,
    *,
    correlation_id: str,
    trigger: str,
    created_at: datetime,
) -> MemoryReflectionJournalEntry:
    if not isinstance(text, str):
        raise MemoryReflectionException("LLM text must be str")
    raw = text.strip()
    if not raw:
        raise MemoryReflectionException("empty LLM output")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise MemoryReflectionException(
            f"invalid JSON: {e}",
            correlation_id=correlation_id,
            cause=e,
        ) from e
    if not isinstance(data, dict):
        raise MemoryReflectionException("JSON root must be object")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return journal_entry_from_llm_dict(
        data,
        correlation_id=correlation_id,
        trigger=trigger,
        created_at=created_at,
        raw_payload_digest=digest,
    )
