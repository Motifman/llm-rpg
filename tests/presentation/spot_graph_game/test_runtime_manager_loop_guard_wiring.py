"""PR-AA (Y_after_pr639_640 後続、code-review HIGH 反映): wiring レベルの
配線テスト。run_phase_b から ``ToolCallLoopGuardService.record_and_check``
に ``success`` / ``error_code`` が forward されていることを検証する。

review 指摘の要旨:
- ``record_and_check`` の新 kwargs は loop_guard 側の単体テストで動作確認済
- **実際の呼び出し側 (wiring 層) が新 kwargs を渡しているか未検証**
- 誰かが「未使用 kwargs」だと lint で削除する regression を防ぐには wiring 経由の
  テストが必要

本テストは既存の ``_ContractRuntime`` テスト基盤を流用し、失敗する tool
handler を注入して ``run_phase_b`` を実行、spy が受け取った kwargs に
``success=False`` と ``error_code=<code>`` が入っていることを assert する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


@pytest.fixture
def clean_runtime_env(monkeypatch):
    # 既存 contract test と同じ env clean を実施 (env leak を防ぐ)
    monkeypatch.delenv("LLM_EPISODIC_ENABLED", raising=False)
    yield


def test_run_phase_b_forwards_success_and_error_code_on_failure(
    clean_runtime_env,
) -> None:
    """失敗 tool 実行後、``loop_guard.record_and_check`` に
    ``success=False`` と ``error_code=<code>`` が forward される。

    PR-AA の新 kwargs を「誰かが未使用として削除する」regression の防波堤。
    """
    # 既存 contract test 基盤を借りる
    from tests.integration.test_world_runtime_current_runtime_contract import (
        _ContractRuntime,
        _LoopGuardSpy,
        _phase_a,
        _wiring_for_contract_runtime,
    )

    player_id = PlayerId(1)
    events: list[str] = []
    runtime = _ContractRuntime(events)
    wiring = _wiring_for_contract_runtime(runtime)
    spy = _LoopGuardSpy(events)
    wiring.tool_call_loop_guard = spy

    # 明示的に失敗を返す handler を注入
    def _failing_handler(pid, args, ctx):
        return LlmCommandResultDto(
            success=False,
            message="failure test",
            error_code="INTERACTION_PRECONDITION_FAILED",
        )

    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = _failing_handler

    result = wiring.run_phase_b(
        _phase_a(
            player_id,
            tool_call={
                "name": TOOL_NAME_SPOT_GRAPH_EXPLORE,
                "arguments": {"inner_thought": "..."},
            },
        )
    )

    # sanity: 失敗結果が返っている
    assert result.success is False
    assert result.error_code == "INTERACTION_PRECONDITION_FAILED"

    # 配線検証: spy が record_and_check を呼ばれ、かつ kwargs に
    # success/error_code が渡っている
    assert spy.calls, "loop_guard.record_and_check が呼ばれていない"
    assert spy.last_kwargs.get("success") is False, (
        f"success=False が forward されていない: {spy.last_kwargs}"
    )
    assert (
        spy.last_kwargs.get("error_code") == "INTERACTION_PRECONDITION_FAILED"
    ), f"error_code が forward されていない: {spy.last_kwargs}"


def test_run_phase_b_forwards_success_True_on_success(
    clean_runtime_env,
) -> None:
    """成功時も ``success=True`` が forward されている (cross_tick 側で
    「成功だから failure history には積まない」判定に必要)。"""
    from tests.integration.test_world_runtime_current_runtime_contract import (
        _ContractRuntime,
        _LoopGuardSpy,
        _phase_a,
        _wiring_for_contract_runtime,
    )

    player_id = PlayerId(1)
    events: list[str] = []
    runtime = _ContractRuntime(events)
    wiring = _wiring_for_contract_runtime(runtime)
    spy = _LoopGuardSpy(events)
    wiring.tool_call_loop_guard = spy

    def _success_handler(pid, args, ctx):
        return LlmCommandResultDto(success=True, message="OK")

    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = _success_handler

    result = wiring.run_phase_b(
        _phase_a(
            player_id,
            tool_call={
                "name": TOOL_NAME_SPOT_GRAPH_EXPLORE,
                "arguments": {"inner_thought": "..."},
            },
        )
    )

    assert result.success is True
    assert spy.calls
    assert spy.last_kwargs.get("success") is True
    # 成功時は error_code が None (LlmCommandResultDto.error_code の default)
    assert spy.last_kwargs.get("error_code") is None
