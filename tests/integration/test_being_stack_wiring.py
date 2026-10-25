"""プレイヤーの Being を用意する処理と、記憶の道具の振り分けを保証する (#1631)。"""

from __future__ import annotations

from pathlib import Path

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_EPISODE_RECALL
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_SCENARIO = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "forbidden_library_demo.json"


class TestBeingStack:
    """Being の解決と記憶の道具の振り分けが、create_world_runtime の組んだ runtime で動くことを保証する。"""

    def test_acting_being_is_resolved_for_a_spawned_player(self) -> None:
        """起動時に配置したプレイヤーから、そのプレイヤーの Being を解決できる。"""
        runtime = create_world_runtime(_SCENARIO)
        player_id = runtime.get_player_ids()[0]

        acting = runtime._acting_being_for(player_id)

        assert acting is not None
        assert acting.being_id.value == f"being_w1_p{player_id.value}"

    def test_wiring_the_being_stack_again_keeps_the_same_beings(self) -> None:
        """Being の準備を何度呼んでも作り直さず、起動時に用意した Being を同じ解決器で引ける。"""
        runtime = create_world_runtime(_SCENARIO)
        resolver = runtime.aux_being_resolver
        player_id = runtime.get_player_ids()[0]
        before = resolver.resolve_being_id(runtime.aux_being_default_world_id, player_id)

        runtime._wire_being_stack()

        assert runtime.aux_being_resolver is resolver
        assert resolver.resolve_being_id(runtime.aux_being_default_world_id, player_id) == before

    def test_old_memo_tool_is_reported_as_unsupported_while_episode_recall_is_handled(self) -> None:
        """古いメモのツール名 memo_add を呼ぶと、止まらずに未対応のツールとして返す。同じ入口で episode_recall は扱われる。"""
        runtime = create_world_runtime(_SCENARIO)
        player_id = runtime.get_player_ids()[0]

        old_memo = runtime.run_llm_auxiliary_tool(player_id, "memo_add", {"content": "鍵を探す"})
        recall = runtime.run_llm_auxiliary_tool(player_id, TOOL_NAME_EPISODE_RECALL, {"handles": ["ep_000000"]})

        assert (old_memo.success, old_memo.error_code) == (False, "UNSUPPORTED_TOOL")
        assert recall.error_code != "UNSUPPORTED_TOOL"
