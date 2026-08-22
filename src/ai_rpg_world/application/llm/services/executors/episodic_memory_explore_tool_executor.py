"""memory_explore_related メタツール（エピソード間リンクの辿り）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.afterglow_store import (
    IAfterglowStore,
    make_afterglow_handle,
    resolve_episode_id_prefix_from_handle,
)
from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
    IEpisodicRecallSlotStore,
)
from ai_rpg_world.application.being.acting_being import ActingBeing
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
    afterglow_store: Optional[IAfterglowStore] = None
    slot_store: Optional[IEpisodicRecallSlotStore] = None

    def get_handlers(
        self,
    ) -> Dict[str, Callable[[ActingBeing, Dict[str, Any]], LlmCommandResultDto]]:
        return {TOOL_NAME_MEMORY_EXPLORE_RELATED: self._run_explore_related}

    def _run_explore_related(
        self,
        acting: ActingBeing,
        arguments: Dict[str, Any],
    ) -> LlmCommandResultDto:
        handle_raw = arguments.get("handle")
        try:
            handle_prefix = resolve_episode_id_prefix_from_handle(handle_raw or "")
        except (TypeError, ValueError) as e:
            return LlmCommandResultDto(
                success=False,
                message=str(e),
                error_code="INVALID_ARGUMENT",
            )
        raw_top = arguments.get("top_k", 5)
        try:
            top_k = int(raw_top)
        except (TypeError, ValueError):
            top_k = 5
        if top_k <= 0:
            top_k = 5
        if top_k > 64:
            top_k = 64
        now = datetime.now(timezone.utc)
        being_id = acting.being_id
        if self.afterglow_store is None and self.slot_store is None:
            return LlmCommandResultDto(
                success=False,
                message=(
                    "EpisodicMemoryExploreToolExecutor requires afterglow_store "
                    "or slot_store to resolve prompt handles."
                ),
                error_code="INVALID_STATE",
            )
        eid = self._resolve_episode_id_from_handle(
            being_id,
            str(handle_raw),
            handle_prefix,
        )
        if eid is None:
            return LlmCommandResultDto(
                success=False,
                message=self._unknown_handle_message(being_id),
                error_code="INVALID_ARGUMENT",
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
            # Phase 3 Step 3e-2: episode_store も being_id 経路 (= being_id は
            # tool 入口で既に解決済、INVALID_STATE をクリアしている)。
            ep = self.episode_store.get_by_being(being_id, other)
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
                acting.being_id, eid, other, now=now
            )
        self.link_service.note_promotion_frontier_episodes(
            acting.being_id, touched
        )
        payload = {"related_episodes": rows}
        return LlmCommandResultDto(
            success=True,
            message=json.dumps(payload, ensure_ascii=False),
        )

    def _resolve_episode_id_from_handle(
        self,
        being_id: BeingId,
        handle: str,
        handle_prefix: str,
    ) -> Optional[str]:
        """prompt handle を episode_id に戻す。

        まず afterglow を見る。``memory_recall_by_handle`` は本文を読んだ後に
        afterglow から消し、recall slot に格上げするため、見つからなければ slot
        も見る。これで「見出しを見る → 本文を読む → 関連を辿る」という自然な順序が
        失敗しない。
        """
        if self.afterglow_store is not None:
            entry = self.afterglow_store.find_by_handle(being_id, handle)
            if entry is not None:
                return entry.episode_id
        if self.slot_store is None:
            return None
        candidates = [
            entry
            for entry in self.slot_store.get_slot(being_id)
            if entry.episode_id.startswith(handle_prefix)
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda entry: entry.entered_tick, reverse=True)
        return candidates[0].episode_id

    def _unknown_handle_message(self, being_id: BeingId) -> str:
        handles: list[str] = []
        seen: set[str] = set()

        def add_handle(episode_id: str) -> None:
            handle = make_afterglow_handle(episode_id)
            if handle in seen:
                return
            seen.add(handle)
            handles.append(handle)

        if self.afterglow_store is not None:
            for entry in self.afterglow_store.get_index(being_id):
                add_handle(entry.episode_id)
        if self.slot_store is not None:
            for entry in self.slot_store.get_slot(being_id):
                add_handle(entry.episode_id)
        if not handles:
            return (
                "指定された handle は見つかりません。"
                "現在使える記憶の見出し handle はありません。"
            )
        return (
            "指定された handle は見つかりません。"
            f"有効な handle: {' / '.join(handles)}"
        )
