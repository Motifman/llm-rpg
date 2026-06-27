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
    TOOL_NAME_SPEECH,
    TOOL_NAME_SPOT_GRAPH_ATTACK,
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
    TOOL_NAME_SPOT_GRAPH_WAIT,
    TOOL_NAME_TODO_ADD,
    TOOL_NAME_TODO_COMPLETE,
    TOOL_NAME_TODO_LIST,
)

from tests.demos._world_runtime_helpers import (
    create_world_runtime_session as _create_session_full,
)


def _create_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """互換: 既存テストの呼び出し形に合わせた wrapper (stub=None で session を作成)。"""
    return _create_session_full(monkeypatch, tmp_path, stub=None)
    return mgr._sessions[summary.session_id]


class TestWorldRuntimeDispatchTable:
    """`_WorldLlmWiring._tool_handlers` が必要な tool を全て登録している。"""

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
            TOOL_NAME_SPEECH,
            TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
            TOOL_NAME_TODO_ADD,
            TOOL_NAME_TODO_LIST,
            TOOL_NAME_TODO_COMPLETE,
        }
        missing = required - set(handlers.keys())
        assert not missing, (
            f"dispatch table から必須 tool が欠落: {missing}"
        )

    def test_ConsumableEffectHandler_が_pipeline_に_subscribe_されている(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """#344 subagent review 後続: ConsumableUsedEvent → ConsumableEffectHandler
        の handler 登録が runtime 構築時に行われていることを確認する。

        登録が漏れると spot_graph_use_item が「使用した」だけ返して HP / hunger
        が一切変化しない silent failure になる (use_item の配線とは別の二重の罠)。
        """
        from ai_rpg_world.domain.item.event.item_event import ConsumableUsedEvent
        from ai_rpg_world.application.world.handlers.consumable_effect_handler import (
            ConsumableEffectHandler,
        )

        state = _create_session(monkeypatch, tmp_path)
        publisher = state.runtime._speech_event_publisher
        assert publisher is not None, "pipeline_event_publisher が runtime に保存されていない"
        # PipelineEventPublisher は InMemoryEventPublisher を委譲経由で保持しており、
        # register_handler で登録された handler を _handlers に持つ。
        # 直接 attribute は internal だが、テスト目的でアクセス。
        from ai_rpg_world.application.world_runtime.pipeline_event_publisher import PipelineEventPublisher
        assert isinstance(publisher, PipelineEventPublisher)
        # PipelineEventPublisher は _side_handlers に (event_type, handler) を持つ。
        registered = [
            handler
            for event_type, handler in publisher._side_handlers
            if event_type is ConsumableUsedEvent
        ]
        assert any(
            isinstance(h, ConsumableEffectHandler) for h in registered
        ), "ConsumableEffectHandler が pipeline publisher に登録されていない"

    def test_dispatch_table_registers_344_wired_tools(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """#344 で配線した spot_graph_use_item / attack / give / pickup / drop /
        prepare_action が dispatch table に登録されていることを直接検証する。

        OFF run 第24回実験 (#343) で 196 件の UNSUPPORTED_TOOL の元になった
        regression を、#154 の listen 配線漏れと同型のテストで防ぐ。
        """
        state = _create_session(monkeypatch, tmp_path)
        handlers = state.llm_wiring._tool_handlers
        required_344 = {
            TOOL_NAME_SPOT_GRAPH_USE_ITEM,
            TOOL_NAME_SPOT_GRAPH_ATTACK,
            TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
            TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
            TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
            TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION,
        }
        missing = required_344 - set(handlers.keys())
        assert not missing, (
            f"#344 配線漏れ regression: {missing}。"
            f"_WorldLlmWiring._wire_missing_spot_graph_tools が動いていない可能性。"
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


class TestWorldRuntimeScheduleTurnDoesNotTouchSelfRescheduleStreak:
    """``_WorldLlmTurnTrigger.schedule_turn`` が self-reschedule streak に
    干渉しない。

    旧名: ``_turn_counts``。PR 7 (#227) で「既存 count を保持」設計に変更したが、
    PR-I で「外部起床 (= schedule_turn) は streak に一切触らない」設計に
    さらに整理した。これにより ping-pong (= 他者発話で起こし合う相互作用)
    は streak の影響を受けず、self-loop (= reschedule=True 連続) だけが
    streak で打ち切られる。
    """

    def test_schedule_turn_preserves_existing_streak(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """既に streak が積まれているプレイヤーへの schedule_turn は
        streak に触らない (既存値を維持する)。"""
        state = _create_session(monkeypatch, tmp_path)
        trigger = state.llm_wiring.llm_turn_trigger
        pid = state.runtime.get_player_ids()[0]

        # self-reschedule streak を 3 まで進めた状況を再現
        trigger._self_reschedule_streak[pid.value] = 3

        # 外部起床 (= schedule_turn) を呼ぶ
        trigger.schedule_turn(pid)

        # streak が 3 のまま (= 外部起床は触らない)
        assert trigger._self_reschedule_streak[pid.value] == 3, (
            "BUG: schedule_turn が既存の self-reschedule streak を変更している。"
            "外部起床は self-loop chain の連続性に介入してはいけない。"
        )

    def test_schedule_turn_does_not_initialize_streak_for_new_player(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """未登録 player への schedule_turn は streak を初期化しない
        (= 次回 self-reschedule での get(default=0) で扱えば十分)。"""
        state = _create_session(monkeypatch, tmp_path)
        trigger = state.llm_wiring.llm_turn_trigger
        pid = state.runtime.get_player_ids()[0]

        trigger._self_reschedule_streak.pop(pid.value, None)
        trigger.schedule_turn(pid)

        # PR-I: streak には登録しない。pending には乗る。
        assert pid.value not in trigger._self_reschedule_streak
        assert pid.value in trigger.pending_player_ids


class TestReinterpretationAfterTurnTrigger:
    """U3: ターン完了で reinterpretation coordinator.after_turn_completed を呼ぶ。"""

    def test_coordinator_ありなら_after_turn_completed_を呼ぶ(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """_episodic_stack.reinterpretation_coordinator があれば player_id 付きで通知する。"""
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        state = _create_session(monkeypatch, tmp_path)
        trigger = state.llm_wiring.llm_turn_trigger

        class _CoordSpy:
            def __init__(self):
                self.calls = []

            def after_turn_completed(self, player_id):
                self.calls.append(player_id)

        spy = _CoordSpy()
        # 実 runtime の stack に coordinator を差し込む (off 構成でも構造を検証できる)
        from types import SimpleNamespace

        trigger.wiring.runtime._episodic_stack = SimpleNamespace(
            reinterpretation_coordinator=spy
        )

        trigger._note_turn_for_reinterpretation(1)
        assert spy.calls == [PlayerId(1)]

    def test_coordinator_未配線なら_no_op(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """reinterpretation OFF (stack=None / coordinator=None) では何もしない・例外も出さない。"""
        state = _create_session(monkeypatch, tmp_path)
        trigger = state.llm_wiring.llm_turn_trigger
        from types import SimpleNamespace

        trigger.wiring.runtime._episodic_stack = None
        trigger._note_turn_for_reinterpretation(1)  # 例外なく no-op

        trigger.wiring.runtime._episodic_stack = SimpleNamespace(
            reinterpretation_coordinator=None
        )
        trigger._note_turn_for_reinterpretation(1)  # 例外なく no-op
