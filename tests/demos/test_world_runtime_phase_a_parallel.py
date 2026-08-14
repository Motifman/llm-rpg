"""Phase A 並列化 (#346 Step 1) の挙動検証。

``LLM_TURN_PARALLEL_WORKERS`` が config で 0 / 未設定なら従来の serial 経路。
2 以上なら ThreadPoolExecutor で LLM 呼び出しを並列化する。

並列化後でも:
- Phase B (世界 mutation) は to_run 順に serial で適用される
- LLM 例外は Phase B で LlmCommandResultDto 化される
- 各 turn の result は同じ (parallelize は速度だけの最適化)
"""

from __future__ import annotations

from pathlib import Path
import threading

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "abandoned_hospital.json"
)


class TestResolveLlmParallelWorkers:
    """config の解釈が安全であること。"""

    def test_unset_zero(self) -> None:
        """未設定なら serial 経路を使う。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        assert cfg.llm_turn_parallel_workers == 0

    def test_config_value(self) -> None:
        """正の整数ならその worker 数を使う。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={"LLM_TURN_PARALLEL_WORKERS": "4"}
        )
        assert cfg.llm_turn_parallel_workers == 4

    def test_config_zero_0(self) -> None:
        """0 は明示的な serial 指定として受け付ける。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={"LLM_TURN_PARALLEL_WORKERS": "0"}
        )
        assert cfg.llm_turn_parallel_workers == 0

    def test_config_negative_raises_value_error(self) -> None:
        """負値は既定値縮退ではなく profile ミスとして止める。"""
        with pytest.raises(ValueError, match="LLM_TURN_PARALLEL_WORKERS"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"LLM_TURN_PARALLEL_WORKERS": "-3"}
            )

    def test_config_invalid_raises_value_error(self) -> None:
        """非整数も fail-fast する。"""
        with pytest.raises(ValueError, match="LLM_TURN_PARALLEL_WORKERS"):
            ResolvedLlmRuntimeConfig.from_mapping(
                values={"LLM_TURN_PARALLEL_WORKERS": "not-a-number"}
            )

    def test_meeting_serial_turns_are_disabled_by_default(self) -> None:
        """未設定なら会議も並列のままにし、逐次化は比較 run の明示条件にする。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(values={})
        assert cfg.llm_meeting_serial_turns is False

    def test_meeting_serial_turns_can_be_enabled_by_profile(self) -> None:
        """profile が true を宣言したときだけ会議の逐次化を有効にする。"""
        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values={"LLM_MEETING_SERIAL_TURNS": "true"}
        )
        assert cfg.llm_meeting_serial_turns is True


class TestPhaseAParallelExecution:
    """Phase A の LLM 呼び出しが ThreadPoolExecutor で並列化されること。

    Phase B (世界 mutation) も実行に時間がかかるため、E2E で run_scheduled_turns
    全体を見ると Phase B のシリアル処理で信号が薄まる。ここでは run_phase_a を
    4 並列で直接呼び、LLM stub 側の barrier を全員が通過できることを確認する。
    """

    def test_calls_four_run_phase_four_column(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """run phase a を 4 並列で呼ぶと LLM 呼び出しが実際に重なって走る。"""
        from concurrent.futures import ThreadPoolExecutor
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        class _BarrierStubLlmClient:
            """invoke に入った全 worker が barrier を通過したことを記録する stub。"""

            def __init__(self, expected_calls: int) -> None:
                self._barrier = threading.Barrier(expected_calls)
                self._lock = threading.Lock()
                self.passed_calls = 0

            def invoke(self, messages, tools, choice, *, metrics_sink=None, reasoning_effort=None, session_id=None) -> dict:
                self._barrier.wait(timeout=5.0)
                with self._lock:
                    self.passed_calls += 1
                return {"name": "wait", "arguments": {"reason": "test"}}

        state = create_world_runtime_session(monkeypatch, tmp_path, stub=None)
        wiring = state.llm_wiring
        player_ids = [
            PlayerId(int(sp.player_id))
            for sp in state.runtime.scenario.player_spawns
        ]
        # review MEDIUM 2 対策: 同 player_id 複数回 sample すると 2 回目以降は
        # buffer が空 / lazy init もキャッシュ済みで serial 時間が不公平に短く
        # 出る。両 path とも warm 状態で比較するよう、計測前に 1 回 prime する。
        sample = (player_ids * 4)[:4]
        for pid in set(sample):
            wiring.run_phase_a(pid)  # warm-up: drain buffer + lazy init

        llm_client = _BarrierStubLlmClient(expected_calls=len(sample))
        state.llm_wiring.llm_client = llm_client

        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(wiring.run_phase_a, sample))

        assert llm_client.passed_calls == len(sample)


class TestPhaseAExceptionHandling:
    """Phase A で LLM が例外を投げた場合、Phase B が LlmCommandResultDto 化する。"""

    def test_llm_api_failed_result_raises_exception(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """LLM 例外時は本人へ空白だけを返し、技術的原因を trace payload に残す。"""
        from tests.demos._world_runtime_helpers import create_world_runtime_session

        class _BoomLlmClient:
            def invoke(self, messages, tools, choice, *, metrics_sink=None, reasoning_effort=None, session_id=None) -> dict:
                raise RuntimeError("network down")

        state = create_world_runtime_session(monkeypatch, tmp_path, stub=None)
        state.llm_wiring.llm_client = _BoomLlmClient()
        player_id = PlayerId(
            int(state.runtime.scenario.player_spawns[0].player_id)
        )
        result = state.llm_wiring.run_turn(player_id)
        assert result.error_code == "LLM_API_FAILED"
        assert result.was_no_op is True
        assert result.message == "意識が途切れ、この間の自分の行動を思い出せない。"
        assert result.trace_payload == {"technical_error_detail": "network down"}
