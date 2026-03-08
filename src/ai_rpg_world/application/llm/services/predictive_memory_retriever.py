"""予測志向記憶検索のデフォルト実装

検索優先度（ランキング）: entity 一致 > location 一致 > actionable/notable 一致
> action 一致 > free text keyword
facts と laws は重複除去・件数制御を厳格にする。
"""
import re

from typing import Any, List, Optional

from ai_rpg_world.application.llm.contracts.dtos import MemoryRetrievalQueryDto
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


def _extract_keywords_from_summary(text: str) -> List[str]:
    """current_state_summary からキーワードを抽出（STOPWORDS 除去）"""
    tokens = re.findall(r"[A-Za-z0-9_一-龥ぁ-んァ-ヶー]{2,}", text)
    result: list[str] = []
    for token in tokens:
        if token in _STOPWORDS:
            continue
        if token not in result:
            result.append(token)
    return result[:10]


def build_memory_retrieval_query_from_state(
    current_state_dto: Any,
    tool_names: List[str],
    current_state_summary: Optional[str] = None,
) -> MemoryRetrievalQueryDto:
    """
    PlayerCurrentStateDto と tool_names から MemoryRetrievalQueryDto を組み立てる。
    current_state_formatter の表現変更が retriever の品質に影響しにくい形にする。
    """
    entity_ids: list[str] = []
    location_ids: list[str] = []
    notable_labels: list[str] = []
    actionable_labels: list[str] = []

    if current_state_dto.current_spot_name:
        location_ids.append(current_state_dto.current_spot_name)
    if current_state_dto.area_name:
        location_ids.append(current_state_dto.area_name)
    for name in current_state_dto.connected_spot_names or []:
        if name and name not in location_ids:
            location_ids.append(name)

    for obj in current_state_dto.visible_objects or []:
        dn = obj.display_name or getattr(obj, "display_name", None)
        if dn and isinstance(dn, str) and dn.strip():
            n = dn.strip()
            if n not in entity_ids:
                entity_ids.append(n)

    for obj in current_state_dto.notable_objects or []:
        dn = obj.display_name or getattr(obj, "display_name", None)
        if dn and isinstance(dn, str) and dn.strip():
            n = dn.strip()
            if n not in notable_labels:
                notable_labels.append(n)

    for obj in current_state_dto.actionable_objects or []:
        dn = obj.display_name or getattr(obj, "display_name", None)
        if dn and isinstance(dn, str) and dn.strip():
            n = dn.strip()
            if n not in actionable_labels:
                actionable_labels.append(n)

    free = (
        _extract_keywords_from_summary(current_state_summary)
        if current_state_summary
        else []
    )
    return MemoryRetrievalQueryDto(
        entity_ids=tuple(entity_ids[:15]),
        location_ids=tuple(location_ids[:10]),
        notable_labels=tuple(notable_labels[:10]),
        actionable_labels=tuple(actionable_labels[:10]),
        action_names=tuple(tool_names[:15]),
        free_text_keywords=tuple(free[:10]),
    )


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
        query_dto: Optional[MemoryRetrievalQueryDto] = None,
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
        if query_dto is not None and not isinstance(
            query_dto, MemoryRetrievalQueryDto
        ):
            raise TypeError("query_dto must be MemoryRetrievalQueryDto or None")

        if query_dto is not None:
            q = query_dto
        else:
            free_text = _extract_keywords_from_summary(current_state_summary)
            q = MemoryRetrievalQueryDto(
                entity_ids=(),
                location_ids=(),
                notable_labels=(),
                actionable_labels=(),
                action_names=tuple(candidate_action_names),
                free_text_keywords=tuple(free_text),
            )

        episodes = self._collect_episode_candidates_ranked(
            player_id, query=q, limit=episode_limit
        )
        for ep in episodes:
            self._episode_store.increment_recall_count(player_id, ep.id)

        all_keywords = list(
            q.entity_ids
            + q.location_ids
            + q.notable_labels
            + q.actionable_labels
            + q.free_text_keywords
        )
        keywords_for_facts = all_keywords[:10] if all_keywords else None

        facts = self._long_term_store.search_facts(
            player_id,
            keywords=keywords_for_facts,
            limit=fact_limit,
        )
        facts = self._dedupe_facts(facts)[:fact_limit]
        if not facts and keywords_for_facts:
            facts = self._long_term_store.search_facts(
                player_id,
                keywords=None,
                limit=fact_limit,
            )
            facts = self._dedupe_facts(facts)[:fact_limit]

        laws = self._collect_law_candidates_from_query(
            player_id, query=q, limit=law_limit
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

    def _collect_episode_candidates_ranked(
        self,
        player_id: PlayerId,
        *,
        query: MemoryRetrievalQueryDto,
        limit: int,
    ):
        """
        検索優先度: entity > location > actionable/notable > action > free_text
        同じエピソードが複数条件でヒットしても 1 件にまとめる。
        """
        seen_ids: set[str] = set()
        result: List = []

        def add_unique(entries):
            for e in entries:
                eid = getattr(e, "id", None)
                if isinstance(eid, str) and eid not in seen_ids:
                    seen_ids.add(eid)
                    result.append(e)

        # 1. entity 一致（最優先）
        if query.entity_ids:
            add_unique(
                self._episode_store.find_by_entities_and_actions(
                    player_id,
                    entity_ids=list(query.entity_ids),
                    action_names=None,
                    limit=limit * 2,
                )
            )
        # 2. location 一致
        if query.location_ids:
            add_unique(
                self._episode_store.find_by_entities_and_actions(
                    player_id,
                    entity_ids=list(query.location_ids),
                    action_names=None,
                    limit=limit * 2,
                )
            )
        # 3. actionable / notable 一致
        notable_actionable = list(query.actionable_labels) + list(
            query.notable_labels
        )
        if notable_actionable:
            add_unique(
                self._episode_store.find_by_entities_and_actions(
                    player_id,
                    entity_ids=notable_actionable,
                    action_names=None,
                    limit=limit * 2,
                )
            )
        # 4. action 一致
        if query.action_names:
            add_unique(
                self._episode_store.find_by_entities_and_actions(
                    player_id,
                    entity_ids=None,
                    action_names=list(query.action_names),
                    limit=limit * 2,
                )
            )
        # 5. free text keyword
        if query.free_text_keywords:
            add_unique(
                self._episode_store.find_by_entities_and_actions(
                    player_id,
                    entity_ids=list(query.free_text_keywords),
                    action_names=None,
                    limit=limit * 2,
                )
            )

        return result[:limit]

    def _collect_law_candidates_from_query(
        self,
        player_id: PlayerId,
        *,
        query: MemoryRetrievalQueryDto,
        limit: int,
    ):
        """法則候補を query から収集し、重複除去して limit 件返す。"""
        candidates = []
        for name in list(query.action_names)[:10]:
            candidates.extend(
                self._long_term_store.find_laws(
                    player_id, subject=None, action_name=name, limit=limit
                )
            )
        for kw in list(query.entity_ids) + list(query.location_ids):
            candidates.extend(
                self._long_term_store.find_laws(
                    player_id, subject=kw, action_name=None, limit=limit
                )
            )
        for kw in list(query.free_text_keywords)[:5]:
            candidates.extend(
                self._long_term_store.find_laws(
                    player_id, subject=kw, action_name=None, limit=limit
                )
            )
        return self._dedupe_by_id(candidates)[:limit]

    def _dedupe_facts(self, facts: List) -> List:
        """事実の重複除去（content の完全一致）"""
        seen: set[str] = set()
        deduped = []
        for f in facts:
            content = getattr(f, "content", "")
            if content and content not in seen:
                seen.add(content)
                deduped.append(f)
        return deduped

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
