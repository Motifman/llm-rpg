"""SNS / trade tool 出し分けの runtime 非依存テスト (経路統一 R2a-2)。

SNS / trade は最終目的 (AI being MMO RPG) の将来機能なので残す。だが従来この gating は
``create_llm_agent_wiring`` (full wiring) 経由の PromptBuilder でしか検証されておらず
(``test_sns_mode_wiring_e2e.py``)、full wiring 退役 (R2c) でカバレッジが失われる。

gating の本体は full wiring ではなく runtime 非依存層にある:
- tool catalog (``get_sns_specs`` / ``get_trade_specs`` 等) が (定義, resolver) を返す
- resolver (``SnsToolAvailabilityResolver`` 等) が PlayerCurrentStateDto.is_sns_mode_active /
  sns_virtual_page_kind を見て出し分ける
- ``DefaultAvailableToolsProvider`` が resolver.is_available で絞る

本テストはこの runtime 非依存の経路 (registry + provider) を直接叩いて gating 仕様を
固定する。full wiring を消しても SNS/trade tool 露出仕様が回帰から守られ、将来 escape
(generic) runtime へ SNS/trade を組み込む際の土台になる。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.available_tools_provider import (
    DefaultAvailableToolsProvider,
)
from ai_rpg_world.application.llm.services.game_tool_registry import (
    DefaultGameToolRegistry,
)
from ai_rpg_world.application.llm.services.tool_catalog import register_default_tools
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SNS_CREATE_POST,
    TOOL_NAME_SNS_ENTER,
    TOOL_NAME_SNS_LOGOUT,
    TOOL_NAME_SNS_VIEW_CURRENT_PAGE,
    TOOL_NAME_TRADE_ENTER,
    TOOL_NAME_TRADE_OFFER,
)
from ai_rpg_world.application.world.contracts.dtos import (
    AvailableMoveDto,
    AvailableTradeSummaryDto,
    InventoryItemDto,
    PlayerCurrentStateDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _state(
    *,
    is_sns_mode_active: bool,
    sns_virtual_page_kind: str | None = None,
) -> PlayerCurrentStateDto:
    """SNS/trade gating 判定に効くフィールドだけ意味を持たせた最小 state。"""
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="P",
        current_spot_id=1,
        current_spot_name="A",
        current_spot_description="",
        x=0,
        y=0,
        z=0,
        area_id=None,
        area_name=None,
        current_player_count=0,
        current_player_ids=set(),
        connected_spot_ids=set(),
        connected_spot_names=set(),
        weather_type="clear",
        weather_intensity=0.0,
        current_terrain_type=None,
        visible_objects=[],
        view_distance=5,
        available_moves=[
            AvailableMoveDto(
                spot_id=2,
                spot_name="B",
                road_id=1,
                road_description="",
                conditions_met=True,
                failed_conditions=[],
            )
        ],
        total_available_moves=1,
        attention_level=AttentionLevel.FULL,
        is_sns_mode_active=is_sns_mode_active,
        sns_virtual_page_kind=sns_virtual_page_kind,
        sns_current_page_snapshot_json=None,
        inventory_items=[InventoryItemDto(1, 10, "剣", 1)],
        available_trades=[
            AvailableTradeSummaryDto(trade_id=1, item_name="盾", requested_gold=10)
        ],
    )


def _tool_names(*, sns_virtual_pages_enabled: bool, state: PlayerCurrentStateDto) -> set[str]:
    """SNS+trade を登録した registry から、state に応じて露出される tool 名集合を返す。"""
    registry = DefaultGameToolRegistry()
    register_default_tools(
        registry,
        sns_enabled=True,
        trade_enabled=True,
        sns_virtual_pages_enabled=sns_virtual_pages_enabled,
    )
    provider = DefaultAvailableToolsProvider(registry)
    tools = provider.get_available_tools(state)
    return {
        t["function"]["name"] for t in tools if t.get("type") == "function"
    }


class TestSnsTradeToolGating:
    """PlayerCurrentStateDto のモードに応じた SNS/trade tool 出し分け (runtime 非依存)。"""

    def test_sns_mode_off_shows_sns_enter_and_trade_enter_only(self) -> None:
        """SNS off: sns_enter / trade_enter は出るが、SNS 内操作・trade_offer は出ない。"""
        names = _tool_names(
            sns_virtual_pages_enabled=False,
            state=_state(is_sns_mode_active=False),
        )
        assert TOOL_NAME_SNS_ENTER in names
        assert TOOL_NAME_TRADE_ENTER in names
        assert TOOL_NAME_SNS_LOGOUT not in names
        assert TOOL_NAME_SNS_CREATE_POST not in names
        assert TOOL_NAME_TRADE_OFFER not in names
        assert TOOL_NAME_SNS_VIEW_CURRENT_PAGE not in names

    def test_sns_mode_on_shows_sns_ops_and_hides_trade_family(self) -> None:
        """SNS on: sns_logout/create_post は出る。trade 系と sns_enter は隠れる (排他)。"""
        names = _tool_names(
            sns_virtual_pages_enabled=False,
            state=_state(is_sns_mode_active=True),
        )
        assert TOOL_NAME_SNS_LOGOUT in names
        assert TOOL_NAME_SNS_CREATE_POST in names
        assert TOOL_NAME_SNS_ENTER not in names
        assert TOOL_NAME_TRADE_ENTER not in names
        assert TOOL_NAME_TRADE_OFFER not in names
        # virtual pages OFF なら view_current_page は出ない
        assert TOOL_NAME_SNS_VIEW_CURRENT_PAGE not in names

    def test_sns_mode_on_with_virtual_pages_shows_view_current_page(self) -> None:
        """SNS on + virtual pages + 現在ページあり: view_current_page が出る。"""
        names = _tool_names(
            sns_virtual_pages_enabled=True,
            state=_state(is_sns_mode_active=True, sns_virtual_page_kind="home"),
        )
        assert TOOL_NAME_SNS_VIEW_CURRENT_PAGE in names
