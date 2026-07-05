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
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from ai_rpg_world.application.llm.llm_argument_fingerprint import (
    build_argument_fingerprint,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPEECH,
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

# PR-AA (Y_after_pr639_640 後続): 「離れた tick に散らばる同一失敗の反復」
# 検出用の default 値。連続 streak (別トラッカー) とは独立。
DEFAULT_CROSS_TICK_FAILURE_WINDOW: int = 20
"""cross_tick_failure 検出の tick 幅。この tick 数以内の失敗を集約対象とする。"""

DEFAULT_CROSS_TICK_FAILURE_THRESHOLD: int = 3
"""cross_tick_failure 検出の閾値。window 内で同 (tool, fingerprint, error_code)
が本数以上出現したら警告を発火する。"""


_CROSS_TICK_WARNING_TEMPLATES: tuple[str, ...] = (
    "⚠ 直近 {window} tick 以内で `{tool_name}` を同じ引数・同じ失敗 "
    "(`{error_code}`) で {count} 回試みています。連続してはいませんが、"
    "同じ壁に何度も当たっている状態です。この失敗理由は状況が変わらない"
    "限り解消しません。目的自体を見直すか、別の対象・別の手段を検討して"
    "ください。",
    "同じ失敗 (`{error_code}`) を伴う `{tool_name}` を、間に別行動を挟みつつ "
    "{count} 回繰り返しました。表面上は行動が変わっていても、実質的な"
    "アプローチが変わっていないのかもしれません。観測を読み直し、"
    "この失敗の前提条件を満たすには何が必要か整理し直してください。",
    "`{tool_name}` の失敗 (`{error_code}`) が {count} 回目です。tick を跨いで"
    "散発的に試していますが、結果が同じなら状況も変わっていない可能性が"
    "高いです。周囲を再確認するか、この目的を別ルートで達成する方法を"
    "考えてみてください。",
)
"""cross_tick_failure 警告 prose のテンプレート。
``{tool_name}`` / ``{error_code}`` / ``{count}`` / ``{window}`` を format 対象とする。
"""


# 警告文のバリエーション。同じ文面が繰り返し届くと LLM が「3 回 wait → 同じ
# 警告」のパターンを学習して文面ごと無視するようになる可能性があるので、
# 警告を再発火するたびに文面を変える。warn_index % len(templates) で
# deterministic に選ぶ (テスト容易性 + 実走での「予測しづらさ」の両立)。
# templates は { consecutive } { tool_name } を含む format 文字列。
_WARNING_TEMPLATES: tuple[str, ...] = (
    "⚠ 直近 {consecutive} ターン連続で `{tool_name}` を同じ引数で実行しています。"
    "状況に変化が無いまま同じ行動を繰り返している可能性があります。"
    "観測内容を再確認し、別の行動 (speech で相手に状況を伝える、別の場所に移動する、"
    "別の対象を examine する、等) を検討してください。",
    "気が付けば `{tool_name}` を {consecutive} 回連続で同じやり方で試みています。"
    "現状を変えるには別の角度のアプローチが必要かもしれません。"
    "周囲の状況や手持ちアイテムを見直してください。",
    "{consecutive} 回続けて同じ `{tool_name}` を選択していますが、結果が変わって"
    "いる兆候はありますか？ いったん立ち止まり、目的を達成する別の手段を考えて"
    "みてください (会話で情報を求める / 場所を移す / 対象を変える等)。",
    "あなたは {consecutive} 連続で `{tool_name}` に固執しています。同じ行為を"
    "重ねても望む結果が出ないなら、それは戦略の見直しの合図です。"
    "別の選択肢を試してみてください。",
    "立て続けに {consecutive} 回 `{tool_name}` を実行している点が気になります。"
    "同じ刺激を繰り返しているうちは、世界の側も同じ反応しか返さないものです。"
    "今までと違う行動を試す好機ではないでしょうか。",
)
"""警告 prose のテンプレート。{tool_name} と {consecutive} を含む format 文字列。"""


@dataclass(frozen=True)
class _ToolCallRecord:
    """1 回の tool 呼出記録 (loop 判定用)。"""

    tool_name: str
    fingerprint: str


@dataclass(frozen=True)
class _FailureRecord:
    """1 回の失敗記録 (cross_tick_failure 検出用、PR-AA)。

    連続 streak トラッカー (_ToolCallRecord) とは独立。tick を持つことで
    「window 外の古いエントリはドロップ」を実装する。
    """

    tick: int
    tool_name: str
    fingerprint: str
    error_code: str


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
        cross_tick_failure_window: int = DEFAULT_CROSS_TICK_FAILURE_WINDOW,
        cross_tick_failure_threshold: int = DEFAULT_CROSS_TICK_FAILURE_THRESHOLD,
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
        if (
            not isinstance(cross_tick_failure_window, int)
            or cross_tick_failure_window < 2
        ):
            raise ValueError("cross_tick_failure_window must be int >= 2")
        if (
            not isinstance(cross_tick_failure_threshold, int)
            or cross_tick_failure_threshold < 2
        ):
            raise ValueError("cross_tick_failure_threshold must be int >= 2")

        self._observation_buffer = observation_buffer
        # datetime.utcnow は naive を返し、sliding window 内で aware な観測との
        # 時刻比較が TypeError になるため、既定 clock は aware (UTC) を返す
        self._clock: Callable[[], datetime] = clock or (
            lambda: datetime.now(timezone.utc)
        )
        self._thresholds: Dict[str, int] = dict(thresholds) if thresholds else dict(
            DEFAULT_LOOP_THRESHOLDS
        )
        self._default_threshold = default_threshold
        self._window_size = window_size
        self._trace_recorder = trace_recorder
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider
        self._history: Dict[int, List[_ToolCallRecord]] = {}
        # 直近の record と連続回数 (player_id -> (record, count))。
        # 同じ record が続いている間 count を増やし、threshold の倍数で警告を
        # 再発火する (旧 once-only から repeat-every-threshold へ)。
        self._streak: Dict[int, tuple[_ToolCallRecord, int]] = {}
        # player ごとに「これまで何回警告を発火したか」を保持して、警告文面の
        # バリエーション選択 (warn_count % len(templates)) に使う。
        self._warn_count: Dict[int, int] = {}
        # PR-AA (Y_after_pr639_640 後続): cross_tick_failure 検出用の別トラッカー。
        # 既存 streak トラッカーとは独立して、失敗のみを (tick, tool, fp, ec) の
        # deque に積んで window 外を drop、閾値到達で警告発火。
        self._cross_tick_failure_window = cross_tick_failure_window
        self._cross_tick_failure_threshold = cross_tick_failure_threshold
        self._failure_history: Dict[int, List[_FailureRecord]] = {}
        # 同一パターンの再発火抑制: warn 発火した (tool, fp, ec) を発火 tick と
        # 共に記録する。window より古くなったら再発火を許可 (= 対象が変われば
        # また警告)。
        self._cross_tick_last_warn: Dict[
            int, Dict[tuple[str, str, str], int]
        ] = {}
        # cross_tick 警告の文面インデックス (rotation)。
        self._cross_tick_warn_count: Dict[int, int] = {}

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
        success: Optional[bool] = None,
        error_code: Optional[str] = None,
    ) -> None:
        """tool 呼出を記録し、連続性しきい値超過なら警告観測を注入する。

        呼出側 (orchestrator) は成功・失敗どちらでも record する。連打は失敗
        を繰り返す形でも問題視したいケースがあるため。

        PR-AA (Y_after_pr639_640 後続): ``success=False`` かつ ``error_code``
        が渡された場合、cross_tick_failure トラッカーにも記録する。連続同一
        streak (旧挙動) とは独立の判定経路で、tick 幅の window 内で同じ
        (tool, fingerprint, error_code) が閾値回数出現したときに警告する。

        Args:
            success: 成否 (True/False/None)。None は「旧 API 呼び出し =
                成否不明」扱いで cross_tick 側には記録しない。
            error_code: 失敗時の error_code。None または ``success!=False``
                のときは cross_tick 側には記録しない。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(tool_name, str) or not tool_name:
            return
        fingerprint = build_argument_fingerprint(arguments)
        record = _ToolCallRecord(tool_name=tool_name, fingerprint=fingerprint)

        # PR-AA: 失敗ケースは cross_tick_failure トラッカーにも積む。
        # 既存 streak 処理より先に走らせて、警告注入順序も cross_tick が
        # 先になるよう明示的に配置する。
        if success is False and isinstance(error_code, str) and error_code:
            self._record_and_check_cross_tick_failure(
                player_id=player_id,
                tool_name=tool_name,
                fingerprint=fingerprint,
                error_code=error_code,
                game_time_label=game_time_label,
            )

        key = player_id.value
        history = self._history.setdefault(key, [])
        history.append(record)
        if len(history) > self._window_size:
            del history[: len(history) - self._window_size]

        threshold = self._thresholds.get(tool_name, self._default_threshold)
        # streak (player ごとの「現在連続で同じ (tool, fingerprint) を実行している
        # 回数」) を維持する。前回の record と異なれば 1 にリセット、同じなら +1。
        prev = self._streak.get(key)
        if prev is None or prev[0] != record:
            streak_count = 1
        else:
            streak_count = prev[1] + 1
        self._streak[key] = (record, streak_count)

        # threshold の倍数で警告を再発火する。
        # 例: threshold=3 のとき streak 3, 6, 9... で発火 (旧 once-only ではなく、
        # LLM が警告を無視し続けても何度でも気付かせる)。
        if streak_count < threshold or streak_count % threshold != 0:
            return

        # warn_count を進めて文面選択に使う (deterministic だが variety あり)。
        warn_index = self._warn_count.get(key, 0)
        self._warn_count[key] = warn_index + 1
        self._observation_buffer.append(
            player_id,
            self._build_warning_entry(
                tool_name=tool_name,
                fingerprint=fingerprint,
                consecutive=streak_count,
                warn_index=warn_index,
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
                    consecutive_count=streak_count,
                    game_time_label=game_time_label,
                )
            except Exception:
                # trace 失敗は loop guard 本来の責務を止めない
                pass

    def peek_streak(self, player_id: PlayerId) -> Optional[tuple[str, int]]:
        """現在連続している ``(tool_name, count)`` を非破壊で覗き見る。

        ``record_and_check`` で進めた streak を prompt_builder が参照して、
        instruction 末尾に「直前 N 回連続で同じ手」警告を載せるために使う。
        副作用なし。連続回数 < 2 (= 直前に同じ手を取っていない) なら ``None``。
        prompt 上の attention に対する追加ヒントなので閾値は loop_guard 本体の
        thresholds とは独立 (本体は warning 観測注入用、こちらは即時 prefix 用)。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        streak = self._streak.get(player_id.value)
        if streak is None:
            return None
        record, count = streak
        if count < 2:
            return None
        return (record.tool_name, count)

    def _record_and_check_cross_tick_failure(
        self,
        *,
        player_id: PlayerId,
        tool_name: str,
        fingerprint: str,
        error_code: str,
        game_time_label: Optional[str],
    ) -> None:
        """PR-AA (Y_after_pr639_640 後続): 連続していない同一失敗の反復を検出。

        tick 幅 (default 20) の window 内で同じ (tool, fingerprint, error_code)
        が threshold 回数以上出現したら警告を発火する。既存 streak トラッカー
        とは独立に動作し、間に別 tool が挟まっていても検出できる。

        window 外のエントリは drop するので、状況が変わって同 failure を
        しばらく出さなければ counter は自然にリセットされる。
        """
        current_tick = self._get_current_tick_or_none()
        if current_tick is None:
            # tick provider が無い / 例外 → cross_tick 検出は skip
            # (連続 streak 側は既に record 済みなので silent OK)
            return
        key = player_id.value
        history = self._failure_history.setdefault(key, [])
        history.append(
            _FailureRecord(
                tick=current_tick,
                tool_name=tool_name,
                fingerprint=fingerprint,
                error_code=error_code,
            )
        )
        # window 外の古いエントリを drop
        window = self._cross_tick_failure_window
        history[:] = [
            r for r in history if (current_tick - r.tick) < window
        ]
        # 同一パターンのカウント
        pattern = (tool_name, fingerprint, error_code)
        count = sum(
            1
            for r in history
            if (r.tool_name, r.fingerprint, r.error_code) == pattern
        )
        if count < self._cross_tick_failure_threshold:
            return
        # 再発火抑制: 直前の警告発火が window 内なら silent (連打で毎回鳴ら
        # ないようにする)。抑制 window は failure window と同じ幅で十分。
        last_warns = self._cross_tick_last_warn.setdefault(key, {})
        # code-review MEDIUM 1 反映: window より古い warn 記録は drop する。
        # unique fingerprint (= object_label が変わるたび別 key) が積み上がる
        # 長走 run で、_cross_tick_last_warn が単調増大しないようにする。
        expired = [
            p for p, t in last_warns.items() if (current_tick - t) >= window
        ]
        for p in expired:
            del last_warns[p]
        last_tick = last_warns.get(pattern)
        if last_tick is not None and (current_tick - last_tick) < window:
            return
        last_warns[pattern] = current_tick

        warn_index = self._cross_tick_warn_count.get(key, 0)
        self._cross_tick_warn_count[key] = warn_index + 1
        self._observation_buffer.append(
            player_id,
            self._build_cross_tick_failure_warning_entry(
                tool_name=tool_name,
                fingerprint=fingerprint,
                error_code=error_code,
                count=count,
                window=window,
                warn_index=warn_index,
                game_time_label=game_time_label,
            ),
        )
        # trace 側にも残す (既存 LOOP_GUARD_WARNING kind を使い、pattern
        # フィールドで区別可能にする)。
        recorder = self._resolve_trace_recorder()
        if recorder is not None:
            try:
                # code-review LOW 1 反映: 既存 ``consecutive_count`` フィールドは
                # 「連続」semantics を持つので、cross_tick 側は distinct
                # フィールド ``window_count`` を使う。将来 trace analyzer が
                # pattern で振り分けやすいよう field を分けた。
                recorder.record(
                    TraceEventKind.LOOP_GUARD_WARNING,
                    tick=current_tick,
                    player_id=int(player_id.value),
                    tool_name=tool_name,
                    argument_fingerprint=fingerprint,
                    window_count=count,
                    window_size=window,
                    game_time_label=game_time_label,
                    pattern="cross_tick_failure",
                    error_code=error_code,
                )
            except Exception:
                pass

    def _get_current_tick_or_none(self) -> Optional[int]:
        """current_tick_provider を安全に呼び出して int を返す。"""
        if self._current_tick_provider is None:
            return None
        try:
            tick = self._current_tick_provider()
        except Exception:
            return None
        if not isinstance(tick, int):
            return None
        return tick

    def _build_cross_tick_failure_warning_entry(
        self,
        *,
        tool_name: str,
        fingerprint: str,
        error_code: str,
        count: int,
        window: int,
        warn_index: int,
        game_time_label: Optional[str],
    ) -> ObservationEntry:
        """cross_tick_failure 警告の ObservationEntry を組み立てる。"""
        template = _CROSS_TICK_WARNING_TEMPLATES[
            warn_index % len(_CROSS_TICK_WARNING_TEMPLATES)
        ]
        prose = template.format(
            tool_name=tool_name,
            error_code=error_code,
            count=count,
            window=window,
        )
        output = ObservationOutput(
            prose=prose,
            structured={
                "loop_guard": True,
                "pattern": "cross_tick_failure",
                "tool_name": tool_name,
                "argument_fingerprint": fingerprint,
                "error_code": error_code,
                "count": count,
                "window": window,
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

    def _build_warning_entry(
        self,
        *,
        tool_name: str,
        fingerprint: str,
        consecutive: int,
        warn_index: int,
        game_time_label: Optional[str],
    ) -> ObservationEntry:
        # warn_index で deterministic にテンプレートを選び、繰り返し警告でも
        # 文面が固定にならないようにする (LLM が同じ警告をパターン学習で
        # 無視するのを防ぐ)。
        template = _WARNING_TEMPLATES[warn_index % len(_WARNING_TEMPLATES)]
        prose = template.format(tool_name=tool_name, consecutive=consecutive)
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
