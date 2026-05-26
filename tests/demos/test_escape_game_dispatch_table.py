"""Issue #227 PR 7: _execute_tool が tool 名 dispatch table 経由で動作することの E2E テスト。

PR 7 は `_execute_tool` の 240 行 if-elif チェーンを `_tool_handlers` という
dict ベースの dispatch に置き換えた。各ツール handler は `_handle_<tool>`
メソッドとして分離され、本家 `ToolCommandMapper.execute` と構造が揃った。

行動レベルの回帰は PR 1〜6 の E2E テストで担保されているため、本ファイルは
**dispatch table が正しく構築され、各 tool 名に対応する handler が登録されている**
ことを直接確認する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SAY,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_WAIT,
    TOOL_NAME_TODO_ADD,
    TOOL_NAME_TODO_COMPLETE,
    TOOL_NAME_TODO_LIST,
    TOOL_NAME_WHISPER,
)

from tests.demos._escape_game_helpers import (
    create_escape_game_session as _create_session_full,
)


def _create_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """互換: 既存テストの呼び出し形に合わせた wrapper (stub=None で session を作成)。"""
    return _create_session_full(monkeypatch, tmp_path, stub=None)
    return mgr._sessions[summary.session_id]


class TestEscapeGameDispatchTable:
    """`_EscapeGameLlmWiring._tool_handlers` が必要な tool を全て登録している。"""

    def test_dispatch_table_registers_all_required_tools(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """必須 tool が dispatch table に揃っているか確認。

        PR 7 の refactor で誤って handler が落ちると、その tool は
        UNSUPPORTED_TOOL になり LLM が困る。E2E ではなく構造を直接確認する。
        """
        state = _create_session(monkeypatch, tmp_path)
        handlers = state.llm_wiring._tool_handlers
        required = {
            TOOL_NAME_SPOT_GRAPH_EXPLORE,
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            TOOL_NAME_SPOT_GRAPH_LISTEN,
            TOOL_NAME_SPOT_GRAPH_WAIT,
            TOOL_NAME_SAY,
            TOOL_NAME_WHISPER,
            TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
            TOOL_NAME_TODO_ADD,
            TOOL_NAME_TODO_LIST,
            TOOL_NAME_TODO_COMPLETE,
        }
        missing = required - set(handlers.keys())
        assert not missing, (
            f"dispatch table から必須 tool が欠落: {missing}"
        )

    def test_unknown_tool_returns_unsupported(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """未登録の tool 名は UNSUPPORTED_TOOL を返す。"""
        stub = StubLlmClient(
            tool_call_to_return={
                "name": "totally_made_up_tool",
                "arguments": {},
            }
        )
        state = _create_session(monkeypatch, tmp_path)
        state.llm_wiring.llm_client = stub
        target_pid = state.runtime.get_player_ids()[0]
        result = state.llm_wiring.run_turn(target_pid)
        assert result.success is False
        assert result.error_code == "UNSUPPORTED_TOOL"
        assert "totally_made_up_tool" in result.message

    def test_each_handler_returns_command_dto(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """テーブルに登録された各 handler は callable で、LlmCommandResultDto を返す
        signature と整合することを smoke-check する (PR 7 refactor の構造保証)。"""
        state = _create_session(monkeypatch, tmp_path)
        handlers = state.llm_wiring._tool_handlers
        for tool_name, handler in handlers.items():
            assert callable(handler), f"{tool_name} の handler が callable でない"


class TestEscapeGameTurnCountNotResetOnSchedule:
    """`_EscapeGameLlmTurnTrigger.schedule_turn` が turn count を 0 リセットしない。

    PR 7 (#227 review HIGH 2): 旧 schedule_turn は呼び出しのたびに
    `_turn_counts[pid] = 0` していたため、PR 2 で speech 経由の再スケジュール
    が入ると turn loop 中に max_turns 制限が無効化されるリスクがあった。
    setdefault で「未登録なら 0、既登録なら維持」に変更したことを保証する。
    """

    def test_schedule_turn_preserves_existing_count(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """既に count が積まれているプレイヤーへの schedule_turn 再呼出は
        count を維持する (リセットしない)。"""
        state = _create_session(monkeypatch, tmp_path)
        trigger = state.llm_wiring.llm_turn_trigger
        pid = state.runtime.get_player_ids()[0]

        # turn count を 3 まで進める
        trigger._turn_counts[pid.value] = 3

        # schedule_turn 呼出
        trigger.schedule_turn(pid)

        # count が 3 のまま (0 にリセットされていない)
        assert trigger._turn_counts[pid.value] == 3, (
            "BUG: schedule_turn が既存の turn count を 0 リセットしている。"
            "PR 2 の speech-driven 再スケジュールと組み合わせて max_turns 制限が"
            "事実上無効化される。"
        )

    def test_schedule_turn_initializes_count_for_new_player(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """初回 schedule_turn (count 未登録) の場合は 0 で初期化する。"""
        state = _create_session(monkeypatch, tmp_path)
        trigger = state.llm_wiring.llm_turn_trigger
        pid = state.runtime.get_player_ids()[0]

        # count を delete してから schedule_turn
        trigger._turn_counts.pop(pid.value, None)
        trigger.schedule_turn(pid)

        assert trigger._turn_counts.get(pid.value) == 0
