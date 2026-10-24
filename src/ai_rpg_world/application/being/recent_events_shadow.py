"""今の【直近の出来事】と、Being の短期記憶から作った文を並べて比べる (#1824、design_decisions D1824-10)。

プロンプトは今の文のまま出す。違ったときだけ trace に残し、切り替えてよいかの材料にする。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder
from ai_rpg_world.being.application.recent_events_text import NO_RECENT_EVENTS, recent_events_text
from ai_rpg_world.being.domain.short_term_memory import ShortTermMemoryRepository
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_logger = logging.getLogger(__name__)

KIND_DIFFERENT = "different"
KIND_PUBLIC_SNS_PROJECTION = "public_sns_projection"
COMPARED_AS_WHOLE = "whole"
COMPARED_AS_SUBSEQUENCE = "subsequence"


def _lines(text: str) -> list[str]:
    """出来事ごとの塊。``- `` で始まる行に、続き行 (呼び出し、心の声) をまとめる。"""
    return [] if text == NO_RECENT_EVENTS else re.split(r"\n(?=- )", text)


def _first_different(current: list[str], being: list[str]) -> tuple[int | None, str | None]:
    """最初に違った行の位置と、その位置の Being の側の行。同じなら位置は None。"""
    for index in range(max(len(current), len(being))):
        current_line = current[index] if index < len(current) else None
        being_line = being[index] if index < len(being) else None
        if current_line != being_line:
            return index, being_line
    return None, None


def _first_missing(current: list[str], being: list[str]) -> tuple[int | None, str | None]:
    """今の文の行を、Being の文の中で前から順に探す。見つからなかった最初の行の位置。全部見つかれば None。"""
    position = 0
    for index, line in enumerate(current):
        try:
            position = being.index(line, position) + 1
        except ValueError:
            return index, None
    return None, None


class RecentEventsShadow:
    """``compare`` をプロンプトを組むたびに、``note_compacted`` を今の短期記憶が古いターンを畳むたびに、
    ``note_restored`` を Being の記憶を snapshot から戻したときに呼ぶ。
    """

    def __init__(
        self,
        *,
        store: ShortTermMemoryRepository,
        being_id_of: Callable[[PlayerId], BeingId | None],
        projection_active: Callable[[], bool],
        current_tick_provider: Callable[[], int | None],
        trace_recorder_provider: Callable[[], ITraceRecorder | None],
    ) -> None:
        self._store = store
        self._being_id_of = being_id_of
        self._projection_active = projection_active
        self._current_tick_provider = current_tick_provider
        self._trace_recorder_provider = trace_recorder_provider
        self._projection_reported: set[BeingId] = set()
        # 全体が同じかではなく、今の文の行が同じ順で含まれるかで比べる Being。
        self._compared_as_subsequence: set[BeingId] = set()

    def note_compacted(self, player_id: PlayerId) -> None:
        being_id = self._being_id_of(player_id)
        if being_id is not None:
            self._compared_as_subsequence.add(being_id)

    def note_restored(self, being_id: BeingId) -> None:
        """戻した Being の記憶は前の run から続くので、今の短期記憶と同じ範囲から始まらない。"""
        self._compared_as_subsequence.add(being_id)

    def compare(self, player_id: PlayerId, current_text: str) -> None:
        """例外は外へ投げない。比べられなくてもプロンプトは今の文で組める。"""
        try:
            self._compare(player_id, current_text)
        except Exception:
            _logger.exception("comparing the recent events with the Being's short-term memory failed")

    def _compare(self, player_id: PlayerId, current_text: str) -> None:
        being_id = self._being_id_of(player_id)
        if being_id is None:
            return
        if self._projection_active():
            # 公開 SNS の投影は観測の構造の情報で並べ替える。Being の側はその情報を持たないので比べない。
            if being_id not in self._projection_reported:
                self._projection_reported.add(being_id)
                self._record(player_id, being_id=being_id.value, mismatch_kind=KIND_PUBLIC_SNS_PROJECTION)
            return
        current = _lines(current_text)
        being = _lines(recent_events_text(self._store.get(being_id)))
        if being_id in self._compared_as_subsequence:
            # 今の短期記憶はターンの区切りで外すので、外したターンの行動の結果が消え、同じ行動が
            # 起こした次のターンの観測は残る。Being の側はまだ外さないので、今の文の行が同じ順で
            # Being の文に含まれるかを見る。
            compared_as, index, being_line = COMPARED_AS_SUBSEQUENCE, *_first_missing(current, being)
        else:
            compared_as, index, being_line = COMPARED_AS_WHOLE, *_first_different(current, being)
        if index is None:
            return
        self._record(
            player_id,
            being_id=being_id.value,
            mismatch_kind=KIND_DIFFERENT,
            compared_as=compared_as,
            line_index=index,
            current_line=current[index] if index < len(current) else None,
            being_line=being_line,
            current_line_count=len(current),
            being_line_count=len(being),
        )

    def _record(self, player_id: PlayerId, **payload: Any) -> None:
        recorder = self._trace_recorder_provider()
        if recorder is None:
            return
        recorder.record(
            TraceEventKind.RECENT_EVENTS_SHADOW_MISMATCH,
            tick=self._current_tick_provider(),
            player_id=int(player_id.value),
            **payload,
        )


__all__ = ["RecentEventsShadow"]
