"""予測志向記憶検索のデフォルト実装"""

from typing import List

from ai_rpg_world.application.llm.contracts.interfaces import (
    IEpisodeMemoryStore,
    ILongTermMemoryStore,
    IPredictiveMemoryRetriever,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


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

        episodes = self._episode_store.find_by_entities_and_actions(
            player_id,
            entity_ids=None,
            action_names=candidate_action_names if candidate_action_names else None,
            limit=episode_limit,
        )
        for ep in episodes:
            self._episode_store.increment_recall_count(player_id, ep.id)

        facts = self._long_term_store.search_facts(
            player_id, keywords=None, limit=fact_limit
        )
        laws = []
        for name in (candidate_action_names or [])[:10]:
            laws.extend(
                self._long_term_store.find_laws(
                    player_id, subject=None, action_name=name, limit=law_limit
                )
            )
        laws = laws[:law_limit]

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
