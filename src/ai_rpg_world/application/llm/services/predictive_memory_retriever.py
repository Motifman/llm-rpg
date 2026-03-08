"""予測志向記憶検索のデフォルト実装"""
import re

from typing import List

from ai_rpg_world.application.llm.contracts.interfaces import (
    IEpisodeMemoryStore,
    ILongTermMemoryStore,
    IPredictiveMemoryRetriever,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_STOPWORDS = {
    "現在地",
    "エリア",
    "天気",
    "地形",
    "注意レベル",
    "視界距離",
    "注目対象",
    "今すぐ行動可能な対象",
    "利用可能な移動先",
    "行動状態",
    "理由",
    "可能",
    "距離",
    "方角",
    "なし",
    "clear",
    "grass",
}


class DefaultPredictiveMemoryRetriever(IPredictiveMemoryRetriever):
    """
    エピソードストアと長期記憶ストアをルールベースで検索し、
    「関連する記憶」用の 1 本のテキストを返す。ヒットしたエピソードの想起回数を更新する。
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

    def retrieve_for_prediction(
        self,
        player_id: PlayerId,
        current_state_summary: str,
        candidate_action_names: List[str],
        episode_limit: int = 5,
        fact_limit: int = 5,
        law_limit: int = 5,
    ) -> str:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(current_state_summary, str):
            raise TypeError("current_state_summary must be str")
        if not isinstance(candidate_action_names, list):
            raise TypeError("candidate_action_names must be list")
        if episode_limit < 0:
            raise ValueError("episode_limit must be 0 or greater")
        if fact_limit < 0:
            raise ValueError("fact_limit must be 0 or greater")
        if law_limit < 0:
            raise ValueError("law_limit must be 0 or greater")

        keywords = self._extract_keywords(current_state_summary)
        episodes = self._collect_episode_candidates(
            player_id,
            keywords=keywords,
            candidate_action_names=candidate_action_names,
            limit=episode_limit,
        )
        for ep in episodes:
            self._episode_store.increment_recall_count(player_id, ep.id)

        facts = self._long_term_store.search_facts(
            player_id,
            keywords=keywords or None,
            limit=fact_limit,
        )
        if not facts and keywords:
            facts = self._long_term_store.search_facts(
                player_id,
                keywords=None,
                limit=fact_limit,
            )
        laws = self._collect_law_candidates(
            player_id,
            keywords=keywords,
            candidate_action_names=candidate_action_names,
            limit=law_limit,
        )

        parts: List[str] = []
        if episodes:
            parts.append("【過去の体験】")
            for ep in episodes:
                parts.append(
                    f"- 状況: {ep.context_summary}; 行動: {ep.action_taken}; 結果: {ep.outcome_summary}"
                )
        if facts:
            parts.append("【覚えていること】")
            for f in facts:
                parts.append(f"- {f.content}")
        if laws:
            parts.append("【傾向・法則】")
            for law in laws:
                parts.append(
                    f"- {law.subject} を {law.relation} → {law.target} (強度: {law.strength:.0f})"
                )
        if not parts:
            return "（なし）"
        return "\n".join(parts)

    def _collect_episode_candidates(
        self,
        player_id: PlayerId,
        *,
        keywords: List[str],
        candidate_action_names: List[str],
        limit: int,
    ):
        candidates = []
        if keywords:
            candidates.extend(
                self._episode_store.find_by_entities_and_actions(
                    player_id,
                    entity_ids=keywords,
                    action_names=None,
                    limit=max(limit, 10),
                )
            )
        if candidate_action_names:
            candidates.extend(
                self._episode_store.find_by_entities_and_actions(
                    player_id,
                    entity_ids=None,
                    action_names=candidate_action_names,
                    limit=max(limit, 10),
                )
            )
        return self._dedupe_by_id(candidates)[:limit]

    def _collect_law_candidates(
        self,
        player_id: PlayerId,
        *,
        keywords: List[str],
        candidate_action_names: List[str],
        limit: int,
    ):
        candidates = []
        for name in candidate_action_names[:10]:
            candidates.extend(
                self._long_term_store.find_laws(
                    player_id, subject=None, action_name=name, limit=limit
                )
            )
        for keyword in keywords[:5]:
            candidates.extend(
                self._long_term_store.find_laws(
                    player_id, subject=keyword, action_name=None, limit=limit
                )
            )
        return self._dedupe_by_id(candidates)[:limit]

    def _extract_keywords(self, current_state_summary: str) -> List[str]:
        tokens = re.findall(r"[A-Za-z0-9_一-龥ぁ-んァ-ヶー]{2,}", current_state_summary)
        keywords: list[str] = []
        for token in tokens:
            if token in _STOPWORDS:
                continue
            if token not in keywords:
                keywords.append(token)
        return keywords[:10]

    def _dedupe_by_id(self, entries):
        seen_ids: set[str] = set()
        deduped = []
        for entry in entries:
            entry_id = getattr(entry, "id", None)
            if not isinstance(entry_id, str) or entry_id in seen_ids:
                continue
            seen_ids.add(entry_id)
            deduped.append(entry)
        return deduped
