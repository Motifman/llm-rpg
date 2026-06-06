"""#356 実験 #25 OFF で発覚した item tool resolver gap の regression 防止。

実験 trace 上で 164 件の INVALID_ARGUMENT が出ていた:
- use_item: 106 件全失敗 (LLM が `item_label: "I1"` を送るが executor は `item_spec_id` を読む)
- drop_item: 25 件失敗 (resolver dispatch にはあるが experiment wiring が呼ばない)
- give_item: 18 件失敗 (同上)
- pickup_item: 15 件失敗 (同上)

原因: `_EscapeGameLlmWiring._wire_missing_spot_graph_tools` が executor を
`_adapt_executor_handler` で直接ラップしていて、引数 resolver
(SpotGraphArgumentResolver) を経由していなかった。

本テストは:
1. resolver の `_resolve_use_item` が item_label → item_spec_id を返す
2. `_adapt_executor_handler_with_resolver` が resolver を呼んで executor に
   解決済み args を渡すこと
3. resolver 例外が LlmCommandResultDto に変換され、success=False で
   INVALID_TARGET_LABEL を返すこと
を保証する。
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    InventoryToolRuntimeTargetDto,
    LlmCommandResultDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    SpotGraphArgumentResolver,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    _EscapeGameLlmWiring,
)


def _inventory_target(
    label: str = "I1",
    item_spec_id: int = 42,
    slot_id: int = 7,
    instance_id: int = 100,
    display_name: str = "椰子の実",
) -> InventoryToolRuntimeTargetDto:
    return InventoryToolRuntimeTargetDto(
        label=label,
        kind="inventory_item",
        display_name=display_name,
        # legacy: use_item は item_instance_id フィールドに item_spec_id を入れる慣習
        item_instance_id=item_spec_id,
        real_item_instance_id=instance_id,
        inventory_slot_id=slot_id,
    )


def _runtime_context(targets: Dict[str, Any]) -> ToolRuntimeContextDto:
    return ToolRuntimeContextDto(targets=targets)


class TestResolveUseItem:
    """`SpotGraphArgumentResolver._resolve_use_item` の基本動作。"""

    def test_item_label_を_item_spec_id_に_変換(self) -> None:
        resolver = SpotGraphArgumentResolver()
        ctx = _runtime_context({"I1": _inventory_target(item_spec_id=42)})
        out = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_USE_ITEM,
            {"item_label": "I1", "inner_thought": "食べたい"},
            ctx,
        )
        assert out is not None
        assert out["item_spec_id"] == 42
        assert out["inner_thought"] == "食べたい"

    def test_item_label_が_空文字なら_INVALID_TARGET_LABEL_例外(self) -> None:
        resolver = SpotGraphArgumentResolver()
        ctx = _runtime_context({})
        with pytest.raises(ToolArgumentResolutionException) as ei:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_USE_ITEM, {"item_label": ""}, ctx,
            )
        assert ei.value.error_code == "INVALID_TARGET_LABEL"

    def test_存在しない_label_は_例外(self) -> None:
        resolver = SpotGraphArgumentResolver()
        ctx = _runtime_context({"I1": _inventory_target()})
        with pytest.raises(ToolArgumentResolutionException):
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_USE_ITEM, {"item_label": "I99"}, ctx,
            )

    def test_TOOL_NAME_SPOT_GRAPH_USE_ITEM_は_dispatch_対象(self) -> None:
        """resolver が use_item を None で素通りさせていた regression を防ぐ。"""
        from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
            _SPOT_GRAPH_TOOLS,
        )
        assert TOOL_NAME_SPOT_GRAPH_USE_ITEM in _SPOT_GRAPH_TOOLS


class TestAdapterWithResolver:
    """`_adapt_executor_handler_with_resolver` が resolver と executor を繋ぐ。"""

    def test_resolver_の_出力が_executor_に_渡る(self) -> None:
        seen_args: Dict[str, Any] = {}

        def fake_executor(pid_int: int, args: Dict[str, Any]) -> LlmCommandResultDto:
            seen_args.update(args)
            return LlmCommandResultDto(success=True, message="ok")

        resolver = MagicMock()
        resolver.resolve_args.return_value = {
            "item_spec_id": 42, "inner_thought": "ok",
        }
        handler = _EscapeGameLlmWiring._adapt_executor_handler_with_resolver(
            fake_executor, TOOL_NAME_SPOT_GRAPH_USE_ITEM, resolver,
        )
        result = handler(PlayerId(1), {"item_label": "I1"}, _runtime_context({}))
        assert result.success is True
        # resolver が canonical 引数に置き換えたものが exec に届く
        assert seen_args["item_spec_id"] == 42
        assert "item_label" not in seen_args

    def test_resolver_例外は_LlmCommandResultDto_に_変換(self) -> None:
        def fake_executor(pid_int: int, args: Dict[str, Any]) -> LlmCommandResultDto:
            pytest.fail("resolver 失敗時に executor が呼ばれてはいけない")

        resolver = MagicMock()
        resolver.resolve_args.side_effect = ToolArgumentResolutionException(
            "ラベルが見つかりません: I99", "INVALID_TARGET_LABEL",
        )
        handler = _EscapeGameLlmWiring._adapt_executor_handler_with_resolver(
            fake_executor, TOOL_NAME_SPOT_GRAPH_USE_ITEM, resolver,
        )
        result = handler(PlayerId(1), {"item_label": "I99"}, _runtime_context({}))
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        assert "I99" in result.message
        # remediation は LLM が次のターンで何をすべきか示唆する
        assert result.remediation
        assert "I1" in result.remediation or "ラベル" in result.remediation

    def test_resolver_が_None_を返したら_RESOLVER_DISPATCH_MISSING_を_返す(
        self,
    ) -> None:
        """resolver dispatch から外れている (設計違反) ケースは、raw args で
        executor に押し付けるのではなく、明示的な error_code で即 surface する
        (code-review HIGH 対応)。raw 渡しだと executor 内で KeyError 等に
        化けて発生源が分かりにくくなる。"""
        called = {"n": 0}

        def fake_executor(pid_int: int, args: Dict[str, Any]) -> LlmCommandResultDto:
            called["n"] += 1
            return LlmCommandResultDto(success=False, message="raw")

        resolver = MagicMock()
        resolver.resolve_args.return_value = None
        handler = _EscapeGameLlmWiring._adapt_executor_handler_with_resolver(
            fake_executor, "unknown_tool", resolver,
        )
        result = handler(PlayerId(1), {"item_label": "I1"}, _runtime_context({}))
        # executor は呼ばれない
        assert called["n"] == 0
        assert result.success is False
        assert result.error_code == "RESOLVER_DISPATCH_MISSING"
        assert "unknown_tool" in result.message


class TestDispatchTableUsesResolver:
    """dispatch table の item tool handler が実際に resolver を経由する。

    `_wire_missing_spot_graph_tools` が resolver-wrapped adapter を選んでいる
    ことを直接検証する (regression test)。
    """

    def test_全4_item_tool_に_resolver_aware_handler_が_登録(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """use/drop/give/pickup の handler が resolver を呼ぶ動作になっている。

        実体は `_adapt_executor_handler_with_resolver` の closure。closure 名を
        検査する代わりに、不正 label を送って INVALID_TARGET_LABEL が返ること
        (= resolver が動いた証拠) で確認する。
        """
        from tests.demos._escape_game_helpers import create_escape_game_session

        state = create_escape_game_session(monkeypatch, tmp_path)
        wiring = state.llm_wiring
        for tool_name in (
            TOOL_NAME_SPOT_GRAPH_USE_ITEM,
            TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
            TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
            TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
        ):
            handler = wiring._tool_handlers.get(tool_name)
            assert handler is not None, f"{tool_name} が dispatch table に無い"
            # 空 targets / 不正 label で呼ぶ → resolver が落ちて
            # INVALID_TARGET_LABEL 系の result_dto が返るはず。
            # 旧コードでは INVALID_ARGUMENT (= resolver を skip して executor が
            # 引数欠落で落ちる) になっていた。
            args = (
                {"ground_item_label": "G99", "inner_thought": "t"}
                if tool_name == TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM
                else {
                    "item_label": "I99",
                    "target_player_label": "P99",
                    "inner_thought": "t",
                }
            )
            ctx = _runtime_context({})
            result = handler(PlayerId(1), args, ctx)
            assert result.success is False
            # resolver 経由なら INVALID_TARGET_LABEL / INVALID_TARGET_KIND が返る
            # (executor 直叩きなら INVALID_ARGUMENT になっていた)
            assert result.error_code in (
                "INVALID_TARGET_LABEL",
                "INVALID_TARGET_KIND",
            ), (
                f"{tool_name}: resolver を経由していない (error_code="
                f"{result.error_code})。executor 直叩きの古い経路に戻った可能性。"
            )
