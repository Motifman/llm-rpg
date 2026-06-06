"""Phase A 並列化 (#346 Step 1) の挙動検証。

env LLM_TURN_PARALLEL_WORKERS が 0 / 未設定なら従来の serial 経路。
2 以上なら ThreadPoolExecutor で LLM 呼び出しを並列化する。

並列化後でも:
- Phase B (世界 mutation) は to_run 順に serial で適用される
- LLM 例外は Phase B で LlmCommandResultDto 化される
- 各 turn の result は同じ (parallelize は速度だけの最適化)
"""

from __future__ import annotations

from pathlib import Path
import time

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    _resolve_llm_parallel_workers,
    _LLM_PARALLEL_WORKERS_ENV,
)


SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "abandoned_hospital.json"
)


class TestResolveLlmParallelWorkers:
    """env の解釈が安全であること。"""

    def test_env_未設定なら_default_を返す(self, monkeypatch) -> None:
        monkeypatch.delenv(_LLM_PARALLEL_WORKERS_ENV, raising=False)
        assert _resolve_llm_parallel_workers(default=0) == 0
        assert _resolve_llm_parallel_workers(default=4) == 4

    def test_env_が_正の整数なら_その値(self, monkeypatch) -> None:
        monkeypatch.setenv(_LLM_PARALLEL_WORKERS_ENV, "4")
        assert _resolve_llm_parallel_workers() == 4

    def test_env_が_0_なら_0(self, monkeypatch) -> None:
        monkeypatch.setenv(_LLM_PARALLEL_WORKERS_ENV, "0")
        assert _resolve_llm_parallel_workers() == 0

    def test_env_が_負値_なら_0(self, monkeypatch) -> None:
        monkeypatch.setenv(_LLM_PARALLEL_WORKERS_ENV, "-3")
        assert _resolve_llm_parallel_workers() == 0

    def test_env_が_不正値なら_default(self, monkeypatch) -> None:
        monkeypatch.setenv(_LLM_PARALLEL_WORKERS_ENV, "not-a-number")
        assert _resolve_llm_parallel_workers(default=2) == 2


class TestPhaseAParallelExecution:
    """Phase A の LLM 呼び出しが ThreadPoolExecutor で並列化されること。

    Phase B (世界 mutation) も実行に時間がかかるため、E2E で run_scheduled_turns
    全体の wall time を測ると Phase B のシリアル時間で速度差が薄まる。ここでは
    run_phase_a を 4 並列で直接呼んで wall time を観察する (LLM 呼び出し自体の
    並列化を分離して計測)。
    """

    def test_run_phase_a_を_4_並列で呼ぶと_4倍速に近づく(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        from concurrent.futures import ThreadPoolExecutor
        from tests.demos._escape_game_helpers import create_escape_game_session

        class _SlowStubLlmClient:
            """各 invoke で 100ms スリープしてから wait を返す stub。"""

            def invoke(self, messages, tools, choice, *, metrics_sink=None) -> dict:
                time.sleep(0.1)
                return {"name": "spot_graph_wait", "arguments": {"reason": "test"}}

        state = create_escape_game_session(monkeypatch, tmp_path, stub=None)
        state.llm_wiring.llm_client = _SlowStubLlmClient()
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

        # serial: 4 連続呼び出し → ~400ms
        t0 = time.monotonic()
        for pid in sample:
            wiring.run_phase_a(pid)
        serial_elapsed = time.monotonic() - t0

        # parallel: ThreadPool で 4 並列 → ~100ms
        t0 = time.monotonic()
        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(wiring.run_phase_a, sample))
        parallel_elapsed = time.monotonic() - t0

        speedup = serial_elapsed / parallel_elapsed if parallel_elapsed > 0 else 0
        # review MEDIUM 2: CI runner が 1 vCPU の場合 thread scheduling overhead で
        # 2x 程度まで落ちることがある。理論値 4x の半分で十分 "parallel が
        # 効いている" を示せる閾値にする (regression detection が目的)。
        assert speedup >= 2.0, (
            f"Phase A parallelization speedup too low: "
            f"serial={serial_elapsed:.3f}s parallel={parallel_elapsed:.3f}s "
            f"speedup={speedup:.2f}x (expected >= 2x)"
        )


class TestPhaseAExceptionHandling:
    """Phase A で LLM が例外を投げた場合、Phase B が LlmCommandResultDto 化する。"""

    def test_LLM_例外時に_LLM_API_FAILED_result_が返る(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        from tests.demos._escape_game_helpers import create_escape_game_session

        class _BoomLlmClient:
            def invoke(self, messages, tools, choice, *, metrics_sink=None) -> dict:
                raise RuntimeError("network down")

        state = create_escape_game_session(monkeypatch, tmp_path, stub=None)
        state.llm_wiring.llm_client = _BoomLlmClient()
        player_id = PlayerId(
            int(state.runtime.scenario.player_spawns[0].player_id)
        )
        result = state.llm_wiring.run_turn(player_id)
        assert result.error_code == "LLM_API_FAILED"
        assert result.was_no_op is True
        assert "network down" in result.message
