"""ToolCallLoopGuardService の単体テスト (Issue #226)。

同一 tool + 同一引数の連打を検知して、観測 buffer に警告 entry を入れる
振る舞いを検証する。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from ai_rpg_world.application.llm.services.tool_call_loop_guard import (
    DEFAULT_LOOP_THRESHOLDS,
    DEFAULT_OTHER_THRESHOLD,
    ToolCallLoopGuardService,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPEECH,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _pid(value: int) -> PlayerId:
    return PlayerId.create(value)


def _fixed_clock() -> datetime:
    return datetime(2026, 5, 25, 0, 0, 0)


class TestToolCallLoopGuardServiceInitialization:
    """ToolCallLoopGuardService の初期化バリデーション。"""

    def test_default_threshold_two_raises_value_error(self) -> None:
        """default_threshold は 2 以上でなければ ValueError を投げる。"""
        with pytest.raises(ValueError):
            ToolCallLoopGuardService(
                DefaultObservationContextBuffer(),
                default_threshold=1,
            )

    def test_window_size_two_raises_value_error(self) -> None:
        """window_size は 2 以上でなければ ValueError を投げる。"""
        with pytest.raises(ValueError):
            ToolCallLoopGuardService(
                DefaultObservationContextBuffer(),
                window_size=1,
            )

    def test_observation_buffer_raises_type_error(self) -> None:
        """observation_buffer は IObservationContextBuffer 必須。"""
        with pytest.raises(TypeError):
            ToolCallLoopGuardService(observation_buffer="not a buffer")  # type: ignore[arg-type]


class TestToolCallLoopGuardServiceDefaultClock:
    """既定 clock が注入する警告観測の occurred_at の時刻型を保証する。"""

    def test_default_clock_emits_timezone_aware_occurred_at(self) -> None:
        """clock 未注入のとき、注入される警告観測の occurred_at が timezone-aware になる。

        naive な occurred_at が sliding window に混入すると、aware な観測との
        時刻比較が TypeError になり prompt 構築ごと落ちる (全機能 ON 実験の
        run を tick 62 で停止させた実障害) ため、既定 clock は aware を返す。
        """
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf)
        pid = _pid(1)
        for _ in range(3):
            svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        entries = buf.get_observations(pid)
        assert len(entries) == 1
        assert entries[0].occurred_at.tzinfo is not None


class TestToolCallLoopGuardServiceWaitDetection:
    """spot_graph_wait の閾値 3 連続での発火挙動。"""

    def test_three_consecutive_same_wait_records_emit_one_warning(self) -> None:
        """wait は threshold=3。3 回目で警告 entry が buffer に追加される。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        for _ in range(3):
            svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        entries = buf.get_observations(pid)
        assert len(entries) == 1
        out = entries[0].output
        assert out.structured["loop_guard"] is True
        assert out.structured["tool_name"] == TOOL_NAME_SPOT_GRAPH_WAIT
        assert out.structured["consecutive_count"] == 3
        assert TOOL_NAME_SPOT_GRAPH_WAIT in out.prose

    def test_two_does_not_trigger(self) -> None:
        """wait の threshold=3 未満では警告は出ない。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        for _ in range(2):
            svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        assert buf.get_observations(pid) == []

    def test_emits_warning_for_4_five_one_6(self) -> None:
        """threshold (wait=3) の倍数で警告を再発火する。

        旧実装は once-only で 105 回 wait しても警告 1 件しか出ず、第24回
        実験 (#343) で「最初の警告のあと LLM が wait を止められなかった」
        症状を引き起こした。新実装は threshold の倍数 (3, 6, 9, ...) で
        繰り返し気付かせる。
        """
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        # 4 回連続 → 警告 1 件 (3 回目発火、4 回目は次の 6 回目までお預け)
        for _ in range(4):
            svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        assert len(buf.get_observations(pid)) == 1
        # 5 回目 → まだ 1 件
        svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        assert len(buf.get_observations(pid)) == 1
        # 6 回目 → 再発火 2 件目
        svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        assert len(buf.get_observations(pid)) == 2

    def test_repeated_warnings_change_message(self) -> None:
        """繰り返し警告の prose が同じだと LLM が学習でフィルタする可能性がある。

        テンプレートを deterministic に rotate して、同じ条件でも文面が変
        わることを保証する。
        """
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        # 9 連打 → threshold=3 の倍数で 3 回警告 (3, 6, 9)
        for _ in range(9):
            svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        obs = buf.get_observations(pid)
        assert len(obs) == 3
        proses = [o.output.prose for o in obs]
        # 連続する 2 件は文面が異なる (rotation の証拠)
        assert proses[0] != proses[1]
        assert proses[1] != proses[2]


class TestToolCallLoopGuardServiceArgumentSensitivity:
    """引数が変わると同一 tool でも発火しないこと。"""

    def test_travel_destination_does_not_trigger(self) -> None:
        """destination が違えば fingerprint が違うので連打扱いされない。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        for dest in ("S1", "S2", "S3", "S4"):
            svc.record_and_check(
                pid,
                TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
                {"destination_label": dest},
            )
        assert buf.get_observations(pid) == []

    def test_emits_warning_for_travel_same_destination_two(self) -> None:
        """travel_to は threshold=2。同一 destination 2 回目で警告。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        for _ in range(2):
            svc.record_and_check(
                pid,
                TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
                {"destination_label": "S1"},
            )
        entries = buf.get_observations(pid)
        assert len(entries) == 1
        assert entries[0].output.structured["consecutive_count"] == 2

    def test_streak_warning_names_target_and_orders_next_action(self) -> None:
        """連続同一行動の警告は対象名を出し、同じ行動を避ける指示形にする。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        for _ in range(2):
            svc.record_and_check(
                pid,
                TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
                {"destination_label": "山頂"},
            )

        entries = buf.get_observations(pid)
        assert len(entries) == 1
        prose = entries[0].output.prose
        assert "対象: 山頂" in prose
        assert "以外の行動を選ぶこと" in prose
        assert "必ず失敗" not in prose

    def test_streak_warning_summarizes_give_item_recipients(self) -> None:
        """give_item の警告は gives 配列内の相手名を対象として短く表示する。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(
            buf,
            clock=_fixed_clock,
            thresholds={"give_item": 2},
        )
        pid = _pid(1)
        args = {
            "gives": [
                {"item_label": "流木", "target_player_label": "エイダ"},
                {"item_label": "真水", "target_player_label": "ノア"},
            ]
        }
        for _ in range(2):
            svc.record_and_check(pid, "give_item", args)

        entries = buf.get_observations(pid)
        assert len(entries) == 1
        assert "対象: エイダ ほか" in entries[0].output.prose

    def test_emits_warning_for_speech_speak_same_arguments_two(self) -> None:
        """speech_speak は threshold=2 (Issue #269 第17回 R2 で 3 連続失敗が
        拾われなかった対策)。同一 channel + content + target_label の 2 回目
        で警告が出る。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        args = {"channel": "whisper", "content": "リン、合流しよう。", "target_label": ""}
        for _ in range(2):
            svc.record_and_check(pid, TOOL_NAME_SPEECH, args)
        entries = buf.get_observations(pid)
        assert len(entries) == 1
        assert entries[0].output.structured["tool_name"] == TOOL_NAME_SPEECH
        assert entries[0].output.structured["consecutive_count"] == 2

    def test_speech_speak_does_not_trigger(self) -> None:
        """通常の会話は発話ごとに content が変わるため fingerprint が変わって
        警告は出ない (legitimate な往復会話を誤検知しない)。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        svc.record_and_check(
            pid, TOOL_NAME_SPEECH, {"channel": "say", "content": "聞こえる？"}
        )
        svc.record_and_check(
            pid, TOOL_NAME_SPEECH, {"channel": "say", "content": "今どこにいる？"}
        )
        assert buf.get_observations(pid) == []

    def test_argument_count(self) -> None:
        """連続性が崩れたら閾値カウンタがリセットされる。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        svc.record_and_check(
            pid, TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"destination_label": "S1"}
        )
        svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        # wait 2 → travel_to → wait 2: いずれも閾値到達せず警告は出ない
        assert buf.get_observations(pid) == []


class TestToolCallLoopGuardServicePlayerIsolation:
    """player 間で履歴が混ざらないこと。"""

    def test_other_player_does_not_affect(self) -> None:
        """履歴は player_id ごとに分離される。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        a, b = _pid(1), _pid(2)
        for _ in range(2):
            svc.record_and_check(a, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        for _ in range(3):
            svc.record_and_check(b, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        # b にだけ警告が出る
        assert buf.get_observations(a) == []
        assert len(buf.get_observations(b)) == 1


class TestToolCallLoopGuardServiceDefaultThreshold:
    """thresholds 辞書に無い tool は default_threshold が使われる。"""

    def test_unknown_tool_five_trigger(self) -> None:
        """default_threshold=5 (デフォルト) なので 5 回目で警告。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        for _ in range(4):
            svc.record_and_check(pid, "memory_explore_related", {"q": "x"})
        assert buf.get_observations(pid) == []
        svc.record_and_check(pid, "memory_explore_related", {"q": "x"})
        assert len(buf.get_observations(pid)) == 1

    def test_value_custom_can_override(self) -> None:
        """初期化時に thresholds を渡せば既定が上書きされる。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(
            buf,
            clock=_fixed_clock,
            thresholds={TOOL_NAME_SPOT_GRAPH_WAIT: 2},
        )
        pid = _pid(1)
        for _ in range(2):
            svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        assert len(buf.get_observations(pid)) == 1


class TestToolCallLoopGuardServiceWarningResume:
    """連打が中断して別の連打に切り替わったら警告を再発行する。"""

    def test_emits_warning_for_repeated_different_arguments(self) -> None:
        """tool / fingerprint が変わったら抑制状態がリセットされる。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        for _ in range(3):
            svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        # 一旦違う tool を挟む
        svc.record_and_check(
            pid, TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"destination_label": "S1"}
        )
        # 別の引数で interact を 4 回連打
        for _ in range(4):
            svc.record_and_check(
                pid,
                TOOL_NAME_SPOT_GRAPH_INTERACT,
                {"object_label": "OBJ1", "action_name": "examine"},
            )
        entries = buf.get_observations(pid)
        assert len(entries) == 2
        kinds = [e.output.structured["tool_name"] for e in entries]
        assert kinds == [TOOL_NAME_SPOT_GRAPH_WAIT, TOOL_NAME_SPOT_GRAPH_INTERACT]


class TestToolCallLoopGuardServiceConstants:
    """既定の閾値マップが期待値どおり。"""

    def test_default_value(self) -> None:
        """DEFAULT_LOOP_THRESHOLDS は wait=3 / travel=2 / interact=4 / speech=2。"""
        assert DEFAULT_LOOP_THRESHOLDS[TOOL_NAME_SPOT_GRAPH_WAIT] == 3
        assert DEFAULT_LOOP_THRESHOLDS[TOOL_NAME_SPOT_GRAPH_TRAVEL_TO] == 2
        assert DEFAULT_LOOP_THRESHOLDS[TOOL_NAME_SPOT_GRAPH_INTERACT] == 4
        # Issue #269 第17回 R2: speech_speak の同一引数連発も travel_to と
        # 同じ threshold=2 で拾う。
        assert DEFAULT_LOOP_THRESHOLDS[TOOL_NAME_SPEECH] == 2
        assert DEFAULT_OTHER_THRESHOLD == 5


class TestToolCallLoopGuardServiceTraceEmission:
    """Issue #240 後続: loop_guard 警告が ITraceRecorder に LOOP_GUARD_WARNING として記録される。"""

    def test_emits_warning_for_trace_recorder_loop_guard_warning(self) -> None:
        """3 回連続 wait で警告観測注入と同時に trace に 1 イベント。"""
        from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind

        class _CapturingRecorder(NullTraceRecorder):
            """record() の引数をキャプチャするテスト用 recorder。"""

            def __init__(self) -> None:
                super().__init__()
                self.calls: list[dict] = []

            def record(self, kind, *, tick=None, player_id=None, **payload):
                self.calls.append(
                    {"kind": kind, "tick": tick, "player_id": player_id, "payload": payload}
                )
                return super().record(kind, tick=tick, player_id=player_id, **payload)

        recorder = _CapturingRecorder()
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(
            buf,
            clock=_fixed_clock,
            trace_recorder=recorder,
            current_tick_provider=lambda: 42,
        )
        pid = _pid(1)
        for _ in range(3):
            svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        # 1 回だけ trace に記録される
        assert len(recorder.calls) == 1
        call = recorder.calls[0]
        assert call["kind"] == TraceEventKind.LOOP_GUARD_WARNING
        assert call["tick"] == 42
        assert call["player_id"] == 1
        assert call["payload"]["tool_name"] == TOOL_NAME_SPOT_GRAPH_WAIT
        assert call["payload"]["consecutive_count"] == 3

    def test_trace_recorder_none_observation_trace_not_recorded(self) -> None:
        """recorder=None の場合は警告観測のみ。下位互換維持。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        for _ in range(3):
            svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        # observation は 1 件入る
        assert len(buf.get_observations(pid)) == 1
        # trace なし状態でクラッシュしない (本テストが通過すれば OK)

    def test_trace_recorder_exception_does_not_stop_loop_guard(self) -> None:
        """trace 失敗時も警告観測は注入される (silent except)。"""
        from ai_rpg_world.application.trace import ITraceRecorder

        class _BrokenRecorder(ITraceRecorder):
            def record(self, kind, *, tick=None, player_id=None, **payload):
                raise RuntimeError("trace failed")

            def close(self) -> None:
                pass

        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(
            buf, clock=_fixed_clock, trace_recorder=_BrokenRecorder()
        )
        pid = _pid(1)
        for _ in range(3):
            svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        # trace 失敗にもかかわらず観測注入は成功
        assert len(buf.get_observations(pid)) == 1


class TestToolCallLoopGuardServiceTraceRecorderProvider:
    """Issue #240 後続バグ修正: trace_recorder_provider で use 時 look-up が動作する。"""

    def test_provider_via_after_recorder(self) -> None:
        """構築後に provider が返す recorder を変えたら、警告発火時にその recorder が使われる。

        実験スクリプト経路 (runtime.set_trace_recorder() で後から差し込み) を模倣する。
        """
        from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind

        class _CapturingRecorder(NullTraceRecorder):
            def __init__(self) -> None:
                super().__init__()
                self.calls: list[dict] = []

            def record(self, kind, *, tick=None, player_id=None, **payload):
                self.calls.append(
                    {"kind": kind, "tick": tick, "player_id": player_id, "payload": payload}
                )
                return super().record(kind, tick=tick, player_id=player_id, **payload)

        # 最初は recorder が None で、後から差し込まれるシナリオ
        late_recorder_holder: list = [None]
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(
            buf,
            clock=_fixed_clock,
            trace_recorder_provider=lambda: late_recorder_holder[0],
        )

        # 後から recorder を差し込む
        captured = _CapturingRecorder()
        late_recorder_holder[0] = captured

        pid = _pid(1)
        for _ in range(3):
            svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})

        # 後から差し込まれた recorder に到達している
        assert len(captured.calls) == 1
        assert captured.calls[0]["kind"] == TraceEventKind.LOOP_GUARD_WARNING

    def test_provider_none_raises_exception(self) -> None:
        """provider が例外を投げても loop guard 本来の責務 (観測注入) は止まらない。"""
        buf = DefaultObservationContextBuffer()

        def broken_provider():
            raise RuntimeError("provider failure")

        svc = ToolCallLoopGuardService(
            buf,
            clock=_fixed_clock,
            trace_recorder_provider=broken_provider,
        )
        pid = _pid(1)
        for _ in range(3):
            svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        # 観測注入は成功
        assert len(buf.get_observations(pid)) == 1

    def test_provider_preferred(self) -> None:
        """trace_recorder と trace_recorder_provider 両方与えると provider 側で look-up。"""
        from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind

        class _CountingRecorder(NullTraceRecorder):
            def __init__(self, name: str) -> None:
                super().__init__()
                self.name = name
                self.count = 0

            def record(self, kind, **kwargs):
                self.count += 1
                return super().record(kind, **kwargs)

        fixed = _CountingRecorder("fixed")
        provider_recorder = _CountingRecorder("provider")
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(
            buf,
            clock=_fixed_clock,
            trace_recorder=fixed,
            trace_recorder_provider=lambda: provider_recorder,
        )
        pid = _pid(1)
        for _ in range(3):
            svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        # provider 側が呼ばれる
        assert provider_recorder.count == 1
        assert fixed.count == 0


class TestToolCallLoopGuardServicePeekStreak:
    """peek_streak が現在の連続記録を非破壊で覗ける挙動を保証する。"""

    def test_returns_none_record_before(self) -> None:
        """まだ何も record されていなければ None。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        assert svc.peek_streak(_pid(1)) is None

    def test_one_record_none(self) -> None:
        """連続 1 回 (= 直前と同じ手を取っていない) は peek_streak の対象外で None。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"target": "X"})
        assert svc.peek_streak(pid) is None

    def test_returns_two_tool_count(self) -> None:
        """同じ tool + 同じ引数を 2 回連続 record すると (tool_name, 2) が返る。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"target": "X"})
        svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"target": "X"})
        assert svc.peek_streak(pid) == (TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, 2)

    def test_returns_none_argument(self) -> None:
        """同じ tool でも引数が違えば連続扱いにならず None。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"target": "X"})
        svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"target": "Y"})
        assert svc.peek_streak(pid) is None

    def test_peek(self) -> None:
        """peek_streak を何度呼んでも streak / history は変わらない。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"target": "X"})
        svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"target": "X"})
        first = svc.peek_streak(pid)
        for _ in range(5):
            assert svc.peek_streak(pid) == first

    def test_player_id_player_id_raises_type_error(self) -> None:
        """player id が PlayerId でないと TypeError。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        with pytest.raises(TypeError):
            svc.peek_streak(1)  # type: ignore[arg-type]
