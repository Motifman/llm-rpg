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

    def test_default_threshold_に_2_未満を渡すと_ValueError(self) -> None:
        """default_threshold は 2 以上でなければ ValueError を投げる。"""
        with pytest.raises(ValueError):
            ToolCallLoopGuardService(
                DefaultObservationContextBuffer(),
                default_threshold=1,
            )

    def test_window_size_に_2_未満を渡すと_ValueError(self) -> None:
        """window_size は 2 以上でなければ ValueError を投げる。"""
        with pytest.raises(ValueError):
            ToolCallLoopGuardService(
                DefaultObservationContextBuffer(),
                window_size=1,
            )

    def test_observation_buffer_が_インタフェース不一致なら_TypeError(self) -> None:
        """observation_buffer は IObservationContextBuffer 必須。"""
        with pytest.raises(TypeError):
            ToolCallLoopGuardService(observation_buffer="not a buffer")  # type: ignore[arg-type]


class TestToolCallLoopGuardServiceWaitDetection:
    """spot_graph_wait の閾値 3 連続での発火挙動。"""

    def test_3_回連続で_同じ_wait_を_record_すると_警告が_1_件_注入される(self) -> None:
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

    def test_2_回連続では_発火しない(self) -> None:
        """wait の threshold=3 未満では警告は出ない。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        for _ in range(2):
            svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        assert buf.get_observations(pid) == []

    def test_連打が_4_回_5_回と続いても_警告は_1_件のまま(self) -> None:
        """同じ (tool, fingerprint) が連続する間は警告を抑制する。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        for _ in range(6):
            svc.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_WAIT, {})
        assert len(buf.get_observations(pid)) == 1


class TestToolCallLoopGuardServiceArgumentSensitivity:
    """引数が変わると同一 tool でも発火しないこと。"""

    def test_travel_to_の宛先が_毎回違えば_発火しない(self) -> None:
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

    def test_travel_to_を_同一宛先で_2_回_連打すると_警告(self) -> None:
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

    def test_間に_違う引数が挟まると_カウントがリセットされる(self) -> None:
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

    def test_他プレイヤーの連打は_自プレイヤーの履歴に影響しない(self) -> None:
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

    def test_未知の_tool_は_5_回連続で_発火(self) -> None:
        """default_threshold=5 (デフォルト) なので 5 回目で警告。"""
        buf = DefaultObservationContextBuffer()
        svc = ToolCallLoopGuardService(buf, clock=_fixed_clock)
        pid = _pid(1)
        for _ in range(4):
            svc.record_and_check(pid, "memory_explore_related", {"q": "x"})
        assert buf.get_observations(pid) == []
        svc.record_and_check(pid, "memory_explore_related", {"q": "x"})
        assert len(buf.get_observations(pid)) == 1

    def test_閾値マップを_カスタムに上書きできる(self) -> None:
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

    def test_違う引数の連打に切り替わると_警告は再発火する(self) -> None:
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

    def test_既定の閾値が_第13回実験の所見に整合(self) -> None:
        """DEFAULT_LOOP_THRESHOLDS は wait=3 / travel=2 / interact=4。"""
        assert DEFAULT_LOOP_THRESHOLDS[TOOL_NAME_SPOT_GRAPH_WAIT] == 3
        assert DEFAULT_LOOP_THRESHOLDS[TOOL_NAME_SPOT_GRAPH_TRAVEL_TO] == 2
        assert DEFAULT_LOOP_THRESHOLDS[TOOL_NAME_SPOT_GRAPH_INTERACT] == 4
        assert DEFAULT_OTHER_THRESHOLD == 5
