"""行動の記録から繰り返しを見つける検出器。

検出器は警告を出さない。見つけたら signal を返し、文面・観測・trace は
``loop_guard_warning.LoopWarningEmitter`` が受け持つ。検出器を足すときは
``ToolCallLoopGuardService`` の検出器の並びに加える。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Union

from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPEECH,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)

DEFAULT_LOOP_THRESHOLDS: dict[str, int] = {
    TOOL_NAME_SPOT_GRAPH_WAIT: 3,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO: 2,
    TOOL_NAME_SPOT_GRAPH_INTERACT: 4,
    # Issue #269 第17回 R2: target_label='' の whisper を 3 ティック連続で
    # 試行して失敗を繰り返した (remediation を読まない)。speech は引数が
    # 変われば (channel / 内容 / 相手) fingerprint が変わるので、同一引数 2
    # 連発は travel_to 同様に「同じ行動の繰り返し」と判定する。
    TOOL_NAME_SPEECH: 2,
}
"""tool ごとの連続回数しきい値 (この回数連続で同一なら警告)。"""

DEFAULT_OTHER_THRESHOLD: int = 5
"""閾値辞書に含まれない tool の default 連続回数。"""

DEFAULT_WINDOW_SIZE: int = 10
"""player ごとに保持する直近 tool call の最大件数。"""

DEFAULT_CROSS_TICK_FAILURE_WINDOW: int = 20
"""cross_tick_failure 検出の tick 幅。この tick 数以内の失敗を集約対象とする。"""

DEFAULT_CROSS_TICK_FAILURE_THRESHOLD: int = 3
"""cross_tick_failure 検出の閾値。window 内で同 (tool, fingerprint, error_code)
が本数以上出現したら警告を発火する。"""


@dataclass(frozen=True)
class RecordedAction:
    """検出器に渡す 1 回の行動記録。"""

    player_key: int
    tool_name: str
    fingerprint: str
    success: bool | None
    error_code: str | None
    tick: int | None
    result_summary: str | None = None


@dataclass(frozen=True)
class ConsecutiveRepeat:
    """同じ (tool, fingerprint) が閾値の倍数回だけ連続した。"""

    tool_name: str
    fingerprint: str
    consecutive: int
    tick: int | None


@dataclass(frozen=True)
class CrossTickFailureRepeat:
    """tick の窓の中で、同じ (tool, fingerprint, error_code) の失敗が閾値回に届いた。"""

    tool_name: str
    fingerprint: str
    error_code: str
    count: int
    window: int
    tick: int


@dataclass(frozen=True)
class SemanticRepeat:
    """直近 K 件の行動が、言い方を変えた同じ試みの繰り返しだと判断された (#1412)。

    ``tool_name`` と ``fingerprint`` は窓の最後の行動。
    """

    tool_name: str
    fingerprint: str
    count: int
    probability: float
    tick: int | None


RepeatSignal = Union[ConsecutiveRepeat, CrossTickFailureRepeat, SemanticRepeat]


class RepeatDetector(Protocol):
    def observe(self, action: RecordedAction) -> RepeatSignal | None: ...


@dataclass(frozen=True)
class _ToolCallRecord:
    tool_name: str
    fingerprint: str


@dataclass(frozen=True)
class _FailureRecord:
    tick: int
    tool_name: str
    fingerprint: str
    error_code: str


class ConsecutiveSameActionDetector:
    """同一 tool + 同一引数の連続を数える。

    閾値の倍数で発火し続ける (threshold=3 なら 3, 6, 9...)。LLM が警告を
    無視し続けても何度でも気付かせるため。
    """

    def __init__(
        self,
        *,
        thresholds: dict[str, int] | None = None,
        default_threshold: int = DEFAULT_OTHER_THRESHOLD,
        window_size: int = DEFAULT_WINDOW_SIZE,
    ) -> None:
        if thresholds is not None and not isinstance(thresholds, dict):
            raise TypeError("thresholds must be dict or None")
        if not isinstance(default_threshold, int) or default_threshold < 2:
            raise ValueError("default_threshold must be int >= 2")
        if not isinstance(window_size, int) or window_size < 2:
            raise ValueError("window_size must be int >= 2")
        self._thresholds: dict[str, int] = dict(thresholds) if thresholds else dict(
            DEFAULT_LOOP_THRESHOLDS
        )
        self._default_threshold = default_threshold
        self._window_size = window_size
        self._history: dict[int, list[_ToolCallRecord]] = {}
        self._streak: dict[int, tuple[_ToolCallRecord, int]] = {}

    def observe(self, action: RecordedAction) -> ConsecutiveRepeat | None:
        key = action.player_key
        record = _ToolCallRecord(
            tool_name=action.tool_name, fingerprint=action.fingerprint
        )
        history = self._history.setdefault(key, [])
        history.append(record)
        if len(history) > self._window_size:
            del history[: len(history) - self._window_size]

        threshold = self._thresholds.get(action.tool_name, self._default_threshold)
        prev = self._streak.get(key)
        if prev is None or prev[0] != record:
            streak_count = 1
        else:
            streak_count = prev[1] + 1
        self._streak[key] = (record, streak_count)

        if streak_count < threshold or streak_count % threshold != 0:
            return None
        return ConsecutiveRepeat(
            tool_name=action.tool_name,
            fingerprint=action.fingerprint,
            consecutive=streak_count,
            tick=action.tick,
        )

    def peek(self, player_key: int) -> tuple[str, int] | None:
        streak = self._streak.get(player_key)
        if streak is None:
            return None
        record, count = streak
        if count < 2:
            return None
        return (record.tool_name, count)


class CrossTickFailureDetector:
    """連続していない同一失敗の反復を、tick の窓で数える。

    間に別 tool が挟まっていても検出できる。窓の外の失敗は捨てるので、
    状況が変わって同じ失敗をしばらく出さなければ自然に数え直しになる。
    発火した組は窓の幅だけ再発火を抑える。
    """

    def __init__(
        self,
        *,
        window: int = DEFAULT_CROSS_TICK_FAILURE_WINDOW,
        threshold: int = DEFAULT_CROSS_TICK_FAILURE_THRESHOLD,
    ) -> None:
        if not isinstance(window, int) or window < 2:
            raise ValueError("cross_tick_failure_window must be int >= 2")
        if not isinstance(threshold, int) or threshold < 2:
            raise ValueError("cross_tick_failure_threshold must be int >= 2")
        self._window = window
        self._threshold = threshold
        self._failure_history: dict[int, list[_FailureRecord]] = {}
        self._last_warn: dict[int, dict[tuple[str, str, str], int]] = {}

    def observe(self, action: RecordedAction) -> CrossTickFailureRepeat | None:
        error_code = action.error_code
        if action.success is not False or not isinstance(error_code, str) or not error_code:
            return None
        current_tick = action.tick
        if current_tick is None:
            return None
        key = action.player_key
        history = self._failure_history.setdefault(key, [])
        history.append(
            _FailureRecord(
                tick=current_tick,
                tool_name=action.tool_name,
                fingerprint=action.fingerprint,
                error_code=error_code,
            )
        )
        window = self._window
        history[:] = [r for r in history if (current_tick - r.tick) < window]
        pattern = (action.tool_name, action.fingerprint, error_code)
        count = sum(
            1
            for r in history
            if (r.tool_name, r.fingerprint, r.error_code) == pattern
        )
        if count < self._threshold:
            return None
        last_warns = self._last_warn.setdefault(key, {})
        # 対象名が変わるたびに別の組になるので、古い発火記録を捨てないと
        # 長い run で単調に増える。
        expired = [p for p, t in last_warns.items() if (current_tick - t) >= window]
        for p in expired:
            del last_warns[p]
        last_tick = last_warns.get(pattern)
        if last_tick is not None and (current_tick - last_tick) < window:
            return None
        last_warns[pattern] = current_tick
        return CrossTickFailureRepeat(
            tool_name=action.tool_name,
            fingerprint=action.fingerprint,
            error_code=error_code,
            count=count,
            window=window,
            tick=current_tick,
        )
