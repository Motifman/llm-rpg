"""``spot_graph_give_items`` の dispatch table 抜け silent bug の回帰テスト
(Y_after_pr639_640_200tick 後続、Issue: RESOLVER_DISPATCH_MISSING)。

Y_after_pr639_640_200tick で P4 カイが tick=124 / 147 に ``spot_graph_give_items``
(batch 配布) を試行した際、resolver が dispatch されず ``RESOLVER_DISPATCH_MISSING``
error_code で 2 回連続失敗した。

原因: ``SpotGraphArgumentResolver.resolve_args`` の入口 gate である
``_SPOT_GRAPH_TOOLS`` frozenset に ``TOOL_NAME_SPOT_GRAPH_GIVE_ITEMS`` が
登録されていなかった (単数版 ``TOOL_NAME_SPOT_GRAPH_GIVE_ITEM`` のみ)。
resolve_args の分岐本体 (``if tool_name == TOOL_NAME_SPOT_GRAPH_GIVE_ITEMS: ...``)
と ``_resolve_give_items`` メソッドは実装済みだったが、gate で ``None`` が
返されて到達しなかった。

**修正**: frozenset に ``TOOL_NAME_SPOT_GRAPH_GIVE_ITEMS`` を追加 (1 行)。

本テストは gate の membership を確認することで、将来また同じ silent bug が
再発する (新 tool を追加したが frozenset 追加を忘れる) 場合を検出する。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    _SPOT_GRAPH_TOOLS,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_ATTACK,
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEMS,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)


class TestGiveItemsIsRegisteredInDispatchGate:
    """``TOOL_NAME_SPOT_GRAPH_GIVE_ITEMS`` が dispatch gate に登録されている。"""

    def test_give_items_が_dispatch_gate_に含まれる(self) -> None:
        """resolve_args の入口 gate である _SPOT_GRAPH_TOOLS frozenset に
        含まれていることを確認。Y_after_pr639_640 の RESOLVER_DISPATCH_MISSING
        再発防止。"""
        assert TOOL_NAME_SPOT_GRAPH_GIVE_ITEMS in _SPOT_GRAPH_TOOLS, (
            "give_items が gate frozenset に無いと dispatch で None が返り、"
            "RESOLVER_DISPATCH_MISSING で silent 失敗する (Y_after_pr639_640 "
            "の tick=124/147 で観測された bug)"
        )

    def test_全ての_spot_graph_tool_が_gate_に登録される(self) -> None:
        """今後の tool 追加で同じ silent bug を防ぐため、tool_constants から
        認識できる ``spot_graph_*`` および spot_graph 系兼用の tool が
        全て gate に含まれることを確認する。

        gate は resolver dispatch の入口。ここに無い tool は resolve_args
        が ``None`` を返し、後段の handler が実装されていても到達しない。
        """
        expected = {
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
            TOOL_NAME_SPOT_GRAPH_EXPLORE,
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            TOOL_NAME_SPOT_GRAPH_WAIT,
            TOOL_NAME_SPOT_GRAPH_ATTACK,
            TOOL_NAME_SPOT_GRAPH_LISTEN,
            TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
            TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
            TOOL_NAME_SPOT_GRAPH_USE_ITEM,
            TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
            TOOL_NAME_SPOT_GRAPH_GIVE_ITEMS,
            TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
        }
        missing = expected - _SPOT_GRAPH_TOOLS
        assert not missing, (
            f"以下の tool が gate に登録されていない (silent dispatch 抜け): "
            f"{missing}"
        )
