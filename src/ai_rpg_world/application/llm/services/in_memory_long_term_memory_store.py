"""長期記憶ストアの in-memory 実装"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ai_rpg_world.application.llm.contracts.dtos import (
    LongTermFactEntry,
    MemoryLawEntry,
)
from ai_rpg_world.application.llm.contracts.interfaces import ILongTermMemoryStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _law_key(subject: str, relation: str, target: str) -> Tuple[str, str, str]:
    return (subject, relation, target)


class InMemoryLongTermMemoryStore(ILongTermMemoryStore):
    """事実・教訓と法則・共起を in-memory で保持する実装。"""

    def __init__(self) -> None:
        self._facts: Dict[int, List[LongTermFactEntry]] = {}
        self._laws: Dict[int, Dict[Tuple[str, str, str], MemoryLawEntry]] = {}
        self._fact_id_to_index: Dict[int, Dict[str, int]] = {}

    def _key(self, player_id: PlayerId) -> int:
        return player_id.value

    def add_fact(self, player_id: PlayerId, content: str) -> str:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(content, str):
            raise TypeError("content must be str")
        key = self._key(player_id)
        if key not in self._facts:
            self._facts[key] = []
            self._fact_id_to_index[key] = {}
        fact_id = str(uuid.uuid4())
        entry = LongTermFactEntry(
            id=fact_id,
            content=content,
            player_id=key,
            updated_at=datetime.now(),
        )
        idx = len(self._facts[key])
        self._facts[key].append(entry)
        self._fact_id_to_index[key][fact_id] = idx
        return fact_id

    def search_facts(
        self,
        player_id: PlayerId,
        keywords: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[LongTermFactEntry]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if keywords is not None and not isinstance(keywords, list):
            raise TypeError("keywords must be list or None")
        if limit < 0:
            raise ValueError("limit must be 0 or greater")
        key = self._key(player_id)
        entries = self._facts.get(key, [])
        if keywords:
            keywords_lower = [k.lower() for k in keywords]
            entries = [
                e
                for e in entries
                if any(k in e.content.lower() for k in keywords_lower)
            ]
        sorted_entries = sorted(
            entries, key=lambda e: e.updated_at, reverse=True
        )
        return sorted_entries[:limit]

    def upsert_law(
        self,
        player_id: PlayerId,
        subject: str,
        relation: str,
        target: str,
        delta_strength: float = 1.0,
    ) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(subject, str):
            raise TypeError("subject must be str")
        if not isinstance(relation, str):
            raise TypeError("relation must be str")
        if not isinstance(target, str):
            raise TypeError("target must be str")
        if not isinstance(delta_strength, (int, float)):
            raise TypeError("delta_strength must be int or float")
        key = self._key(player_id)
        if key not in self._laws:
            self._laws[key] = {}
        k = _law_key(subject, relation, target)
        if k in self._laws[key]:
            existing = self._laws[key][k]
            new_strength = existing.strength + delta_strength
            self._laws[key][k] = MemoryLawEntry(
                id=existing.id,
                subject=existing.subject,
                relation=existing.relation,
                target=existing.target,
                strength=max(0.0, new_strength),
                player_id=key,
            )
        else:
            law_id = str(uuid.uuid4())
            self._laws[key][k] = MemoryLawEntry(
                id=law_id,
                subject=subject,
                relation=relation,
                target=target,
                strength=max(0.0, float(delta_strength)),
                player_id=key,
            )

    def find_laws(
        self,
        player_id: PlayerId,
        subject: Optional[str] = None,
        action_name: Optional[str] = None,
        limit: int = 10,
    ) -> List[MemoryLawEntry]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if subject is not None and not isinstance(subject, str):
            raise TypeError("subject must be str or None")
        if action_name is not None and not isinstance(action_name, str):
            raise TypeError("action_name must be str or None")
        if limit < 0:
            raise ValueError("limit must be 0 or greater")
        key = self._key(player_id)
        laws_dict = self._laws.get(key, {})
        entries = list(laws_dict.values())
        if subject:
            entries = [e for e in entries if subject.lower() in e.subject.lower()]
        if action_name:
            an_lower = action_name.lower()
            entries = [
                e
                for e in entries
                if an_lower in e.relation.lower() or an_lower in e.subject.lower()
            ]
        sorted_entries = sorted(
            entries, key=lambda e: e.strength, reverse=True
        )
        return sorted_entries[:limit]
