"""
tool spec ↔ _tool_handlers の整合性検証ユーティリティの単体テスト。

過去 PR #589 / #590 で「tool spec が expose されているのに dispatch SSOT 側に
handler 未登録」という silent failure が 2 段階で発生した。本ユーティリティは
そのギャップを起動時に検出するためのもの。
"""

import pytest

from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    validate_tool_handler_consistency,
    ToolHandlerConsistencyError,
)


class TestValidateToolHandlerConsistency:
    """validate_tool_handler_consistency が spec ⊆ handler を保証する挙動。"""

    def test_raises_when_exposed_tool_has_no_handler(self):
        """spec に出ているのに _tool_handlers に無い tool があると、
        ToolHandlerConsistencyError を投げる。"""
        with pytest.raises(ToolHandlerConsistencyError):
            validate_tool_handler_consistency(
                exposed_tool_names=["spot_graph_travel_to", "memory_recall_by_handle"],
                handler_keys=["spot_graph_travel_to"],
            )

    def test_error_message_lists_missing_tool_names(self):
        """エラーメッセージに不整合 tool 名が含まれ、運用者がどの handler を
        足せばいいかが一目で分かる。"""
        with pytest.raises(ToolHandlerConsistencyError) as exc_info:
            validate_tool_handler_consistency(
                exposed_tool_names=["memory_recall_by_handle", "fictional_tool"],
                handler_keys=["spot_graph_travel_to"],
            )
        message = str(exc_info.value)
        assert "memory_recall_by_handle" in message
        assert "fictional_tool" in message

    def test_passes_when_all_exposed_tools_have_handlers(self):
        """spec が handler の部分集合になっていれば例外を投げず返る。"""
        validate_tool_handler_consistency(
            exposed_tool_names=["spot_graph_travel_to", "memory_recall_by_handle"],
            handler_keys=[
                "spot_graph_travel_to",
                "memory_recall_by_handle",
                "spot_graph_interact",
            ],
        )

    def test_allows_handlers_not_in_spec(self):
        """handler だけが存在し spec に出ていない tool は許容する。
        feature flag OFF や aux executor 常駐パターンを潰さないため。"""
        validate_tool_handler_consistency(
            exposed_tool_names=["spot_graph_travel_to"],
            handler_keys=["spot_graph_travel_to", "memory_recall_by_handle"],
        )

    def test_empty_inputs_are_safe(self):
        """両集合が空のとき (= minimal wiring / 構築途中) は例外にしない。"""
        validate_tool_handler_consistency(
            exposed_tool_names=[],
            handler_keys=[],
        )


class _StubToolDefinition:
    def __init__(self, name: str) -> None:
        self.name = name


class _StubRuntime:
    def __init__(self, definitions):
        self._definitions = definitions

    def get_tool_definitions(self):
        return self._definitions


class _StubWiring:
    """_WorldLlmWiring._validate_tool_handler_consistency を runtime / handler の
    両側だけ差し替えてテストするためのスタブ。"""

    def __init__(self, definitions, handlers):
        self.runtime = _StubRuntime(definitions)
        self._tool_handlers = dict.fromkeys(handlers, None)

    # _WorldLlmWiring 側のメソッドをそのまま借りる
    from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
        _WorldLlmWiring,
    )
    _validate_tool_handler_consistency = (
        _WorldLlmWiring._validate_tool_handler_consistency
    )


class TestWorldLlmWiringConsistencyHook:
    """_WorldLlmWiring._validate_tool_handler_consistency が runtime の
    get_tool_definitions と _tool_handlers を突き合わせる挙動。"""

    def test_raises_when_runtime_exposes_tool_without_handler(self):
        """runtime.get_tool_definitions が出した tool 名が _tool_handlers に
        無いと ToolHandlerConsistencyError を投げる。"""
        wiring = _StubWiring(
            definitions=[
                _StubToolDefinition("spot_graph_travel_to"),
                _StubToolDefinition("memory_recall_by_handle"),
            ],
            handlers=["spot_graph_travel_to"],
        )
        with pytest.raises(ToolHandlerConsistencyError):
            wiring._validate_tool_handler_consistency()

    def test_passes_when_runtime_tools_subset_of_handlers(self):
        """runtime が見せる tool が全て handler 集合に含まれていれば例外を
        投げない。"""
        wiring = _StubWiring(
            definitions=[_StubToolDefinition("spot_graph_travel_to")],
            handlers=["spot_graph_travel_to", "memory_recall_by_handle"],
        )
        wiring._validate_tool_handler_consistency()

    def test_skips_when_get_tool_definitions_raises(self):
        """get_tool_definitions 自体が例外を投げる構築途中の状態では、
        整合性検証は警告だけ残して return する (= 起動を巻き添えにしない)。"""

        class _BrokenRuntime:
            def get_tool_definitions(self):
                raise RuntimeError("runtime not ready")

        wiring = _StubWiring(definitions=[], handlers=[])
        wiring.runtime = _BrokenRuntime()
        wiring._validate_tool_handler_consistency()  # 例外を投げないこと
