"""エピソード記憶ストアの in-memory 実装"""

from datetime import datetime
from typing import Dict, List, Optional

from ai_rpg_world.application.llm.contracts.dtos import EpisodeMemoryEntry
from ai_rpg_world.application.llm.contracts.interfaces import IEpisodeMemoryStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class InMemoryEpisodeMemoryStore(IEpisodeMemoryStore):
    """プレイヤーごとにエピソードをリストで保持する in-memory 実装。"""

    def __init__(self) -> None:
        self._store: Dict[int, List[EpisodeMemoryEntry]] = {}
        self._id_to_index: Dict[int, Dict[str, int]] = {}  # player_id -> episode_id -> index

    def _key(self, player_id: PlayerId) -> int:
        return player_id.value

    def add(self, player_id: PlayerId, entry: EpisodeMemoryEntry) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(entry, EpisodeMemoryEntry):
            raise TypeError("entry must be EpisodeMemoryEntry")
        key = self._key(player_id)
        if key not in self._store:
            self._store[key] = []
            self._id_to_index[key] = {}
        idx = len(self._store[key])
        self._store[key].append(entry)
        self._id_to_index[key][entry.id] = idx

    def add_many(
        self, player_id: PlayerId, entries: List[EpisodeMemoryEntry]
    ) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(entries, list):
            raise TypeError("entries must be list")
        for e in entries:
            if not isinstance(e, EpisodeMemoryEntry):
                raise TypeError("entries must contain only EpisodeMemoryEntry")
        for entry in entries:
            self.add(player_id, entry)

    def get_recent(
        self,
        player_id: PlayerId,
        limit: int,
        since: Optional[datetime] = None,
    ) -> List[EpisodeMemoryEntry]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if limit < 0:
            raise ValueError("limit must be 0 or greater")
        if since is not None and not isinstance(since, datetime):
            raise TypeError("since must be datetime or None")
        key = self._key(player_id)
        entries = self._store.get(key, [])
        if since is not None:
            entries = [e for e in entries if e.timestamp >= since]
        sorted_entries = sorted(entries, key=lambda e: e.timestamp, reverse=True)
        return sorted_entries[:limit]

    def find_by_entities_and_actions(
        self,
        player_id: PlayerId,
        entity_ids: Optional[List[str]] = None,
        action_names: Optional[List[str]] = None,
        world_object_ids: Optional[List[int]] = None,
        spot_ids: Optional[List[int]] = None,
        scope_keys: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[EpisodeMemoryEntry]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if entity_ids is not None and not isinstance(entity_ids, list):
            raise TypeError("entity_ids must be list or None")
        if action_names is not None and not isinstance(action_names, list):
            raise TypeError("action_names must be list or None")
        if world_object_ids is not None and not isinstance(world_object_ids, list):
            raise TypeError("world_object_ids must be list or None")
        if spot_ids is not None and not isinstance(spot_ids, list):
            raise TypeError("spot_ids must be list or None")
        if scope_keys is not None and not isinstance(scope_keys, list):
            raise TypeError("scope_keys must be list or None")
        if limit < 0:
            raise ValueError("limit must be 0 or greater")
        key = self._key(player_id)
        entries = self._store.get(key, [])

        wo_set = set(world_object_ids) if world_object_ids else None
        sp_set = set(spot_ids) if spot_ids else None
        scope_set = set(scope_keys) if scope_keys else None
        if wo_set or sp_set:
            entries = [
                e
                for e in entries
                if (wo_set and any(wo in wo_set for wo in e.world_object_ids))
                or (sp_set and e.spot_id_value is not None and e.spot_id_value in sp_set)
            ]
        if scope_set:
            entries = [
                e
                for e in entries
                if any(sk in scope_set for sk in e.scope_keys)
            ]
        if entity_ids:
            entity_set = set(entity_ids)
            entries = [
                e
                for e in entries
                if any(ent in entity_set for ent in e.entity_ids)
                or (e.location_id is not None and e.location_id in entity_set)
            ]
        if action_names:
            action_set = set(a.lower() for a in action_names)
            entries = [
                e
                for e in entries
                if any(a in e.action_taken.lower() for a in action_set)
            ]
        sorted_entries = sorted(entries, key=lambda e: e.timestamp, reverse=True)
        return sorted_entries[:limit]

    def increment_recall_count(self, player_id: PlayerId, episode_id: str) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(episode_id, str):
            raise TypeError("episode_id must be str")
        key = self._key(player_id)
        if key not in self._store:
            return
        idx = self._id_to_index.get(key, {}).get(episode_id)
        if idx is None:
            return
        entry = self._store[key][idx]
        new_entry = EpisodeMemoryEntry(
            id=entry.id,
            context_summary=entry.context_summary,
            action_taken=entry.action_taken,
            outcome_summary=entry.outcome_summary,
            entity_ids=entry.entity_ids,
            location_id=entry.location_id,
            timestamp=entry.timestamp,
            importance=entry.importance,
            surprise=entry.surprise,
            recall_count=entry.recall_count + 1,
            world_object_ids=entry.world_object_ids,
            spot_id_value=entry.spot_id_value,
            scope_keys=entry.scope_keys,
        )
        self._store[key][idx] = new_entry

    def get_important_or_high_recall(
        self,
        player_id: PlayerId,
        since: datetime,
        min_importance: Optional[str] = None,
        min_recall_count: Optional[int] = None,
        limit: int = 20,
    ) -> List[EpisodeMemoryEntry]:
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
        if limit < 0:
            raise ValueError("limit must be 0 or greater")
        key = self._key(player_id)
        entries = self._store.get(key, [])
        entries = [e for e in entries if e.timestamp >= since]
        if min_importance:
            order = ("low", "medium", "high")
            if min_importance not in order:
                raise ValueError(
                    "min_importance must be 'low', 'medium', or 'high', "
                    f"got: {min_importance!r}"
                )
            min_idx = order.index(min_importance)
            entries = [
                e
                for e in entries
                if order.index(e.importance) >= min_idx
            ]
        if min_recall_count is not None:
            entries = [e for e in entries if e.recall_count >= min_recall_count]
        sorted_entries = sorted(
            entries,
            key=lambda e: (e.recall_count, e.timestamp),
            reverse=True,
        )
        return sorted_entries[:limit]
