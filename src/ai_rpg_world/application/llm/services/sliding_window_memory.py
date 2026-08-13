"""スライディングウィンドウ記憶のデフォルト実装（in-memory）"""

from datetime import datetime
import logging
from typing import Any, Callable, List, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.llm.contracts.interfaces import IShortTermMemory
from ai_rpg_world.application.llm.services.unified_recent_event_store import (
    UnifiedRecentEventStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind


_logger = logging.getLogger(__name__)


class DefaultSlidingWindowMemory(IShortTermMemory):
    """プレイヤーごとに観測をリストで保持し、直近 N 件を返す in-memory 実装。"""

    def __init__(
        self,
        max_entries_per_player: int = 100,
        *,
        event_store: UnifiedRecentEventStore | None = None,
        turn_cap: int = 20,
        compact_turn_count: int = 10,
        trace_recorder_provider: Optional[Callable[[], Any]] = None,
        current_tick_provider: Optional[Callable[[], Optional[int]]] = None,
    ) -> None:
        if max_entries_per_player <= 0:
            raise ValueError("max_entries_per_player must be greater than 0")
        self._max_entries = max_entries_per_player
        self._event_store = event_store or UnifiedRecentEventStore()
        self._turn_cap = turn_cap
        self._compact_turn_count = compact_turn_count
        self._trace_recorder_provider = trace_recorder_provider or NullTraceRecorder
        self._current_tick_provider = current_tick_provider
        if turn_cap <= 0 or compact_turn_count <= 0 or compact_turn_count >= turn_cap:
            raise ValueError("turn window requires 0 < compact_turn_count < turn_cap")

    def _key(self, player_id: PlayerId) -> int:
        return player_id.value

    @property
    def recent_equal_timestamp_newest_first(self) -> bool:
        """同時刻の観測は従来どおり append 順を保つ。"""
        return False

    def append(self, player_id: PlayerId, entry: ObservationEntry) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(entry, ObservationEntry):
            raise TypeError("entry must be ObservationEntry")
        self._event_store.append_observation(
            player_id, entry, max_entries=self._max_entries
        )

    def append_all(
        self, player_id: PlayerId, entries: List[ObservationEntry]
    ) -> List[ObservationEntry]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(entries, list):
            raise TypeError("entries must be list")
        for e in entries:
            if not isinstance(e, ObservationEntry):
                raise TypeError("entries must contain only ObservationEntry")
        overflow: List[ObservationEntry] = []
        for entry in entries:
            overflow.extend(
                self._event_store.append_observation(
                    player_id, entry, max_entries=self._max_entries
                )
            )
        return overflow

    def get_recent(self, player_id: PlayerId, limit: int) -> List[ObservationEntry]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if limit < 0:
            raise ValueError("limit must be 0 or greater")
        return self._event_store.get_recent_observations(player_id, limit)

    def complete_turn(self, player_id: PlayerId) -> None:
        """ターンを閉じ、cap 到達時は古い K ターンを破棄する。"""
        self._event_store.close_turn(player_id)
        if self._event_store.completed_turn_count(player_id) >= self._turn_cap:
            turns_before = self._event_store.completed_turn_count(player_id)
            entries_before = len(self._event_store.get_active_timeline(player_id))
            compaction = self._event_store.compact_oldest_turns(
                player_id, self._compact_turn_count
            )
            self._emit_compaction(
                player_id,
                completed_turn_count_before=turns_before,
                entry_count_before=entries_before,
                compacted_turn_count=compaction.turn_count,
            )

    def set_trace_recorder_provider(
        self, provider: Optional[Callable[[], Any]]
    ) -> None:
        """WorldRuntime が確定した recorder を後から共有する。"""
        self._trace_recorder_provider = provider or NullTraceRecorder

    def set_current_tick_provider(
        self, provider: Optional[Callable[[], Optional[int]]]
    ) -> None:
        """圧縮発火時の world tick を後から共有する。"""
        self._current_tick_provider = provider

    def _emit_compaction(
        self,
        player_id: PlayerId,
        *,
        completed_turn_count_before: int,
        entry_count_before: int,
        compacted_turn_count: int,
    ) -> None:
        try:
            tick = (
                self._current_tick_provider()
                if self._current_tick_provider is not None
                else None
            )
            self._trace_recorder_provider().record(
                TraceEventKind.SHORT_TERM_MEMORY_COMPACTED,
                tick=tick,
                player_id=int(player_id),
                completed_turn_count_before=completed_turn_count_before,
                completed_turn_count_after=self._event_store.completed_turn_count(
                    player_id
                ),
                entry_count_before=entry_count_before,
                entry_count_after=len(
                    self._event_store.get_active_timeline(player_id)
                ),
                compacted_turn_count=compacted_turn_count,
            )
        except Exception:
            _logger.exception("短期記憶の圧縮 trace を記録できませんでした")

    def get_oldest_entry_datetime(
        self, player_id: PlayerId
    ) -> Optional[datetime]:
        """PR5 (R1): 現在 window に乗っている最古 entry の ``occurred_at``。

        episodic recall の時間下限フィルタに使う。entry が無ければ None。
        sliding window は max_entries で打ち切られるので、最古 = 「直近 N 件
        の中の最古」を返す。"""
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        entries = self._event_store.get_recent_observations(
            player_id, self._max_entries
        )
        if not entries:
            return None
        # naive / aware が混在しても直接比較で TypeError にしない。
        # get_recent と同じく timestamp() を比較キーにする
        return min(entries, key=lambda e: e.occurred_at.timestamp()).occurred_at
