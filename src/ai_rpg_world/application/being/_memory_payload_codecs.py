"""Being の memory store の VO ↔ JSON dict 変換ヘルパ。

Phase 4 Step 4-2b (Issue #470): ``BeingMemorySnapshotService`` が `BeingSnapshot`
の ``memory_payload_json`` に詰める JSON の **内部 schema を版管理する** ための
serializer 群。

各 ``_<vo>_to_dict`` / ``_dict_to_<vo>`` は 1:1 の VO ↔ dict 変換を提供する。
**Enum は ``.value``** で表現する (= JSON 標準型のみ)。
これにより snapshot JSON は他言語 / 外部ツールでも読みやすい。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.being.domain.acquaintance import Acquaintance, HowKnown
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex, IndexRevision
from ai_rpg_world.being.domain.memo_book import (
    Memo,
    MemoCertainty,
    MemoKind,
    MemoProvenance,
    MemoSource,
)
from ai_rpg_world.domain.common.exception import DomainException


def acquaintance_to_dict(acquaintance: Acquaintance) -> dict[str, Any]:
    return {
        "environment_name": acquaintance.environment_name,
        "name": acquaintance.name,
        "how_known": acquaintance.how_known.name,
        "known_since_turn": acquaintance.known_since_turn,
        "name_learned_turn": acquaintance.name_learned_turn,
        "relation_note": acquaintance.relation_note,
        "met_count": acquaintance.met_count,
        "first_met_turn": acquaintance.first_met_turn,
        "last_met_turn": acquaintance.last_met_turn,
    }


def dict_to_acquaintance(data: dict[str, Any]) -> Acquaintance:
    return Acquaintance(
        environment_name=data["environment_name"],
        name=data["name"],
        how_known=HowKnown[data["how_known"]],
        known_since_turn=data["known_since_turn"],
        name_learned_turn=data["name_learned_turn"],
        relation_note=data["relation_note"],
        met_count=data["met_count"],
        first_met_turn=data["first_met_turn"],
        last_met_turn=data["last_met_turn"],
    )


def _episode_index_to_dict(index: EpisodeIndex) -> dict[str, Any]:
    return {"summary": index.summary, "recall_when": index.recall_when}


def _dict_to_episode_index(data: dict[str, Any]) -> EpisodeIndex:
    return EpisodeIndex(summary=data["summary"], recall_when=data["recall_when"])


def being_episode_to_dict(episode: Episode) -> dict[str, Any]:
    return {
        "episode_id": episode.episode_id,
        "handle": episode.handle,
        "environment_name": episode.environment_name,
        "written_turn": episode.written_turn,
        "index": _episode_index_to_dict(episode.index),
        "body": episode.body,
        "recall_count": episode.recall_count,
        "last_recalled_turn": episode.last_recalled_turn,
        "index_history": [
            {
                "previous": _episode_index_to_dict(revision.previous),
                "revised_turn": revision.revised_turn,
            }
            for revision in episode.index_history
        ],
    }


def dict_to_being_episode(data: dict[str, Any]) -> Episode:
    """呼び名は ID から作り直さない。伸ばした呼び名が 6 文字に戻ると、前の呼び名が別の記録を指す。"""
    try:
        return Episode(
            episode_id=data["episode_id"],
            handle=data["handle"],
            environment_name=data["environment_name"],
            written_turn=data["written_turn"],
            index=_dict_to_episode_index(data["index"]),
            body=data["body"],
            recall_count=data["recall_count"],
            last_recalled_turn=data["last_recalled_turn"],
            index_history=tuple(
                IndexRevision(
                    previous=_dict_to_episode_index(revision["previous"]),
                    revised_turn=revision["revised_turn"],
                )
                for revision in data["index_history"]
            ),
        )
    except DomainException as exc:
        raise ValueError(f"invalid being episode payload: {exc}") from exc


def being_memo_to_dict(memo: Memo) -> dict[str, Any]:
    provenance = memo.provenance
    return {
        "memo_id": memo.memo_id,
        "handle": memo.handle,
        "kind": memo.kind.value,
        "text": memo.text,
        "provenance": None
        if provenance is None
        else {
            "source": provenance.source.value,
            "certainty": provenance.certainty.value,
            "source_from": provenance.source_from,
        },
        "written_turn": memo.written_turn,
        "edited_turn": memo.edited_turn,
        "environment_name": memo.environment_name,
    }


def dict_to_being_memo(data: dict[str, Any]) -> Memo:
    """呼び名は ID から作り直さない (エピソードと同じ理由)。"""
    try:
        provenance = data["provenance"]
        return Memo(
            memo_id=data["memo_id"],
            handle=data["handle"],
            kind=MemoKind(data["kind"]),
            text=data["text"],
            provenance=None
            if provenance is None
            else MemoProvenance(
                source=MemoSource(provenance["source"]),
                certainty=MemoCertainty(provenance["certainty"]),
                source_from=provenance["source_from"],
            ),
            written_turn=data["written_turn"],
            edited_turn=data["edited_turn"],
            environment_name=data["environment_name"],
        )
    except DomainException as exc:
        raise ValueError(f"invalid being memo payload: {exc}") from exc
