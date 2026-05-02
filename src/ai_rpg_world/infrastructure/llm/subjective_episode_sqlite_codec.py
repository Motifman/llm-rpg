"""v2 SubjectiveEpisode の SQLite 用 JSON シリアライズ。

レガシー `episode_memories`（IEpisodeMemoryStore）とは別系統の payload。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, Mapping

from ai_rpg_world.application.llm.contracts.dtos import (
    BeliefUpdateCandidateEntry,
    EpisodicCue,
    MemoryReflectionEpisodePatchDto,
    MemoryReflectionIdentityCandidateDto,
    MemoryReflectionJournalEntry,
    MemoryReflectionSemanticCandidateDto,
    RelationshipDeltaEntry,
    SubjectiveEpisode,
    SubjectiveFelt,
    SubjectivePredictionError,
)

_CODEC_VERSION = 1


def _isoify(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _isoify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_isoify(x) for x in obj]
    return obj


def _parse_datetimes(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            if k in ("created_at", "last_recalled_at") and isinstance(v, str):
                try:
                    out[k] = datetime.fromisoformat(v)
                except ValueError:
                    out[k] = _parse_datetimes(v)
            elif isinstance(v, dict):
                out[k] = _parse_datetimes(v)
            elif isinstance(v, list):
                out[k] = [_parse_datetimes(x) for x in v]
            else:
                out[k] = v
        return out
    if isinstance(obj, list):
        return [_parse_datetimes(x) for x in obj]
    return obj


def _belief(d: Mapping[str, Any]) -> BeliefUpdateCandidateEntry:
    return BeliefUpdateCandidateEntry(
        summary=d["summary"],
        confidence=d["confidence"],
        note=d.get("note", ""),
    )


def _relationship(d: Mapping[str, Any]) -> RelationshipDeltaEntry:
    return RelationshipDeltaEntry(
        target=d["target"],
        delta_summary=d["delta_summary"],
        confidence=d["confidence"],
    )


def _cue(d: Mapping[str, Any]) -> EpisodicCue:
    return EpisodicCue(
        axis=d["axis"],
        value=d["value"],
        source=d.get("source", "rule"),
    )


def _felt(d: Mapping[str, Any]) -> SubjectiveFelt:
    sec = d.get("secondary_emotions", [])
    if not isinstance(sec, (list, tuple)):
        sec = ()
    return SubjectiveFelt(
        primary_emotion=d["primary_emotion"],
        secondary_emotions=tuple(sec),
        emotion_note=d.get("emotion_note", ""),
    )


def _pred(d: Mapping[str, Any]) -> SubjectivePredictionError:
    return SubjectivePredictionError(
        level=d["level"],
        reason=d.get("reason", ""),
    )


def _patch(d: Mapping[str, Any]) -> MemoryReflectionEpisodePatchDto:
    return MemoryReflectionEpisodePatchDto(
        emphasized=d.get("emphasized", ""),
        faded=d.get("faded", ""),
        new_meaning=d.get("new_meaning", ""),
        emotional_tone_shift=d.get("emotional_tone_shift", ""),
    )


def _sem(d: Mapping[str, Any]) -> MemoryReflectionSemanticCandidateDto:
    return MemoryReflectionSemanticCandidateDto(
        summary=d["summary"],
        note=d.get("note", ""),
    )


def _ident(d: Mapping[str, Any]) -> MemoryReflectionIdentityCandidateDto:
    return MemoryReflectionIdentityCandidateDto(
        summary=d["summary"],
        note=d.get("note", ""),
    )


def _journal(d: Mapping[str, Any]) -> MemoryReflectionJournalEntry:
    return MemoryReflectionJournalEntry(
        entry_id=d["entry_id"],
        created_at=d["created_at"],
        correlation_id=d["correlation_id"],
        trigger=d["trigger"],
        recall_trigger=d.get("recall_trigger", ""),
        current_interpretation=d.get("current_interpretation", ""),
        effect_on_decision=d.get("effect_on_decision", ""),
        episode_patch=_patch(d["episode_patch"]),
        semantic_update_candidates=tuple(
            _sem(x) for x in d.get("semantic_update_candidates", [])
        ),
        identity_update_candidates=tuple(
            _ident(x) for x in d.get("identity_update_candidates", [])
        ),
        raw_payload_digest=d.get("raw_payload_digest", ""),
    )


def subjective_episode_from_payload_dict(d: Mapping[str, Any]) -> SubjectiveEpisode:
    d = dict(_parse_datetimes(dict(d)))
    return SubjectiveEpisode(
        episode_id=d["episode_id"],
        agent_id=int(d["agent_id"]),
        created_at=d["created_at"],
        started_at_tick=d.get("started_at_tick"),
        ended_at_tick=d.get("ended_at_tick"),
        source_trace_ids=tuple(d["source_trace_ids"]),
        observed=d["observed"],
        interpreted=d["interpreted"],
        felt=_felt(d["felt"]),
        intended=d["intended"],
        expected=d["expected"],
        prediction_error=_pred(d["prediction_error"]),
        belief_at_encoding=d.get("belief_at_encoding", ""),
        belief_update_candidates=tuple(
            _belief(x) for x in d.get("belief_update_candidates", [])
        ),
        relationship_deltas=tuple(
            _relationship(x) for x in d.get("relationship_deltas", [])
        ),
        cue_keys=tuple(d.get("cue_keys", [])),
        cues=tuple(_cue(x) for x in d.get("cues", [])),
        importance=d["importance"],
        salience_reasons=tuple(d.get("salience_reasons", [])),
        recall_count=int(d.get("recall_count", 0)),
        last_recalled_at=d.get("last_recalled_at"),
        reflections=tuple(d.get("reflections", [])),
        reconsolidation_history=tuple(d.get("reconsolidation_history", [])),
        memory_reflection_journal=tuple(
            _journal(x) for x in d.get("memory_reflection_journal", [])
        ),
        confidence=d.get("confidence", "medium"),
        candidate_id=d.get("candidate_id", ""),
    )


def subjective_episode_to_json(ep: SubjectiveEpisode) -> str:
    """フルエピソードを JSON 文字列へ（テーブル payload_json 用）。"""
    payload = {"_codec_version": _CODEC_VERSION, "episode": _isoify(asdict(ep))}
    return json.dumps(payload, ensure_ascii=False)


def subjective_episode_from_json(raw: str) -> SubjectiveEpisode:
    """payload_json から SubjectiveEpisode へ。"""
    outer = json.loads(raw)
    ver = outer.get("_codec_version")
    if ver is None:
        episode_dict = outer
    elif ver == _CODEC_VERSION:
        episode_dict = outer["episode"]
    else:
        raise ValueError(f"unsupported subjective episode codec version: {ver!r}")
    return subjective_episode_from_payload_dict(episode_dict)
