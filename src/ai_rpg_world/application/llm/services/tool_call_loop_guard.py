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

繰り返しを見つける処理は ``loop_guard_detectors``、警告を出す処理は
``loop_guard_warning`` にある。この service は両者をつなぐ入口で、
外から使われる口 (``record_and_check`` / ``peek_streak`` /
``consume_gate_signal``) を保つ。
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.application.llm.llm_argument_fingerprint import (
    build_argument_fingerprint,
)
from ai_rpg_world.application.llm.services.loop_diagnosis import LoopDiagnosis
from ai_rpg_world.application.llm.services.loop_guard_detectors import (
    DEFAULT_CROSS_TICK_FAILURE_THRESHOLD,
    DEFAULT_CROSS_TICK_FAILURE_WINDOW,
    DEFAULT_LOOP_THRESHOLDS,
    DEFAULT_OTHER_THRESHOLD,
    DEFAULT_WINDOW_SIZE,
    ConsecutiveSameActionDetector,
    CrossTickFailureDetector,
    CrossTickFailureRepeat,
    RecordedAction,
    RepeatDetector,
    RepeatSignal,
)
from ai_rpg_world.application.llm.services.loop_guard_warning import (
    LoopGuardGateSignal,
    LoopWarningEmitter,
    RecentAction,
    build_action_summary,
)
from ai_rpg_world.application.llm.services.semantic_repeat_detector import (
    SemanticRepeatDetector,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.application.trace import ITraceRecorder
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

__all__ = [
    "DEFAULT_CROSS_TICK_FAILURE_THRESHOLD",
    "DEFAULT_CROSS_TICK_FAILURE_WINDOW",
    "DEFAULT_LOOP_THRESHOLDS",
    "DEFAULT_OTHER_THRESHOLD",
    "DEFAULT_WINDOW_SIZE",
    "CrossTickFailureTrigger",
    "LoopGuardGateSignal",
    "ToolCallLoopGuardService",
]


_RECENT_ACTION_LIMIT = 5


@dataclass(frozen=True)
class CrossTickFailureTrigger:
    """``record_and_check`` が cross_tick_failure 閾値到達を検知したときに
    呼び出し側へ返す通知 (U6: STRUCTURED_FAILURE + salience)。

    loop_guard 自身は being_id や episode 文脈を持たないため、
    ``BeliefEvidence`` への転記は being 解決ができる呼び出し側に委ねる。
    """

    tool_name: str
    error_code: str
    count: int
    window: int


def _said(arguments: dict[str, Any] | None) -> str | None:
    content = (arguments or {}).get("content")
    return content.strip() or None if isinstance(content, str) else None


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
        time_label_provider: Callable[[], str | None],
        *,
        clock: Callable[[], datetime] | None = None,
        thresholds: dict[str, int] | None = None,
        default_threshold: int = DEFAULT_OTHER_THRESHOLD,
        window_size: int = DEFAULT_WINDOW_SIZE,
        trace_recorder: ITraceRecorder | None = None,
        trace_recorder_provider: Callable[[], ITraceRecorder | None] | None = None,
        current_tick_provider: Callable[[], int | None] | None = None,
        cross_tick_failure_window: int = DEFAULT_CROSS_TICK_FAILURE_WINDOW,
        cross_tick_failure_threshold: int = DEFAULT_CROSS_TICK_FAILURE_THRESHOLD,
        loop_diagnosis: LoopDiagnosis | None = None,
        location_provider: Callable[[PlayerId], str | None] | None = None,
        semantic_repeat_detector: SemanticRepeatDetector | None = None,
    ) -> None:
        """
        trace_recorder vs trace_recorder_provider:
            ``trace_recorder`` は構築時に捕まえる固定 recorder (主にテスト用)。
            ``trace_recorder_provider`` は use 時に look-up する callable で、
            ``runtime.set_trace_recorder()`` のような後から差し込まれる構成で
            使う (実験スクリプト経路はこちら)。両方与えると provider 優先。

        loop_diagnosis:
            与えると、警告を出す前に繰り返しの理由を問い、文面を選ぶ (#1411)。
            None なら判断を引かず、今の文面で出す。
        location_provider:
            見立ての材料と文面に載せる現在地の名前。
        semantic_repeat_detector:
            与えると、完全一致で数えられない言い直しや往復も判断に問う (#1412)。
            完全一致の検出の後に回し、発火したかを渡す。
        """
        if not isinstance(observation_buffer, IObservationContextBuffer):
            raise TypeError(
                "observation_buffer must be IObservationContextBuffer"
            )
        if not callable(time_label_provider):
            raise TypeError("time_label_provider must be callable")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable or None")
        self._consecutive_detector = ConsecutiveSameActionDetector(
            thresholds=thresholds,
            default_threshold=default_threshold,
            window_size=window_size,
        )
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
        if loop_diagnosis is not None and not isinstance(loop_diagnosis, LoopDiagnosis):
            raise TypeError("loop_diagnosis must be LoopDiagnosis or None")
        if location_provider is not None and not callable(location_provider):
            raise TypeError("location_provider must be callable or None")
        if semantic_repeat_detector is not None and not isinstance(
            semantic_repeat_detector, SemanticRepeatDetector
        ):
            raise TypeError(
                "semantic_repeat_detector must be SemanticRepeatDetector or None"
            )
        cross_tick_detector = CrossTickFailureDetector(
            window=cross_tick_failure_window,
            threshold=cross_tick_failure_threshold,
        )

        self._trace_recorder = trace_recorder
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider
        # 両方が同じ呼び出しで発火したとき、観測は cross_tick を先に積み、
        # gate signal は streak が上書きする。この順を保つために並びを固定する。
        self._detectors: tuple[RepeatDetector, ...] = (
            cross_tick_detector,
            self._consecutive_detector,
        )
        # datetime.utcnow は naive を返し、sliding window 内で aware な観測との
        # 時刻比較が TypeError になるため、既定 clock は aware (UTC) を返す
        #: 公開するのは、見立てが profile から届いたかを外から確かめるため。
        self.loop_diagnosis = loop_diagnosis
        #: 公開する理由は ``loop_diagnosis`` と同じ。
        self.semantic_repeat_detector = semantic_repeat_detector
        self._emitter = LoopWarningEmitter(
            observation_buffer=observation_buffer,
            time_label_provider=time_label_provider,
            clock=clock or (lambda: datetime.now(timezone.utc)),
            trace_recorder_resolver=self._resolve_trace_recorder,
            diagnosis=loop_diagnosis,
            location_provider=location_provider,
        )
        #: 見立ての材料。検出器の数え方とは独立に、直近の数件だけを持つ。
        self._recent_actions: dict[int, deque[RecentAction]] = {}

    def _resolve_trace_recorder(self) -> ITraceRecorder | None:
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
        arguments: dict[str, Any] | None,
        *,
        success: bool | None = None,
        error_code: str | None = None,
        result_summary: str | None = None,
    ) -> CrossTickFailureTrigger | None:
        """tool 呼出を記録し、繰り返しを見つけたら警告観測を注入する。

        呼出側は成功・失敗どちらでも record する。連打は失敗を繰り返す形でも
        問題視したいケースがあるため。

        cross_tick_failure が今回の呼び出しで発火したときだけ
        ``CrossTickFailureTrigger`` を返す。呼び出し側が being_id を解決して
        ``BeliefEvidence`` へ転記するかどうかを決める。

        Args:
            success: 成否。None は成否不明として cross_tick 側には記録しない。
            error_code: 失敗時の error_code。None または ``success!=False``
                のときは cross_tick 側には記録しない。
            result_summary: 行動の結果の文。見立ての材料にする。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(tool_name, str) or not tool_name:
            return None
        action = RecordedAction(
            player_key=player_id.value,
            tool_name=tool_name,
            fingerprint=build_argument_fingerprint(arguments),
            success=success,
            error_code=error_code,
            tick=self._get_current_tick_or_none(),
            result_summary=result_summary,
        )
        recent = self._recent_actions.setdefault(
            player_id.value, deque(maxlen=_RECENT_ACTION_LIMIT)
        )
        recent.append(
            RecentAction(
                action=build_action_summary(tool_name, action.fingerprint),
                succeeded=success,
                result=result_summary,
                said=_said(arguments),
            )
        )
        signals: list[RepeatSignal] = []
        for detector in self._detectors:
            signal = detector.observe(action)
            if signal is not None:
                signals.append(signal)
        if self.semantic_repeat_detector is not None:
            semantic = self.semantic_repeat_detector.observe(
                action, exact_match_fired=bool(signals)
            )
            if semantic is not None:
                signals.append(semantic)
        cross_tick_trigger: CrossTickFailureTrigger | None = None
        for signal in self._emitter.emit_all(player_id, signals, tuple(recent)):
            if isinstance(signal, CrossTickFailureRepeat):
                cross_tick_trigger = CrossTickFailureTrigger(
                    tool_name=signal.tool_name,
                    error_code=signal.error_code,
                    count=signal.count,
                    window=signal.window,
                )
        return cross_tick_trigger

    def consume_gate_signal(self, player_id: PlayerId) -> LoopGuardGateSignal | None:
        """直近の loop_guard 警告 signal を 1 回だけ取り出す。

        reason-first gating は「loop_guard が実際に発火した直後」だけを使う。
        ここで消費することで、1 つの警告から何ターンも 2段階に入り続ける
        ことを防ぐ。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        return self._emitter.consume_gate_signal(player_id)

    def peek_streak(self, player_id: PlayerId) -> tuple[str, int] | None:
        """現在連続している ``(tool_name, count)`` を非破壊で覗き見る。

        prompt_builder が instruction 末尾に「直前 N 回連続で同じ手」警告を
        載せるために使う。連続回数 < 2 なら ``None``。閾値は警告観測の
        閾値とは独立。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        return self._consecutive_detector.peek(player_id.value)

    def _get_current_tick_or_none(self) -> int | None:
        if self._current_tick_provider is None:
            return None
        try:
            tick = self._current_tick_provider()
        except Exception:
            return None
        if not isinstance(tick, int):
            return None
        return tick
