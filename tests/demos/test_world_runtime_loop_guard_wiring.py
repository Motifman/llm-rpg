"""Issue #227 PR 4: tool_call_loop_guard を world_runtime に配線した動作確認 E2E。

第13/14回実験 (#223, #232) で観測されたカイトの ``spot_graph_wait`` 18-29 連発の
直接修正。PR #230 で ``ToolCallLoopGuardService`` を実装し
``LlmAgentOrchestrator.run_turn`` 経由で配線したが、world_runtime の
``_WorldLlmWiring.run_turn`` はそれを通らないため、loop guard が一切
発火しなかった (trace.jsonl に警告痕跡なし)。

本 PR で ``_WorldLlmWiring`` に ``ToolCallLoopGuardService`` を
組み込み、world_runtime 経路でも同一ツール連打を検知して警告観測を注入する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

from tests.demos._world_runtime_helpers import (
    create_world_runtime_session as _create_session,
)


def _wait_outputs_only(player_id: PlayerId, state) -> list:
    """player の observation buffer から loop_guard 警告だけを抽出する。"""
    entries = state.runtime._obs_buffer.get_observations(player_id)
    return [e for e in entries if e.output.structured.get("loop_guard") is True]


class TestWorldRuntimeLoopGuardWiring:
    """ToolCallLoopGuardService が world_runtime 経路でも動作する。"""

    def test_three_consecutive_waits_inject_loop_guard_warning(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """spot_graph_wait は threshold=3。3 回目で警告が出る。"""
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_wait",
                "arguments": {"reason": "考え中"},
            }
        )
        state = _create_session(monkeypatch, tmp_path, stub)
        target_pid = state.runtime.get_player_ids()[0]

        # 1 回目・2 回目では発火しない
        state.llm_wiring.run_turn(target_pid)
        state.llm_wiring.run_turn(target_pid)
        assert _wait_outputs_only(target_pid, state) == [], (
            "2 回連続では threshold=3 未満なので発火しないはず"
        )

        # 3 回目で発火
        state.llm_wiring.run_turn(target_pid)
        warnings = _wait_outputs_only(target_pid, state)
        assert len(warnings) == 1, (
            f"3 回目の wait で loop_guard 警告が 1 件出るはず. got={warnings}"
        )
        warning = warnings[0]
        assert warning.output.structured["tool_name"] == "spot_graph_wait"
        assert warning.output.structured["consecutive_count"] == 3
        # observation_category は self_only (該当プレイヤーだけに届く)
        assert warning.output.observation_category == "self_only"

    def test_travel_to_with_varying_arguments_does_not_trip_loop_guard(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """travel_to の threshold は 2 だが、引数が違えば fingerprint が違うので発火しない。

        正当な多段移動 (毎ターン違うスポットへ) では loop guard が誤検知しない。
        """
        # ターンごとに違う destination を返す stub
        calls = iter([
            {"name": "spot_graph_travel_to", "arguments": {"destination_label": "閲覧室"}},
            {"name": "spot_graph_travel_to", "arguments": {"destination_label": "入口広間"}},
            {"name": "spot_graph_travel_to", "arguments": {"destination_label": "カード目録室"}},
        ])

        class _MultiCallStub:
            def invoke(self, *_args, **_kwargs):
                return next(calls)

        state = _create_session(monkeypatch, tmp_path, _MultiCallStub())
        target_pid = state.runtime.get_player_ids()[0]
        for _ in range(3):
            state.llm_wiring.run_turn(target_pid)
        assert _wait_outputs_only(target_pid, state) == [], (
            "引数が違えば loop_guard は発火しないはず"
        )

    def test_two_consecutive_travel_to_same_destination_trips_loop_guard(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """travel_to の threshold=2。第13回のリン bouncing (同 destination 連打) を
        検知できることを確認する。
        """
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_travel_to",
                "arguments": {"destination_label": "S1"},
            }
        )
        state = _create_session(monkeypatch, tmp_path, stub)
        target_pid = state.runtime.get_player_ids()[0]
        for _ in range(2):
            state.llm_wiring.run_turn(target_pid)
        warnings = _wait_outputs_only(target_pid, state)
        assert len(warnings) == 1, (
            f"同一引数の travel_to を 2 回で警告が出るはず. got={warnings}"
        )
        assert warnings[0].output.structured["tool_name"] == "spot_graph_travel_to"
        assert warnings[0].output.structured["consecutive_count"] == 2

    def test_loop_guard_warning_is_self_only_and_does_not_leak_to_others(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """observation_category=self_only が守られている (forbidden_library_demo は
        2 プレイヤー)。"""
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_wait",
                "arguments": {"reason": "待機"},
            }
        )
        state = _create_session(monkeypatch, tmp_path, stub)
        ids = state.runtime.get_player_ids()
        assert len(ids) >= 2
        target_pid, other_pid = ids[0], ids[1]
        for _ in range(3):
            state.llm_wiring.run_turn(target_pid)
        assert len(_wait_outputs_only(target_pid, state)) >= 1
        assert _wait_outputs_only(other_pid, state) == [], (
            "loop_guard 警告は self_only。他プレイヤーには届かないはず"
        )
