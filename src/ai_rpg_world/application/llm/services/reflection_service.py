"""Reflection のデフォルト実装（ルールベース統合）"""

from datetime import datetime
from typing import Optional

from ai_rpg_world.application.llm.contracts.interfaces import (
    IEpisodeMemoryStore,
    ILongTermMemoryStore,
    IReflectionService,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class RuleBasedReflectionService(IReflectionService):
    """
    重要・高想起エピソードを取得し、教訓として事実を追加、
    行動→結果のパターンを法則として長期記憶に upsert する。
    LLM は使わずルールベースで要約する。
    """

    def __init__(
        self,
        episode_store: IEpisodeMemoryStore,
        long_term_store: ILongTermMemoryStore,
    ) -> None:
        if not isinstance(episode_store, IEpisodeMemoryStore):
            raise TypeError("episode_store must be IEpisodeMemoryStore")
        if not isinstance(long_term_store, ILongTermMemoryStore):
            raise TypeError("long_term_store must be ILongTermMemoryStore")
        self._episode_store = episode_store
        self._long_term_store = long_term_store

    def run(
        self,
        player_id: PlayerId,
        since: datetime,
        min_importance: Optional[str] = None,
        min_recall_count: Optional[int] = None,
        episode_limit: int = 20,
    ) -> Optional[datetime]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(since, datetime):
            raise TypeError("since must be datetime")
        if min_importance is not None and not isinstance(min_importance, str):
            raise TypeError("min_importance must be str or None")
        if min_recall_count is not None and not isinstance(
            min_recall_count, int
        ):
            raise TypeError("min_recall_count must be int or None")
        if episode_limit < 0:
            raise ValueError("episode_limit must be 0 or greater")

        episodes = self._episode_store.get_important_or_high_recall(
            player_id,
            since=since,
            min_importance=min_importance,
            min_recall_count=min_recall_count,
            limit=episode_limit,
        )
        max_ts: Optional[datetime] = None
        for ep in episodes:
            fact_content = (
                f"状況: {ep.context_summary}; "
                f"行動: {ep.action_taken}; 結果: {ep.outcome_summary}"
            )
            self._long_term_store.add_fact(player_id, fact_content)
            subject = ep.action_taken[:50] if len(ep.action_taken) > 50 else ep.action_taken
            self._long_term_store.upsert_law(
                player_id,
                subject=subject,
                relation="すると",
                target=ep.outcome_summary[:50] if len(ep.outcome_summary) > 50 else ep.outcome_summary,
                delta_strength=1.0,
            )
            if max_ts is None or ep.timestamp > max_ts:
                max_ts = ep.timestamp
        return max_ts
