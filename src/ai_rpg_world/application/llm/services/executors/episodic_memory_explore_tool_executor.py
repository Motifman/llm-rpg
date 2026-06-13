"""memory_explore_related メタツール（エピソード間リンクの辿り）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    IEpisodicEpisodeStore,
)
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    effective_link_strength,
    other_episode_id,
)
from ai_rpg_world.domain.memory.episodic.repository.memory_link_repository import (
    IMemoryLinkStore,
)
from ai_rpg_world.application.llm.services.episodic_memory_link_application_service import (
    EpisodicMemoryLinkApplicationService,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_MEMORY_EXPLORE_RELATED


@dataclass
class EpisodicMemoryExploreToolExecutor:
    """リンクストアから隣接エピソードを列挙し、JSON メッセージを返す。"""

    episode_store: IEpisodicEpisodeStore
    link_store: IMemoryLinkStore
    link_service: EpisodicMemoryLinkApplicationService

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
        links = self.link_store.list_links_for_episode(
            player_id, eid, now=now, limit=256
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
