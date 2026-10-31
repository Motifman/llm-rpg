"""プレイヤーごとに、未処理の観測と直近の行動の結果を持つストア。

足した観測と行動の結果は、足すたびに聞き手へ知らせる。プロンプトの【直近の出来事】は Being の短期記憶から作るので、
ここは出来事の並びを持たない (design_decisions D1824-24)。
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from typing import Final

from ai_rpg_world.application.llm.contracts.chunk_encoding import UnifiedRecentEventEntry
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

AppendListener = Callable[[PlayerId, UnifiedRecentEventEntry], None]

#: 持っておく直近の行動の結果の件数。読むのは Phase A の起動判定 (直近 2 件) だけだが、起きた時刻の順と足した順が
#: ずれても新しい 2 件を取りこぼさないよう、今の短期記憶が持っていた範囲 (最大 20 ターン分) と同じだけ残す。
RECENT_ACTION_RESULTS_KEPT: Final = 20


class UnifiedRecentEventStore:
    def __init__(self) -> None:
        self._action_results: dict[int, deque[ActionResultEntry]] = {}
        self._pending: dict[int, list[ObservationEntry]] = {}
        self._append_listeners: list[AppendListener] = []

    def add_append_listener(self, listener: AppendListener) -> None:
        """足した観測と行動の結果を、足すたびに知らせる。

        Being 側の短期記憶へ書くための聞き手 (design_decisions D1824-7)。未処理の観測の預かりと、snapshot から戻す
        置き換えは知らせない。
        """
        if not callable(listener):
            raise TypeError("listener must be callable")
        self._append_listeners.append(listener)

    def remove_append_listener(self, listener: AppendListener) -> None:
        self._append_listeners.remove(listener)

    def _announce(self, player_id: PlayerId, entry: UnifiedRecentEventEntry) -> None:
        for listener in self._append_listeners:
            listener(player_id, entry)

    @staticmethod
    def _key(player_id: PlayerId) -> int:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        return player_id.value

    def append_observation(self, player_id: PlayerId, entry: ObservationEntry) -> None:
        """観測は持たず、聞き手に知らせるだけ。"""
        if not isinstance(entry, ObservationEntry):
            raise TypeError("entry must be ObservationEntry")
        self._key(player_id)
        self._announce(player_id, UnifiedRecentEventEntry.from_observation(entry))

    def append_action_result(self, player_id: PlayerId, entry: ActionResultEntry) -> None:
        if not isinstance(entry, ActionResultEntry):
            raise TypeError("entry must be ActionResultEntry")
        self._results_of(self._key(player_id)).append(entry)
        self._announce(player_id, UnifiedRecentEventEntry.from_action_result(entry))

    def _results_of(self, key: int) -> deque[ActionResultEntry]:
        return self._action_results.setdefault(key, deque(maxlen=RECENT_ACTION_RESULTS_KEPT))

    def get_recent_action_results(self, player_id: PlayerId, limit: int) -> list[ActionResultEntry]:
        """起きた時刻の新しい順に ``limit`` 件まで。同じ時刻なら、先に足したものが先 (並びを持っていたころと同じ)。"""
        if limit < 0:
            raise ValueError("limit must be 0 or greater")
        entries = list(enumerate(self._action_results.get(self._key(player_id), ())))
        entries.sort(key=lambda pair: (pair[1].occurred_at.timestamp(), -pair[0]), reverse=True)
        return [entry for _, entry in entries[:limit]]

    def action_results_in_storage_order(self, player_id: PlayerId) -> list[ActionResultEntry]:
        return list(self._action_results.get(self._key(player_id), ()))

    def replace_action_results(self, player_id: PlayerId, entries: Iterable[ActionResultEntry]) -> None:
        key = self._key(player_id)
        self._action_results[key] = deque(entries, maxlen=RECENT_ACTION_RESULTS_KEPT)

    def append_pending_observation(self, player_id: PlayerId, entry: ObservationEntry) -> None:
        if not isinstance(entry, ObservationEntry):
            raise TypeError("entry must be ObservationEntry")
        self._pending.setdefault(self._key(player_id), []).append(entry)

    def get_pending_observations(self, player_id: PlayerId) -> list[ObservationEntry]:
        return list(self._pending.get(self._key(player_id), []))

    def drain_pending_observations(self, player_id: PlayerId) -> list[ObservationEntry]:
        key = self._key(player_id)
        entries = self._pending.get(key, [])
        self._pending[key] = []
        return entries

    def replace_pending_observations(self, player_id: PlayerId, entries: Iterable[ObservationEntry]) -> None:
        self._pending[self._key(player_id)] = list(entries)

    def player_ids(self) -> set[int]:
        return {key for key, results in self._action_results.items() if results} | {
            key for key, pending in self._pending.items() if pending
        }


__all__ = ["RECENT_ACTION_RESULTS_KEPT", "AppendListener", "UnifiedRecentEventStore"]
