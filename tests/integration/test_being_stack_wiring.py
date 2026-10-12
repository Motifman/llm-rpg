"""プレイヤーの Being を用意する処理が、古いメモの実行器の準備に頼らないことを保証する (#1631)。"""

from __future__ import annotations

from pathlib import Path

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "forbidden_library_demo.json"
)


class TestBeingStackWithoutOldMemoExecutor:
    """Being の解決と補助ツールの振り分けが、古いメモの実行器が無くても動くことを保証する。"""

    def test_acting_being_is_resolved_without_building_the_old_memo_executor(self) -> None:
        """古いメモの実行器が無い runtime でも、プレイヤーから Being を解決でき、実行器は作られないまま残る。"""
        runtime = create_world_runtime(_SCENARIO)
        player_id = runtime.get_player_ids()[0]
        runtime._todo_tool_executor = None

        acting = runtime._acting_being_for(player_id)

        assert acting is not None
        assert acting.being_id.value == f"being_w1_p{player_id.value}"
        assert runtime._todo_tool_executor is None

    def test_wiring_the_being_stack_again_keeps_the_same_beings(self) -> None:
        """Being の準備を何度呼んでも作り直さず、起動時に用意した Being を同じ解決器で引ける。"""
        runtime = create_world_runtime(_SCENARIO)
        resolver = runtime.aux_being_resolver
        player_id = runtime.get_player_ids()[0]
        before = resolver.resolve_being_id(runtime.aux_being_default_world_id, player_id)

        runtime._wire_being_stack()
        runtime._wire_auxiliary_tool_stack()

        assert runtime.aux_being_resolver is resolver
        assert resolver.resolve_being_id(runtime.aux_being_default_world_id, player_id) == before

    def test_auxiliary_tool_without_old_memo_executor_reports_unsupported_tool(self) -> None:
        """古いメモの実行器を組まない runtime で古いメモのツールを呼ぶと、止まらずに未対応のツールとして返す。実行器があれば同じ呼び出しは通る。"""
        runtime = create_world_runtime(_SCENARIO)
        player_id = runtime.get_player_ids()[0]
        with_executor = runtime.run_llm_auxiliary_tool(
            player_id, "memo_add", {"content": "鍵を探す"}
        )
        runtime._todo_tool_executor = None
        runtime._wire_auxiliary_tool_stack = runtime._wire_being_stack  # type: ignore[method-assign]

        result = runtime.run_llm_auxiliary_tool(player_id, "memo_add", {"content": "鍵を探す"})

        assert with_executor.success
        assert (result.success, result.error_code) == (False, "UNSUPPORTED_TOOL")
