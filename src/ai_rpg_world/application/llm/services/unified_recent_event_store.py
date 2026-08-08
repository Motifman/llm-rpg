"""観測と行動結果を記録時から同じ時系列に保持するストア。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    UnifiedRecentEventEntry,
    UnifiedRecentEventKind,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


@dataclass(frozen=True)
class CompletedTurnCompaction:
    """L1 から外れ、L4 へ渡す古いターン群。"""

    turn_count: int
    entries: tuple[UnifiedRecentEventEntry, ...]

    @property
    def observations(self) -> tuple[ObservationEntry, ...]:
        """ステップ4までは従来どおり観測だけを L4 入力へ渡す。"""
        return tuple(
            entry.payload for entry in self.entries if entry.kind == "observation"
        )


class UnifiedRecentEventStore:
    """1 player の観測・行動・未処理観測を一つの保管場所で管理する。"""

    def __init__(self) -> None:
        self._entries: dict[int, list[UnifiedRecentEventEntry]] = {}
        self._pending: dict[int, list[UnifiedRecentEventEntry]] = {}
        # 完了済みターンごとの entry 数。末尾より後ろが、前回の自分の
        # ターン完了後から現在までに届いた open bucket になる。空ターンも
        # 0 として残すため、entry の有無ではターン数を代用しない。
        self._completed_turn_sizes: dict[int, list[int]] = {}

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
        sizes = self._completed_turn_sizes.get(key, [])
        if sizes:
            removed_per_bucket = [0] * len(sizes)
            bucket_index = 0
            bucket_end = sizes[0]
            for index in sorted(remove):
                while bucket_index < len(sizes) and index >= bucket_end:
                    bucket_index += 1
                    if bucket_index < len(sizes):
                        bucket_end += sizes[bucket_index]
                if bucket_index < len(sizes):
                    removed_per_bucket[bucket_index] += 1
            self._completed_turn_sizes[key] = [
                size - removed_count
                for size, removed_count in zip(sizes, removed_per_bucket)
            ]
        self._entries[key] = [
            event for index, event in enumerate(entries) if index not in remove
        ]
        return removed

    def get_timeline(
        self, player_id: PlayerId
    ) -> list[UnifiedRecentEventEntry]:
        entries = list(self._entries.get(self._key(player_id), []))
        return sorted(entries, key=lambda entry: entry.occurred_at.timestamp())

    def get_active_timeline(
        self, player_id: PlayerId
    ) -> list[UnifiedRecentEventEntry]:
        """現在のターン窓に残る観測と行動を、件数で切らず時系列順に返す。"""
        return self.get_timeline(player_id)

    def close_turn(self, player_id: PlayerId) -> None:
        """open bucket を閉じる。保持数の政策は短期記憶実装が決める。"""
        key = self._key(player_id)
        entries = self._entries.setdefault(key, [])
        sizes = self._completed_turn_sizes.setdefault(key, [])
        open_size = len(entries) - sum(sizes)
        if open_size < 0:  # pragma: no cover - replace 系の契約違反への防御
            raise RuntimeError("completed turn sizes exceed stored entries")
        sizes.append(open_size)

    def compact_oldest_turns(
        self, player_id: PlayerId, turn_count: int
    ) -> CompletedTurnCompaction:
        """古い完了ターンを指定数だけ L1 から外す。"""
        if turn_count <= 0:
            raise ValueError("turn_count must be greater than 0")
        key = self._key(player_id)
        sizes = self._completed_turn_sizes.get(key, [])
        if turn_count > len(sizes):
            raise ValueError("turn_count exceeds completed turns")
        entries = self._entries.setdefault(key, [])
        compact_sizes = sizes[:turn_count]
        del sizes[:turn_count]
        compact_entry_count = sum(compact_sizes)
        compacted = tuple(entries[:compact_entry_count])
        del entries[:compact_entry_count]
        return CompletedTurnCompaction(
            turn_count=turn_count,
            entries=compacted,
        )

    def completed_turn_count(self, player_id: PlayerId) -> int:
        """現在 L1 に残る完了済みターン数を返す。"""
        return len(self._completed_turn_sizes.get(self._key(player_id), []))

    def completed_turn_sizes(self, player_id: PlayerId) -> tuple[int, ...]:
        """snapshot codec 用に完了済みターン境界を返す。"""
        return tuple(self._completed_turn_sizes.get(self._key(player_id), []))

    def replace_completed_turn_sizes(
        self, player_id: PlayerId, sizes: Iterable[int]
    ) -> None:
        """snapshot から完了済みターン境界を復元する。"""
        values = list(sizes)
        if any(not isinstance(size, int) or size < 0 for size in values):
            raise ValueError("completed turn sizes must be non-negative integers")
        if sum(values) > len(self._entries.get(self._key(player_id), [])):
            raise ValueError("completed turn sizes exceed stored entries")
        self._completed_turn_sizes[self._key(player_id)] = values

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
        key = self._key(player_id)
        self._entries[key] = list(entries)
        self._completed_turn_sizes[key] = []

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
        return set(self._entries) | set(self._pending) | set(self._completed_turn_sizes)
