"""メモリエントリを DSL で扱いやすい dict 形式に変換する"""

from typing import Any, Dict, List

from ai_rpg_world.application.llm.contracts.dtos import (
    EpisodeMemoryEntry,
    LongTermFactEntry,
    MemoryLawEntry,
)


def episode_to_dict(entry: EpisodeMemoryEntry) -> Dict[str, Any]:
    """EpisodeMemoryEntry を dict に変換する。"""
    return {
        "id": entry.id,
        "context_summary": entry.context_summary,
        "action_taken": entry.action_taken,
        "outcome_summary": entry.outcome_summary,
        "entity_ids": list(entry.entity_ids),
        "location_id": entry.location_id,
        "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
        "importance": entry.importance,
        "recall_count": entry.recall_count,
    }


def fact_to_dict(entry: LongTermFactEntry) -> Dict[str, Any]:
    """LongTermFactEntry を dict に変換する。"""
    return {
        "id": entry.id,
        "content": entry.content,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


def law_to_dict(entry: MemoryLawEntry) -> Dict[str, Any]:
    """MemoryLawEntry を dict に変換する。"""
    return {
        "id": entry.id,
        "subject": entry.subject,
        "relation": entry.relation,
        "target": entry.target,
        "strength": entry.strength,
    }


def episodes_to_dicts(entries: List[EpisodeMemoryEntry]) -> List[Dict[str, Any]]:
    """EpisodeMemoryEntry のリストを dict のリストに変換する。"""
    return [episode_to_dict(e) for e in entries]


def facts_to_dicts(entries: List[LongTermFactEntry]) -> List[Dict[str, Any]]:
    """LongTermFactEntry のリストを dict のリストに変換する。"""
    return [fact_to_dict(e) for e in entries]


def laws_to_dicts(entries: List[MemoryLawEntry]) -> List[Dict[str, Any]]:
    """MemoryLawEntry のリストを dict のリストに変換する。"""
    return [law_to_dict(e) for e in entries]
