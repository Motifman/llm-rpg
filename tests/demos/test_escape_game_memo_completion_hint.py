"""Issue #227 PR 5: MemoCompletionHintService を escape_game に配線した動作確認 E2E。

LLM が memo_done を呼ばずに memo を放置するケースを救済するため、
action_summary / result_summary と未完了 memo の content を SequenceMatcher
で比較し、類似度が高ければ result.message に「memo を完了したかも」hint を
append する機能。

本家経路 (LlmAgentOrchestrator) では PR #230 と並行して既に配線済みだったが、
escape_game の独自 turn 実行は経由しないため hint が一切出ていなかった。
PR 5 で escape_game の _EscapeGameLlmWiring に配線。

PR 5 のスコープ: MemoCompletionHintService のみ。
EpisodicChunkCoordinator / EpisodicReinterpretationCoordinator は依存関係が
複雑 (LLM completion ports, recall buffer store, journal store 等) で、
PR 7 (経路統一) で本家 wiring 経由に切り替えた際に自動的に配線される
ため本 PR では deferred とする。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    GameRuntimeManager,
)
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _create_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stub: StubLlmClient,
    world_id: str = "forbidden_library_demo",
):
    monkeypatch.setenv("SPOT_GRAPH_TICK_LOOP_ENABLED", "false")
    mgr = GameRuntimeManager(
        scenarios_dir=_REPO_ROOT / "data" / "scenarios",
        characters_path=tmp_path / "characters.json",
    )
    char = mgr.create_character(CharacterCreateRequest(name="カイト"))
    summary = mgr.create_session(
        SessionCreateRequest(world_id=world_id, character_ids=[char.id])
    )
    state = mgr._sessions[summary.session_id]
    state.llm_wiring.llm_client = stub
    return state


class TestEscapeGameMemoCompletionHint:
    """memo の内容が action/result と類似していたら hint が出る。"""

    def test_未完了_memo_の内容が_action_に強く現れたら_result_に_hint_が_append_される(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """memo に「閲覧室へ移動」と書いた後、travel_to 閲覧室 を実行すると、
        result.message に hint テキスト「memo ... を達成した可能性」が追記される。
        """
        # まず memo_add で「閲覧室へ移動」を登録する (短く類似度が高くなるよう抑えた)
        stub_add = StubLlmClient(
            tool_call_to_return={
                "name": "memo_add",
                "arguments": {"content": "閲覧室へ移動する"},
            }
        )
        state = _create_session(monkeypatch, tmp_path, stub_add)
        kaito = state.runtime.get_player_ids()[0]
        result_add = state.llm_wiring.run_turn(kaito)
        assert result_add.success is True
        # 次に閲覧室 (spawn の隣接スポット) へ travel_to する
        state.llm_wiring.llm_client = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_travel_to",
                "arguments": {"destination_label": "閲覧室"},
            }
        )
        result_travel = state.llm_wiring.run_turn(kaito)
        # hint が追記されていれば成功
        assert result_travel.success is True
        assert "[hint]" in result_travel.message or "memo" in result_travel.message, (
            f"BUG: memo hint が result.message に追記されていない: {result_travel.message!r}"
        )
        assert "閲覧室" in result_travel.message

    def test_memo_add_直後は_hint_が出ない_冗長抑止(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """memo_add の結果に対しては hint を出さない (memo_* ツール自身は除外)。
        本家経路と同じ動作を保証する。"""
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "memo_add",
                "arguments": {"content": "memo を追加するだけ"},
            }
        )
        state = _create_session(monkeypatch, tmp_path, stub)
        kaito = state.runtime.get_player_ids()[0]
        result = state.llm_wiring.run_turn(kaito)
        assert result.success is True
        assert "[hint]" not in result.message, (
            f"BUG: memo_add の結果に hint が追加されている: {result.message!r}"
        )

    def test_類似性が低い_memo_には_hint_が出ない_誤検知抑止(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """memo の内容と全く無関係な action では hint が出ない。"""
        stub_add = StubLlmClient(
            tool_call_to_return={
                "name": "memo_add",
                "arguments": {"content": "クライス・フィンの暗号を覚える"},
            }
        )
        state = _create_session(monkeypatch, tmp_path, stub_add)
        kaito = state.runtime.get_player_ids()[0]
        state.llm_wiring.run_turn(kaito)
        # 全く別のスポットへ移動
        state.llm_wiring.llm_client = StubLlmClient(
            tool_call_to_return={
                "name": "spot_graph_travel_to",
                "arguments": {"destination_label": "閲覧室"},
            }
        )
        result_travel = state.llm_wiring.run_turn(kaito)
        assert result_travel.success is True
        assert "クライス・フィン" not in result_travel.message
        # hint 文字列が message に紛れていないこと
        assert "[hint]" not in result_travel.message
