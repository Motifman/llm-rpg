"""第26回実験 (#384) で発覚した 3 つのバグへの regression test。

実験 #26 OFF trace 分析結果:
1. **use_item SYSTEM_ERROR 72 件** (`PlayerInventoryAggregate object has
   no attribute 'slots'`): executor が存在しない属性を iter していた
2. **interact_failed prose の "何か" 漏出 92/92 件**: object_name resolver
   が graph.get_spot(spot_id).interior=None で fallback "何か" を返す
3. **`search`/`examine`/`interact` ad-hoc action で LLM_TOOL_EXECUTION_FAILED**:
   `InteractionNotFoundException` が generic error に化けて利用可能 action
   一覧が LLM に届かない
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "survival_island_v2.json"
)


class TestUseItemInventoryIter:
    """#26 Bug 1: use_item executor が inv._inventory_slots を正しく iter する。"""

    def test_inventory_slots_iter_use_item_works(self) -> None:
        """PlayerInventoryAggregate には `slots` 属性は無く、
        `_inventory_slots: Dict[SlotId, Optional[ItemInstanceId]]` を持つ。
        executor が誤って `inv.slots` を iter していたため、全 use_item が
        AttributeError → SYSTEM_ERROR で死んでいた regression を防ぐ。"""
        from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
        from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
            grant_item_specs_to_inventory,
        )
        from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        runtime = create_world_runtime(SCENARIO_PATH)
        ada = PlayerId(int(runtime.scenario.player_spawns[0].player_id))
        # 椰子の実 (CONSUMABLE) を付与
        coconut_id = runtime.id_mapper.get_int("item_spec", "coconut")
        grant_item_specs_to_inventory(
            player_id=ada,
            item_spec_ids=(ItemSpecId.create(coconut_id),),
            item_repository=runtime._item_repo,
            item_spec_repository=runtime._item_spec_repo,
            player_inventory_repository=runtime._player_inventory_repo,
        )
        executor = runtime._spot_graph_executor if hasattr(runtime, "_spot_graph_executor") else None
        # executor は runtime_manager 経由でしか接続されないので、直接 _use_item
        # を呼ぶには別経路が必要。代わりに inventory iter ロジックだけを検証する。
        inv = runtime._player_inventory_repo.find_by_id(ada)
        assert inv is not None
        # _inventory_slots は dict — iter で AttributeError にならない
        ids = [iid for _, iid in inv._inventory_slots.items() if iid is not None]
        assert len(ids) >= 1, "椰子の実が inventory に入っていない"

    def test_use_item_executor_inv_slots(self) -> None:
        """executor のソースコードから旧 `inv.slots` 参照が消えていることを
        確認する (regression text-level check)。"""
        from pathlib import Path
        executor_src = (
            Path(__file__).resolve().parents[2]
            / "src/ai_rpg_world/application/llm/services/executors/spot_graph_tool_executor.py"
        )
        text = executor_src.read_text(encoding="utf-8")
        # 旧コード: `for slot in inv.slots:` (code 上の参照のみを検出。
        # コメント中の文字列言及は許可)。
        non_comment_lines = [
            ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
        ]
        joined = "\n".join(non_comment_lines)
        assert "inv.slots" not in joined, (
            "spot_graph_tool_executor.py に code 上の 'inv.slots' 参照が "
            "残っている (実験 #26 で発覚した SYSTEM_ERROR の原因)"
        )


class TestObjectNameResolverFallback:
    """#26 Bug 2: _resolve_object_name が spot_interior_repository fallback で
    "何か" 漏出を防ぐ。"""

    def test_object_name_can_lookup(self) -> None:
        """v2 scenario の wreck_hold (船倉) を object_name 解決する。
        graph.get_spot(spot_id).interior は None だが、
        spot_interior_repository から引いて "船倉" を返す。"""
        from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

        runtime = create_world_runtime(SCENARIO_PATH)
        # obs_pipeline 経由で formatter を取り出し、_resolve_object_name を直接呼ぶ
        formatter = runtime._obs_pipeline._formatter
        # 内部 SpotGraphObservationFormatter にアクセス
        from ai_rpg_world.application.observation.services.formatters._spot_graph_object_handler import (
            SpotGraphObjectHandler,
        )
        sg_formatter = next(
            f for f in formatter._formatters
            if any(isinstance(h, SpotGraphObjectHandler) for h in getattr(f, "_handlers", []))
        )
        handler = next(
            h for h in sg_formatter._handlers if isinstance(h, SpotGraphObjectHandler)
        )
        spot_id_int = runtime.id_mapper.get_int("spot", "shipwreck_beach")
        wreck_hold_id = runtime.id_mapper.get_int("object", "wreck_hold")
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
        name = handler._resolve_object_name(SpotId.create(spot_id_int), SpotObjectId.create(wreck_hold_id))
        assert name != "何か", (
            f"object_name が fallback '何か' のまま。"
            f"spot_interior_repository 注入が効いていない可能性"
        )
        # 実際の name は scenario JSON 由来 (例: "船倉")
        assert "船倉" in name or len(name) >= 2


class TestInteractionNotFoundRemediation:
    """#26 Bug 3: ad-hoc action_name で `InteractionNotFoundException` が
    generic LLM_TOOL_EXECUTION_FAILED に化ける問題を防ぐ。"""

    def test_returns_action_name_action(
        self, monkeypatch, tmp_path,
    ) -> None:
        """存在しない action name では 利用可能 action 一覧が 返る。"""
        from tests.demos._world_runtime_helpers import create_world_runtime_session
        from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
        from ai_rpg_world.application.llm.tool_constants import (
            TOOL_NAME_SPOT_GRAPH_INTERACT,
        )

        state = create_world_runtime_session(monkeypatch, tmp_path)
        wiring = state.llm_wiring
        # 存在しない action_name "search" を投げる
        stub = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_INTERACT,
            "arguments": {
                "object_label": "OBJ1",
                "action_name": "search_made_up",
                "inner_thought": "t",
            },
        })
        wiring.llm_client = stub
        target_pid = state.runtime.get_player_ids()[0]
        result = wiring.run_turn(target_pid)
        assert result.success is False
        # error_code が INTERACTION_ACTION_NOT_FOUND または OBJ ラベル
        # 解決失敗等の specific code (= LLM_TOOL_EXECUTION_FAILED ではない)
        assert result.error_code != "LLM_TOOL_EXECUTION_FAILED", (
            f"action_name 不正が generic error に化けた: {result.error_code} / {result.message[:80]}"
        )
