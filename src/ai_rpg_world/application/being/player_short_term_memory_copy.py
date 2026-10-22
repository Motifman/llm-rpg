"""今の短期記憶に入った出来事を、契約の型に写して Being 側の短期記憶にも書く (#1824)。

今の短期記憶はそのまま動かし続ける。写せなかった出来事は trace に残し、run を止めない
(design_decisions D1824-7)。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

from ai_rpg_world.application.common.execution_provenance import current_execution_provenance
from ai_rpg_world.application.llm.contracts.chunk_encoding import UnifiedRecentEventEntry
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.observation.being_contract import (
    ObservationNotRepresentable,
    Observer,
    agent_move_from_tool_call,
    observation_from_action_result,
    observation_from_game,
    observation_from_unprompted_result,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder
from ai_rpg_world.being.contract import AgentMove, ContractViolation, Observation
from ai_rpg_world.being.domain.memory_turn_clock import MemoryTurnReader
from ai_rpg_world.being.domain.short_term_memory import (
    RememberedEvent,
    ShortTermMemoryRepository,
    turn_for_event,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
    ShortTermMemoryValidationException,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_logger = logging.getLogger(__name__)

REASON_NO_AGENT_MOVE = "no_agent_move"
REASON_MEMORY_RULE = "memory_rule"
REASON_CONTRACT_VIOLATION = "contract_violation"
REASON_UNEXPECTED_ERROR = "unexpected_error"


class _NoAgentMove(Exception):
    pass


class PlayerShortTermMemoryCopy:
    """``on_appended`` を今の保存先の追記の口に、``note_move`` を 1 手を受け取った直後に呼ぶ。"""

    def __init__(
        self,
        *,
        store: ShortTermMemoryRepository,
        being_id_of: Callable[[PlayerId], BeingId | None],
        turn_reader: MemoryTurnReader,
        observer_of: Callable[[PlayerId], Observer],
        current_tick_provider: Callable[[], int | None],
        trace_recorder_provider: Callable[[], ITraceRecorder | None],
    ) -> None:
        self._store = store
        self._being_id_of = being_id_of
        self._turn_reader = turn_reader
        self._observer_of = observer_of
        self._current_tick_provider = current_tick_provider
        self._trace_recorder_provider = trace_recorder_provider
        self._moves: dict[PlayerId, AgentMove] = {}

    def note_move(self, player_id: PlayerId, tool_name: str, arguments: Mapping[str, Any]) -> None:
        """実行中の要求の ID を ``call_id`` にして書き留める。結果と 1 手はこの ID で結ぶ。"""
        self._moves.pop(player_id, None)
        being_id: BeingId | None = None
        try:
            being_id = self._being_id_of(player_id)
            provenance = current_execution_provenance()
            if being_id is None or provenance is None:
                return
            self._moves[player_id] = agent_move_from_tool_call(
                tool_name, arguments, call_id=provenance.execution_request_id
            )
        except (ContractViolation, ValueError):
            self._not_copied(player_id, being_id, source="move", reason=REASON_CONTRACT_VIOLATION, event_kind=tool_name)
        except Exception as exc:
            self._unexpected(player_id, being_id, source="move", event_kind=tool_name, exc=exc)

    def on_appended(self, player_id: PlayerId, entry: UnifiedRecentEventEntry) -> None:
        source = entry.kind
        kind = _kind_of(entry.payload)
        being_id: BeingId | None = None
        try:
            being_id = self._being_id_of(player_id)
            if being_id is None:
                return
            observation, move = self._translate(player_id, entry.payload)
            turn = turn_for_event(observation.route, current_turn=self._turn_reader.current_turn(being_id))
            memory = self._store.get(being_id).remember(
                RememberedEvent(turn=turn, observation=observation, move=move)
            )
            self._store.save(being_id, memory)
        except ObservationNotRepresentable as exc:
            self._not_copied(player_id, being_id, source=source, reason=exc.reason.value, event_kind=exc.kind)
        except _NoAgentMove:
            self._not_copied(player_id, being_id, source=source, reason=REASON_NO_AGENT_MOVE, event_kind=kind)
        except ShortTermMemoryValidationException:
            self._not_copied(player_id, being_id, source=source, reason=REASON_MEMORY_RULE, event_kind=kind)
        except ContractViolation:
            self._not_copied(player_id, being_id, source=source, reason=REASON_CONTRACT_VIOLATION, event_kind=kind)
        except Exception as exc:
            self._unexpected(player_id, being_id, source=source, event_kind=kind, exc=exc)

    def _unexpected(
        self,
        player_id: PlayerId,
        being_id: BeingId | None,
        *,
        source: str,
        event_kind: str | None,
        exc: Exception,
    ) -> None:
        _logger.exception("copying a short-term memory event to the Being failed")
        self._not_copied(
            player_id,
            being_id,
            source=source,
            reason=REASON_UNEXPECTED_ERROR,
            event_kind=event_kind,
            error_type=type(exc).__name__,
        )

    def _translate(
        self, player_id: PlayerId, payload: ObservationEntry | ActionResultEntry
    ) -> tuple[Observation, AgentMove | None]:
        observer = self._observer_of(player_id)
        if isinstance(payload, ObservationEntry):
            return (
                observation_from_game(
                    payload.output,
                    # 観測は起きた tick を持たない。取り出した時点の tick で埋めると、時刻の
                    # 表示とずれるので、秒は分からないとする (design_decisions D1824-7)。
                    tick=None,
                    game_time_label=payload.game_time_label,
                    observer=observer,
                ),
                None,
            )
        provenance = payload.execution_provenance
        if provenance is None:
            return observation_from_unprompted_result(payload, observer=observer), None
        move = self._moves.get(player_id)
        if move is None or move.call_id != provenance.execution_request_id:
            # 記憶の道具の結果は、1 手が無いことより先に、Being の内側の記録として拒む。
            observation_from_action_result(payload, call_id=provenance.execution_request_id, observer=observer)
            raise _NoAgentMove
        return observation_from_action_result(payload, call_id=move.call_id, observer=observer), move

    def _not_copied(self, player_id: PlayerId, being_id: BeingId | None, **payload: Any) -> None:
        try:
            recorder = self._trace_recorder_provider()
            if recorder is None:
                return
            recorder.record(
                TraceEventKind.BEING_SHORT_TERM_MEMORY_NOT_COPIED,
                tick=self._current_tick_provider(),
                player_id=int(player_id.value),
                being_id=None if being_id is None else being_id.value,
                **payload,
            )
        except Exception:
            _logger.exception("trace recorder.record raised for BEING_SHORT_TERM_MEMORY_NOT_COPIED; skipping")


def _kind_of(payload: ObservationEntry | ActionResultEntry) -> str | None:
    if isinstance(payload, ObservationEntry):
        kind = payload.output.structured.get("type") or payload.output.structured.get("kind")
        return kind if isinstance(kind, str) else None
    return payload.tool_name


__all__ = ["PlayerShortTermMemoryCopy"]
