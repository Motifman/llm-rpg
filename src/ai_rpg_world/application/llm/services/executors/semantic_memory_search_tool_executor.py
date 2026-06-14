"""memory_search_semantic メタツール (Phase 1d / semantic 能動検索)。

LLM が「タカシについて知っていること全部欲しい」のように query を渡して
semantic_store を能動的に検索する。passive top-K (Phase 1c) と直交する
経路で、状況連想で出てこない遠い記憶を狙って引きにいける。

設計指針:

- **scale する**: 結果は最大 ``top_k`` 件 (既定 5、最大 32)。store が大量に
  あっても LLM の context は太らない
- **scoring は cheap lexical**: tag 完全一致 + 本文/tag への部分一致を見て
  ヒット数で並べる。embedding 化は将来余地として残す (interface は不変)
- **副作用なし**: 世界状態は変えない。結果は ``LlmCommandResultDto.message``
  に JSON で返し、次ターンの ``recent_events_text`` に観測として現れる
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import SemanticMemoryEntry
from ai_rpg_world.domain.memory.semantic.repository.semantic_memory_repository import (
    SemanticMemoryRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_MEMORY_SEARCH_SEMANTIC


DEFAULT_TOP_K = 5
MAX_TOP_K = 32
SUMMARY_CHARS = 200


@dataclass
class SemanticMemorySearchToolExecutor:
    """``memory_search_semantic`` の実装。

    query を semantic_store の各 entry の tags / text と突き合わせ、ヒット数で
    並べた上位 K 件を JSON 返却する。query が空でも空配列 (= 該当なし) を
    success=True で返す (LLM 側に「何もない」と伝える)。
    """

    semantic_store: SemanticMemoryRepository
    # Phase 3 Step 3b-3: Resolver+WorldId は constructor 上は Optional のまま
    # (= 既存テスト互換) だが、tool 実行時に未注入 / Being 未 provision なら
    # error_code=INVALID_STATE で fail-fast する。tool は LLM-visible なので
    # 黙って空結果を返すと「該当なし」と区別がつかない。
    being_attachment_resolver: Optional[BeingAttachmentResolver] = None
    default_world_id: Optional[WorldId] = None

    def __post_init__(self) -> None:
        """Phase 3 Step 3b-2: 他 caller と型ガードを揃える。"""
        if self.being_attachment_resolver is not None and not isinstance(
            self.being_attachment_resolver, BeingAttachmentResolver
        ):
            raise TypeError(
                "being_attachment_resolver must be BeingAttachmentResolver"
            )
        if self.default_world_id is not None and not isinstance(
            self.default_world_id, WorldId
        ):
            raise TypeError("default_world_id must be WorldId")

    def _require_being_id(self, player_id: int):  # type: ignore[no-untyped-def]
        """Resolver+WorldId+Being が揃わなければ RuntimeError を投げる。

        Phase 3 Step 3b-3: legacy player_id 経路は撤去済。tool 実行時に Being
        が解決できないのは wiring の bug なので、握り潰さず明示的に失敗させる。
        """
        if self.being_attachment_resolver is None or self.default_world_id is None:
            raise RuntimeError(
                "SemanticMemorySearchToolExecutor requires being_attachment_resolver "
                "and default_world_id (Phase 3 Step 3b-3)."
            )
        being_id = self.being_attachment_resolver.resolve_being_id(
            self.default_world_id, PlayerId(player_id)
        )
        if being_id is None:
            raise RuntimeError(
                f"Being not provisioned for player_id={player_id} in world="
                f"{self.default_world_id.value} (Phase 3 Step 3b-3)."
            )
        return being_id

    def _list_entries(self, player_id: int) -> List[SemanticMemoryEntry]:
        """being_id 経路で entry 一覧を返す。"""
        being_id = self._require_being_id(player_id)
        return list(self.semantic_store.list_for_being(being_id))

    def get_handlers(
        self,
    ) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        return {TOOL_NAME_MEMORY_SEARCH_SEMANTIC: self._run_search_semantic}

    def _run_search_semantic(
        self,
        player_id: int,
        arguments: Dict[str, Any],
    ) -> LlmCommandResultDto:
        query = str(arguments.get("query", "")).strip()
        raw_top = arguments.get("top_k", DEFAULT_TOP_K)
        try:
            top_k = int(raw_top)
        except (TypeError, ValueError):
            top_k = DEFAULT_TOP_K
        if top_k <= 0:
            top_k = DEFAULT_TOP_K
        if top_k > MAX_TOP_K:
            top_k = MAX_TOP_K

        if not query:
            return LlmCommandResultDto(
                success=False,
                message="query が空です。検索したい単語や名前を指定してください。",
                error_code="INVALID_ARGUMENT",
            )

        try:
            entries = self._list_entries(player_id)
        except RuntimeError as exc:
            # Phase 3 Step 3b-3: Resolver/WorldId/Being が未設定なら wiring の
            # bug。LLM 側には「内部状態が未準備」と分かる形で返す。
            return LlmCommandResultDto(
                success=False,
                message=str(exc),
                error_code="INVALID_STATE",
            )
        ranked = _rank_entries(entries, query=query)
        top = ranked[:top_k]

        rows: list[dict[str, Any]] = [
            {
                "entry_id": cand.entry.entry_id,
                "summary": (cand.entry.text or "")[:SUMMARY_CHARS],
                "tags": list(cand.entry.tags),
                "importance_score": cand.entry.importance_score,
                "match_score": cand.match_score,
            }
            for cand in top
        ]
        payload = {"query": query, "matched_entries": rows}
        return LlmCommandResultDto(
            success=True,
            message=json.dumps(payload, ensure_ascii=False),
        )


@dataclass(frozen=True)
class _Ranked:
    entry: SemanticMemoryEntry
    match_score: int


def _rank_entries(
    entries: List[SemanticMemoryEntry],
    *,
    query: str,
) -> list[_Ranked]:
    """query のヒット数 + importance + 新しさ で降順ソート。

    match_score の構成:
    - tag に完全一致 → +3
    - tag に部分一致 → +1
    - text に部分一致 → +1
    - 文字列比較は case-insensitive (英語混在に対応)
    """
    q_lower = query.lower()
    scored: list[_Ranked] = []
    for entry in entries:
        score = _score_entry(entry, query=query, q_lower=q_lower)
        if score > 0:
            scored.append(_Ranked(entry=entry, match_score=score))
    # tie-breaker: importance_score 高い順 → created_at 新しい順
    scored.sort(
        key=lambda r: (
            r.match_score,
            r.entry.importance_score,
            r.entry.created_at,
        ),
        reverse=True,
    )
    return scored


def _score_entry(
    entry: SemanticMemoryEntry,
    *,
    query: str,
    q_lower: str,
) -> int:
    score = 0
    for tag in entry.tags:
        tag_lower = tag.lower()
        if tag_lower == q_lower:
            score += 3
        elif q_lower in tag_lower:
            score += 1
    if q_lower in entry.text.lower():
        score += 1
    return score


__all__ = ["SemanticMemorySearchToolExecutor"]
