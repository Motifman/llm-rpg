"""LLM の同一 tool 連打を検知し、観測として警告を注入する service。

第13回実験 (Issue #223) で、カイトが master_study 到達後に
``spot_graph_wait`` を 18 回連続で実行して context が劣化した。
プロンプトでの行動ルール追記による対症療法ではなく、engine 側で
機械的にループを検知し「あなたは同じ行動を繰り返しています」と
観測として LLM に通知する root-cause fix を入れる。

設計判断 (Issue #226):
- 同一性判定は ``(tool_name, argument_fingerprint)`` の完全一致。
  fingerprint は既存の ``build_argument_fingerprint`` を流用。
  → ``travel_to(\"A\") → travel_to(\"B\")`` のように引数が変われば発火しない。
- 閾値は tool 系統ごとに設定 (wait は 3、travel_to は 2、interact は 4、
  その他は 5)。連打しても害が薄い tool (memo_list 等) も default に含まれる。
- 注入は ObservationContextBuffer に直接 append。prompt_builder.drain で
  自然に次ターンに流れる。ObservationPipeline 経由の domain event 化は
  オーバーキル。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ai_rpg_world.application.llm.llm_argument_fingerprint import (
    build_argument_fingerprint,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


DEFAULT_LOOP_THRESHOLDS: Dict[str, int] = {
    TOOL_NAME_SPOT_GRAPH_WAIT: 3,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO: 2,
    TOOL_NAME_SPOT_GRAPH_INTERACT: 4,
}
"""tool ごとの連続回数しきい値 (この回数連続で同一なら警告)。"""

DEFAULT_OTHER_THRESHOLD: int = 5
"""閾値辞書に含まれない tool の default 連続回数。"""

DEFAULT_WINDOW_SIZE: int = 10
"""player ごとに保持する直近 tool call の最大件数。"""


@dataclass(frozen=True)
class _ToolCallRecord:
    """1 回の tool 呼出記録 (loop 判定用)。"""

    tool_name: str
    fingerprint: str


class ToolCallLoopGuardService:
    """同一 tool + 同一引数の連打を検知し、観測として警告を注入する。

    Args:
        observation_buffer: 警告観測の注入先。
        clock: 現在時刻取得関数。テスト時に上書き可能。
        thresholds: tool ごとの連続回数しきい値マップ。
        default_threshold: thresholds に無い tool の閾値。
        window_size: player ごとに保持する直近 tool call の最大件数。
    """

    def __init__(
        self,
        observation_buffer: IObservationContextBuffer,
        *,
        clock: Optional[Callable[[], datetime]] = None,
        thresholds: Optional[Dict[str, int]] = None,
        default_threshold: int = DEFAULT_OTHER_THRESHOLD,
        window_size: int = DEFAULT_WINDOW_SIZE,
        trace_recorder: Optional[ITraceRecorder] = None,
        trace_recorder_provider: Optional[
            Callable[[], Optional[ITraceRecorder]]
        ] = None,
        current_tick_provider: Optional[Callable[[], Optional[int]]] = None,
    ) -> None:
        """
        trace_recorder vs trace_recorder_provider:
            ``trace_recorder`` は構築時に捕まえる固定 recorder (主にテスト用)。
            ``trace_recorder_provider`` は use 時に look-up する callable で、
            ``runtime.set_trace_recorder()`` のような後から差し込まれる構成で
            使う (実験スクリプト経路はこちら)。両方与えると provider 優先。
        """
        if not isinstance(observation_buffer, IObservationContextBuffer):
            raise TypeError(
                "observation_buffer must be IObservationContextBuffer"
            )
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable or None")
        if thresholds is not None and not isinstance(thresholds, dict):
            raise TypeError("thresholds must be dict or None")
        if not isinstance(default_threshold, int) or default_threshold < 2:
            raise ValueError("default_threshold must be int >= 2")
        if not isinstance(window_size, int) or window_size < 2:
            raise ValueError("window_size must be int >= 2")
        if trace_recorder is not None and not isinstance(trace_recorder, ITraceRecorder):
            raise TypeError("trace_recorder must be ITraceRecorder or None")
        if trace_recorder_provider is not None and not callable(
            trace_recorder_provider
        ):
            raise TypeError(
                "trace_recorder_provider must be callable or None"
            )
        if current_tick_provider is not None and not callable(current_tick_provider):
            raise TypeError("current_tick_provider must be callable or None")

        self._observation_buffer = observation_buffer
        self._clock: Callable[[], datetime] = clock or datetime.utcnow
        self._thresholds: Dict[str, int] = dict(thresholds) if thresholds else dict(
            DEFAULT_LOOP_THRESHOLDS
        )
        self._default_threshold = default_threshold
        self._window_size = window_size
        self._trace_recorder = trace_recorder
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider
        self._history: Dict[int, List[_ToolCallRecord]] = {}
        self._last_warned: Dict[int, _ToolCallRecord] = {}

    def _resolve_trace_recorder(self) -> Optional[ITraceRecorder]:
        """use 時に最新の trace_recorder を取得する。

        provider があれば毎回呼び出して look-up、なければ構築時の固定値を返す。
        provider が例外を投げたら None フォールバック。
        """
        if self._trace_recorder_provider is not None:
            try:
                return self._trace_recorder_provider()
            except Exception:
                return None
        return self._trace_recorder

    def record_and_check(
        self,
        player_id: PlayerId,
        tool_name: str,
        arguments: Optional[Dict[str, Any]],
        *,
        game_time_label: Optional[str] = None,
    ) -> None:
        """tool 呼出を記録し、連続性しきい値超過なら警告観測を注入する。

        呼出側 (orchestrator) は成功・失敗どちらでも record する。連打は失敗
        を繰り返す形でも問題視したいケースがあるため。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(tool_name, str) or not tool_name:
            return
        fingerprint = build_argument_fingerprint(arguments)
        record = _ToolCallRecord(tool_name=tool_name, fingerprint=fingerprint)

        key = player_id.value
        history = self._history.setdefault(key, [])
        history.append(record)
        if len(history) > self._window_size:
            del history[: len(history) - self._window_size]

        threshold = self._thresholds.get(tool_name, self._default_threshold)
        if len(history) < threshold:
            return
        latest = history[-threshold:]
        if any(r != record for r in latest):
            return

        # 同じ (tool, fingerprint) で連続警告するのは冗長なので、最後に警告
        # を出した record を覚えておき、連打が続く限り 1 回しか出さない。
        # tool/fingerprint が変われば抑制状態はリセットされる。
        if self._last_warned.get(key) == record:
            return
        self._last_warned[key] = record

        self._observation_buffer.append(
            player_id,
            self._build_warning_entry(
                tool_name=tool_name,
                fingerprint=fingerprint,
                consecutive=threshold,
                game_time_label=game_time_label,
            ),
        )
        # Issue #240 後続: 警告観測の注入を trace にも残し、実 LLM 試走の
        # 振り返りで「loop_guard が実際に発火したか」を可視化する。
        # trace_recorder は use 時に look-up (provider 経由) して、
        # runtime.set_trace_recorder() で後から差し込まれた recorder にも追従する。
        recorder = self._resolve_trace_recorder()
        if recorder is not None:
            tick: Optional[int] = None
            if self._current_tick_provider is not None:
                try:
                    tick = self._current_tick_provider()
                except Exception:
                    tick = None
            try:
                recorder.record(
                    TraceEventKind.LOOP_GUARD_WARNING,
                    tick=tick,
                    player_id=int(player_id.value),
                    tool_name=tool_name,
                    argument_fingerprint=fingerprint,
                    consecutive_count=threshold,
                    game_time_label=game_time_label,
                )
            except Exception:
                # trace 失敗は loop guard 本来の責務を止めない
                pass

    def _build_warning_entry(
        self,
        *,
        tool_name: str,
        fingerprint: str,
        consecutive: int,
        game_time_label: Optional[str],
    ) -> ObservationEntry:
        prose = (
            f"⚠ 直近 {consecutive} ターン連続で `{tool_name}` を同じ引数で実行しています。"
            f"状況に変化が無いまま同じ行動を繰り返している可能性があります。"
            f"観測内容を再確認し、別の行動 (speech で相手に状況を伝える、別の場所に移動する、"
            f"別の対象を examine する、等) を検討してください。"
        )
        output = ObservationOutput(
            prose=prose,
            structured={
                "loop_guard": True,
                "tool_name": tool_name,
                "argument_fingerprint": fingerprint,
                "consecutive_count": consecutive,
            },
            observation_category="self_only",
            schedules_turn=False,
            breaks_movement=False,
        )
        return ObservationEntry(
            occurred_at=self._clock(),
            output=output,
            game_time_label=game_time_label,
        )
