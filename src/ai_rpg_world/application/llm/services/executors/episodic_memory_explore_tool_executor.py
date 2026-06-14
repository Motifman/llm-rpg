"""memory_explore_related メタツール（エピソード間リンクの辿り）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
)
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    effective_link_strength,
    other_episode_id,
)
from ai_rpg_world.domain.memory.episodic.repository.memory_link_repository import (
    MemoryLinkRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.application.llm.services.episodic_memory_link_application_service import (
    EpisodicMemoryLinkApplicationService,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_MEMORY_EXPLORE_RELATED


@dataclass
class EpisodicMemoryExploreToolExecutor:
    """リンクストアから隣接エピソードを列挙し、JSON メッセージを返す。"""

    episode_store: EpisodicEpisodeRepository
    link_store: MemoryLinkRepository
    link_service: EpisodicMemoryLinkApplicationService
    # Phase 3 Step 3c-3: legacy player_id 経路は撤去済。constructor 上は
    # Optional のまま (= 既存テスト互換) だが、tool 実行時に未注入 / Being
    # 未 provision なら ``INVALID_STATE`` で fail-fast する。tool は LLM-visible
    # なので「該当 0 件」と「内部状態未準備」を区別する必要がある (= semantic
    # search の 3b-3 と同じ判断、design_decisions.md #13 参照)。
    being_attachment_resolver: Optional[BeingAttachmentResolver] = None
    default_world_id: Optional[WorldId] = None

    def __post_init__(self) -> None:
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

    def _resolve_being_id(self, player_id: int) -> Optional[BeingId]:
        """Resolver+WorldId 揃いつつ Being が attach 済なら BeingId、
        いずれか欠ければ None (= legacy 経路へ fallback)。"""
        if self.being_attachment_resolver is None or self.default_world_id is None:
            return None
        return self.being_attachment_resolver.resolve_being_id(
            self.default_world_id, PlayerId(player_id)
        )

    def get_handlers(
        self,
    ) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        return {TOOL_NAME_MEMORY_EXPLORE_RELATED: self._run_explore_related}

    def _run_explore_related(
        self,
        player_id: int,
        arguments: Dict[str, Any],
    ) -> LlmCommandResultDto:
        eid = str(arguments.get("episode_id", "")).strip()
        raw_top = arguments.get("top_k", 5)
        try:
            top_k = int(raw_top)
        except (TypeError, ValueError):
            top_k = 5
        if top_k <= 0:
            top_k = 5
        if top_k > 64:
            top_k = 64
        if not eid:
            return LlmCommandResultDto(
                success=False,
                message="episode_id が空です。",
                error_code="INVALID_ARGUMENT",
            )
        now = datetime.now(timezone.utc)
        being_id = self._resolve_being_id(player_id)
        if being_id is None:
            return LlmCommandResultDto(
                success=False,
                message=(
                    "internal state not ready: being_attachment_resolver / "
                    "default_world_id / Being provision のいずれかが欠落 "
                    "(Phase 3 Step 3c-3)。"
                ),
                error_code="INVALID_STATE",
            )
        links = self.link_store.list_links_for_episode_by_being(
            being_id, eid, now=now, limit=256
        )
        ranked = sorted(
            links,
            key=lambda ln: effective_link_strength(ln, now),
            reverse=True,
        )
        rows: list[dict[str, Any]] = []
        touched: list[str] = [eid]
        for ln in ranked[:top_k]:
            other = other_episode_id(ln, eid)
            ep = self.episode_store.get(player_id, other)
            if ep is None:
                continue
            eff = effective_link_strength(ln, now)
            text = ep.recall_text or ep.what
            rows.append(
                {
                    "episode_id": other,
                    "link_type": ln.link_type.value,
                    "effective_strength": round(eff, 4),
                    "summary": text[:500],
                }
            )
            touched.append(other)
            self.link_service.strengthen_from_meta_exploration(
                player_id, eid, other, now=now
            )
        self.link_service.note_promotion_frontier_episodes(player_id, touched)
        payload = {"related_episodes": rows}
        return LlmCommandResultDto(
            success=True,
            message=json.dumps(payload, ensure_ascii=False),
        )
