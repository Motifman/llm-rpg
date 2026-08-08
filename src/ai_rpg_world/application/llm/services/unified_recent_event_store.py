"""観測と行動結果を記録時から同じ時系列に保持するストア。"""

from __future__ import annotations

from typing import Iterable

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    UnifiedRecentEventEntry,
    UnifiedRecentEventKind,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class UnifiedRecentEventStore:
    """1 player の観測・行動・未処理観測を一つの保管場所で管理する。"""

    def __init__(self) -> None:
        self._entries: dict[int, list[UnifiedRecentEventEntry]] = {}
        self._pending: dict[int, list[UnifiedRecentEventEntry]] = {}

    @staticmethod
    def _key(player_id: PlayerId) -> int:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        return player_id.value

    def append_observation(
        self,
        player_id: PlayerId,
        entry: ObservationEntry,
        *,
        max_entries: int | None = None,
    ) -> list[ObservationEntry]:
        if not isinstance(entry, ObservationEntry):
            raise TypeError("entry must be ObservationEntry")
        key = self._key(player_id)
        self._entries.setdefault(key, []).append(
            UnifiedRecentEventEntry.from_observation(entry)
        )
        return self._trim_kind(key, "observation", max_entries)

    def append_action_result(
        self,
        player_id: PlayerId,
        entry: ActionResultEntry,
        *,
        max_entries: int | None = None,
    ) -> list[ActionResultEntry]:
        if not isinstance(entry, ActionResultEntry):
            raise TypeError("entry must be ActionResultEntry")
        key = self._key(player_id)
        self._entries.setdefault(key, []).append(
            UnifiedRecentEventEntry.from_action_result(entry)
        )
        return self._trim_kind(key, "action_result", max_entries)

    def _trim_kind(
        self,
        key: int,
        kind: UnifiedRecentEventKind,
        max_entries: int | None,
    ) -> list:
        if max_entries is None:
            return []
        if max_entries <= 0:
            raise ValueError("max_entries must be greater than 0")
        entries = self._entries.get(key, [])
        indices = [index for index, event in enumerate(entries) if event.kind == kind]
        overflow_count = max(0, len(indices) - max_entries)
        if overflow_count == 0:
            return []
        remove = set(indices[:overflow_count])
        removed = [entries[index].payload for index in indices[:overflow_count]]
        self._entries[key] = [
            event for index, event in enumerate(entries) if index not in remove
        ]
        return removed

    def get_timeline(
        self, player_id: PlayerId
    ) -> list[UnifiedRecentEventEntry]:
        entries = list(self._entries.get(self._key(player_id), []))
        return sorted(entries, key=lambda entry: entry.occurred_at.timestamp())

    def get_recent_timeline(
        self,
        player_id: PlayerId,
        *,
        observation_limit: int,
        action_result_limit: int,
        newest_equal_observation_first: bool,
    ) -> list[UnifiedRecentEventEntry]:
        """従来の種類別件数と同時刻の順序を保った統一時系列を返す。"""
        observations = self.get_recent_observations(
            player_id,
            observation_limit,
            newest_equal_first=newest_equal_observation_first,
        )
        actions = self.get_recent_action_results(player_id, action_result_limit)
        selected = [
            UnifiedRecentEventEntry.from_observation(entry)
            for entry in observations
        ]
        selected.extend(
            UnifiedRecentEventEntry.from_action_result(entry) for entry in actions
        )
        selected.sort(key=lambda entry: entry.occurred_at.timestamp())
        return selected

    def observations_in_storage_order(
        self, player_id: PlayerId
    ) -> list[ObservationEntry]:
        return [
            event.payload
            for event in self._entries.get(self._key(player_id), [])
            if event.kind == "observation"
        ]

    def action_results_in_storage_order(
        self, player_id: PlayerId
    ) -> list[ActionResultEntry]:
        return [
            event.payload
            for event in self._entries.get(self._key(player_id), [])
            if event.kind == "action_result"
        ]

    def get_recent_observations(
        self,
        player_id: PlayerId,
        limit: int,
        *,
        newest_equal_first: bool = False,
    ) -> list[ObservationEntry]:
        return self._get_recent_kind(
            player_id,
            limit,
            "observation",
            newest_equal_first=newest_equal_first,
        )

    def get_recent_action_results(
        self, player_id: PlayerId, limit: int
    ) -> list[ActionResultEntry]:
        return self._get_recent_kind(
            player_id, limit, "action_result", newest_equal_first=False
        )

    def _get_recent_kind(
        self,
        player_id: PlayerId,
        limit: int,
        kind: UnifiedRecentEventKind,
        *,
        newest_equal_first: bool,
    ) -> list:
        if limit < 0:
            raise ValueError("limit must be 0 or greater")
        entries = [
            (index, event)
            for index, event in enumerate(
                self._entries.get(self._key(player_id), [])
            )
            if event.kind == kind
        ]
        entries.sort(
            key=lambda pair: (
                pair[1].occurred_at.timestamp(),
                pair[0] if newest_equal_first else -pair[0],
            ),
            reverse=True,
        )
        return [event.payload for _, event in entries[:limit]]

    def pop_oldest_observations(
        self, player_id: PlayerId, count: int
    ) -> list[ObservationEntry]:
        if count < 0:
            raise ValueError("count must be 0 or greater")
        key = self._key(player_id)
        entries = self._entries.get(key, [])
        observation_indices = [
            index for index, event in enumerate(entries) if event.kind == "observation"
        ][:count]
        remove = set(observation_indices)
        removed = [entries[index].payload for index in observation_indices]
        self._entries[key] = [
            event for index, event in enumerate(entries) if index not in remove
        ]
        return removed

    def count_observations(self, player_id: PlayerId) -> int:
        return sum(
            event.kind == "observation"
            for event in self._entries.get(self._key(player_id), [])
        )

    def append_pending_observation(
        self, player_id: PlayerId, entry: ObservationEntry
    ) -> None:
        if not isinstance(entry, ObservationEntry):
            raise TypeError("entry must be ObservationEntry")
        key = self._key(player_id)
        self._pending.setdefault(key, []).append(
            UnifiedRecentEventEntry.from_observation(entry)
        )

    def get_pending_observations(
        self, player_id: PlayerId
    ) -> list[ObservationEntry]:
        return [
            event.payload for event in self._pending.get(self._key(player_id), [])
        ]

    def drain_pending_observations(
        self, player_id: PlayerId
    ) -> list[ObservationEntry]:
        key = self._key(player_id)
        entries = self._pending.get(key, [])
        self._pending[key] = []
        return [event.payload for event in entries]

    def replace_timeline(
        self, player_id: PlayerId, entries: Iterable[UnifiedRecentEventEntry]
    ) -> None:
        self._entries[self._key(player_id)] = list(entries)

    def replace_observations(
        self, player_id: PlayerId, entries: Iterable[ObservationEntry]
    ) -> None:
        key = self._key(player_id)
        retained = [
            event
            for event in self._entries.get(key, [])
            if event.kind != "observation"
        ]
        retained.extend(
            UnifiedRecentEventEntry.from_observation(entry) for entry in entries
        )
        self._entries[key] = retained

    def replace_action_results(
        self, player_id: PlayerId, entries: Iterable[ActionResultEntry]
    ) -> None:
        key = self._key(player_id)
        retained = [
            event
            for event in self._entries.get(key, [])
            if event.kind != "action_result"
        ]
        retained.extend(
            UnifiedRecentEventEntry.from_action_result(entry) for entry in entries
        )
        self._entries[key] = retained

    def replace_pending_observations(
        self, player_id: PlayerId, entries: Iterable[ObservationEntry]
    ) -> None:
        self._pending[self._key(player_id)] = [
            UnifiedRecentEventEntry.from_observation(entry) for entry in entries
        ]

    def player_ids(self) -> set[int]:
        return set(self._entries) | set(self._pending)
