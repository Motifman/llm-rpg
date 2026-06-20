"""Issue #227 PR 3: travel_to の display_name fallback を world_runtime 経路でも有効化する E2E テスト。

第13/14回実験で観測されたリンの「閲覧室 ↔ 入口広間」bouncing は、LLM が
過去 turn の tool_call 履歴に残った ``destination_label="S1"`` を再使用
した結果だった。S1 は「現在地から見た first neighbor」を指す相対ラベル
なので、自スポットが変わると逆方向を指してしまう。

PR #229 で本家経路 (LlmAgentOrchestrator → spot_graph_resolver) に
display_name (= スポット名) fallback を追加したが、world_runtime runtime は
独自に ``_execute_tool`` で直接 label lookup していたため、その修正は
world_runtime 経路では効いていなかった。

本 PR 3 で world_runtime の ``_execute_tool`` にも同等の fallback を追加し、
LLM が ``destination_label="閲覧室"`` のような不変な名前を渡しても spot_id
に解決できるようにする。
"""

from __future__ import annotations

from pathlib import Path

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    GameRuntimeManager,
)
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _create_forbidden_library_session(monkeypatch, tmp_path: Path, stub: StubLlmClient):
    """forbidden_library_demo シナリオでセッションを立ち上げる。"""
    monkeypatch.setenv("SPOT_GRAPH_TICK_LOOP_ENABLED", "false")
    chars = tmp_path / "characters.json"
    mgr = GameRuntimeManager(
        scenarios_dir=_REPO_ROOT / "data" / "scenarios",
        characters_path=chars,
    )
    char = mgr.create_character(CharacterCreateRequest(name="カイト"))
    summary = mgr.create_session(
        SessionCreateRequest(world_id="forbidden_library_demo", character_ids=[char.id])
    )
    state = mgr._sessions[summary.session_id]
    state.llm_wiring.llm_client = stub
    return state


class TestWorldRuntimeTravelBySpotName:
    """destination_label にスポット名を渡しても解決される (PR 3)。"""

    def test_destination_label_accepts_spot_display_name(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """旧 world_runtime では label lookup のみで失敗していた。PR 3 で
        display_name fallback が追加され、スポット名指定で移動できる。"""
        # forbidden_library_demo: カイトの spawn は入口広間 (1)。閲覧室 (2) は
        # 隣接スポットの 1 つ。
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_travel_to",
                "arguments": {"destination_label": "閲覧室"},
            }
        )
        state = _create_forbidden_library_session(monkeypatch, tmp_path, stub)
        target_pid = state.runtime.get_player_ids()[0]
        result = state.llm_wiring.run_turn(target_pid)

        assert result.success is True, (
            f"BUG: スポット名 '閲覧室' で移動できなかった: {result.message}"
        )
        assert "閲覧室" in result.message

    def test_dynamic_label_s1_still_works_after_fallback_added(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """display_name fallback 追加後も既存のラベル指定パスは動く (回帰確認)。"""
        # 入口広間からの隣接スポットの先頭 (S1) を指定する
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_travel_to",
                "arguments": {"destination_label": "S1"},
            }
        )
        state = _create_forbidden_library_session(monkeypatch, tmp_path, stub)
        target_pid = state.runtime.get_player_ids()[0]
        result = state.llm_wiring.run_turn(target_pid)

        assert result.success is True, (
            f"BUG: 既存のラベル指定が動かなくなった: {result.message}"
        )

    def test_unknown_destination_returns_learnable_failure_dto(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """ラベルにも display_name にもマッチしなければ INVALID_DESTINATION_LABEL
        を返し、有効候補を message に列挙する (F1 学習可能性)。"""
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_travel_to",
                "arguments": {"destination_label": "存在しない神秘の部屋"},
            }
        )
        state = _create_forbidden_library_session(monkeypatch, tmp_path, stub)
        target_pid = state.runtime.get_player_ids()[0]
        result = state.llm_wiring.run_turn(target_pid)

        assert result.success is False
        assert result.error_code == "INVALID_DESTINATION_LABEL"
        # 有効候補が message に並ぶ
        assert "S1" in result.message
        assert result.remediation is not None
        # 新 remediation はラベル or スポット名どちらでも OK と案内する
        assert "スポット名" in result.remediation
