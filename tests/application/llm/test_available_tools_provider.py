"""DefaultAvailableToolsProvider のテスト（正常・例外）"""

from dataclasses import replace

import pytest

from ai_rpg_world.application.llm.services.available_tools_provider import (
    DefaultAvailableToolsProvider,
)
from ai_rpg_world.application.llm.services.game_tool_registry import (
    DefaultGameToolRegistry,
)
from ai_rpg_world.application.llm.services.tool_catalog import (
    register_default_tools,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SNS_CREATE_POST,
    TOOL_NAME_SNS_ENTER,
    TOOL_NAME_SNS_LOGOUT,
    TOOL_NAME_SNS_VIEW_CURRENT_PAGE,
    TOOL_NAME_TRADE_ACCEPT,
    TOOL_NAME_TRADE_CANCEL,
    TOOL_NAME_TRADE_ENTER,
    TOOL_NAME_TRADE_EXIT,
    TOOL_NAME_TRADE_OFFER,
    TOOL_NAME_TRADE_VIEW_CURRENT_PAGE,
)
from ai_rpg_world.application.world.contracts.dtos import (
    AvailableMoveDto,
    AvailableTradeSummaryDto,
    InventoryItemDto,
    PlayerCurrentStateDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _context_with_moves(total: int, *, is_busy: bool = False, visible_objects=None):
    moves = [
        AvailableMoveDto(spot_id=2, spot_name="B", road_id=1, road_description="", conditions_met=True, failed_conditions=[])
    ] * max(0, total)
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="P",
        current_spot_id=1,
        current_spot_name="A",
        current_spot_description="",
        x=0, y=0, z=0,
        area_id=None,
        area_name=None,
        current_player_count=0,
        current_player_ids=set(),
        connected_spot_ids=set(),
        connected_spot_names=set(),
        weather_type="clear",
        weather_intensity=0.0,
        current_terrain_type=None,
        visible_objects=visible_objects or [],
        view_distance=5,
        available_moves=moves if total else [],
        total_available_moves=total,
        attention_level=AttentionLevel.FULL,
        is_busy=is_busy,
        is_sns_mode_active=False,
    )


class TestDefaultAvailableToolsProvider:
    """DefaultAvailableToolsProvider の正常・例外ケース"""

    @pytest.fixture
    def registry(self):
        r = DefaultGameToolRegistry()
        register_default_tools(
            r,
            speech_enabled=True,
        )
        return r

    @pytest.fixture
    def provider(self, registry):
        return DefaultAvailableToolsProvider(registry)

    @pytest.fixture
    def registry_sns_and_trade(self):
        """sns_enabled と trade_enabled を同時に有効化したレジストリ（取引カタログは sns に依存しない）"""
        r = DefaultGameToolRegistry()
        register_default_tools(
            r,
            speech_enabled=True,
            sns_enabled=True,
            trade_enabled=True,
        )
        return r

    @pytest.fixture
    def provider_sns_and_trade(self, registry_sns_and_trade):
        return DefaultAvailableToolsProvider(registry_sns_and_trade)

    @pytest.fixture
    def registry_trade_virtual_pages(self):
        r = DefaultGameToolRegistry()
        register_default_tools(
            r,
            speech_enabled=True,
            sns_enabled=True,
            trade_enabled=True,
            trade_virtual_pages_enabled=True,
        )
        return r

    @pytest.fixture
    def provider_trade_vp(self, registry_trade_virtual_pages):
        return DefaultAvailableToolsProvider(registry_trade_virtual_pages)

    def test_sns_mode_off_shows_sns_enter_and_trade_enter_only(self, provider_sns_and_trade):
        """未起動では SNS は sns_enter のみ、取引は trade_enter のみ（ミューテーションは出ない）"""
        ctx = _context_with_moves(1)
        ctx.is_sns_mode_active = False
        ctx.is_trade_mode_active = False
        ctx.inventory_items = [InventoryItemDto(1, 10, "剣", 1)]
        ctx.available_trades = [AvailableTradeSummaryDto(trade_id=1, item_name="盾", requested_gold=10)]
        tools = provider_sns_and_trade.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_SNS_ENTER in names
        assert TOOL_NAME_SNS_LOGOUT not in names
        assert TOOL_NAME_SNS_CREATE_POST not in names
        assert TOOL_NAME_TRADE_ENTER in names
        assert TOOL_NAME_TRADE_EXIT not in names
        assert TOOL_NAME_TRADE_OFFER not in names
        assert TOOL_NAME_TRADE_ACCEPT not in names
        assert TOOL_NAME_SNS_VIEW_CURRENT_PAGE not in names

    def test_sns_mode_on_shows_sns_tools_trade_family_hidden(self, provider_sns_and_trade):
        """SNS モード ON では SNS 操作のみ。取引ファミリーは非表示"""
        ctx = _context_with_moves(1)
        ctx.is_sns_mode_active = True
        ctx.inventory_items = [InventoryItemDto(1, 10, "剣", 1)]
        ctx.available_trades = [AvailableTradeSummaryDto(trade_id=1, item_name="盾", requested_gold=10)]
        tools = provider_sns_and_trade.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_SNS_ENTER not in names
        assert TOOL_NAME_SNS_LOGOUT in names
        assert TOOL_NAME_SNS_CREATE_POST in names
        assert TOOL_NAME_TRADE_ENTER not in names
        assert TOOL_NAME_TRADE_OFFER not in names
        assert TOOL_NAME_SNS_VIEW_CURRENT_PAGE not in names

    def test_trade_mode_on_without_virtual_page_hides_trade_ref_mutations(self, provider_sns_and_trade):
        """trade page 未配線では trade_ref 前提ミューテーションは表示しない。"""
        ctx = replace(
            _context_with_moves(1),
            active_game_app="trade",
            inventory_items=[InventoryItemDto(1, 10, "剣", 1)],
            available_trades=[AvailableTradeSummaryDto(trade_id=1, item_name="盾", requested_gold=10)],
        )
        tools = provider_sns_and_trade.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_TRADE_ENTER not in names
        assert TOOL_NAME_TRADE_EXIT in names
        assert TOOL_NAME_TRADE_OFFER in names
        assert TOOL_NAME_TRADE_ACCEPT not in names
        assert TOOL_NAME_TRADE_CANCEL not in names

    def test_trade_mode_with_virtual_page_shows_nav_tools(self, provider_trade_vp):
        """仮想取引所配線時、取引所モードかつ page kind があるとナビツールが出る"""
        ctx = replace(
            _context_with_moves(1),
            active_game_app="trade",
            trade_virtual_page_kind="market",
            inventory_items=[InventoryItemDto(1, 10, "剣", 1)],
            available_trades=[],
        )
        tools = provider_trade_vp.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_TRADE_VIEW_CURRENT_PAGE in names

    def test_trade_mode_incoming_tab_shows_accept_not_cancel(self, provider_trade_vp):
        """my_trades / incoming では受諾・拒否のみ（キャンセルは selling のみ）"""
        ctx = replace(
            _context_with_moves(1),
            active_game_app="trade",
            trade_virtual_page_kind="my_trades",
            trade_my_trades_tab="incoming",
            inventory_items=[InventoryItemDto(1, 10, "剣", 1)],
            available_trades=[AvailableTradeSummaryDto(trade_id=1, item_name="盾", requested_gold=10)],
        )
        tools = provider_trade_vp.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_TRADE_ACCEPT in names
        assert TOOL_NAME_TRADE_CANCEL not in names

    def test_trade_mode_incoming_tab_shows_accept_when_available_trades_empty(
        self, provider_trade_vp
    ):
        """my_trades / incoming では宛先要約が空でも受諾を出す（スナップショットの trade_ref を正とする）"""
        ctx = replace(
            _context_with_moves(1),
            active_game_app="trade",
            trade_virtual_page_kind="my_trades",
            trade_my_trades_tab="incoming",
            inventory_items=[InventoryItemDto(1, 10, "剣", 1)],
            available_trades=[],
        )
        tools = provider_trade_vp.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_TRADE_ACCEPT in names

    def test_trade_mode_selling_tab_shows_cancel_not_accept(self, provider_trade_vp):
        """my_trades / selling ではキャンセルのみ（incoming 要約が空でも cancel を出す）"""
        ctx = replace(
            _context_with_moves(1),
            active_game_app="trade",
            trade_virtual_page_kind="my_trades",
            trade_my_trades_tab="selling",
            inventory_items=[InventoryItemDto(1, 10, "剣", 1)],
            available_trades=[],
        )
        tools = provider_trade_vp.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_TRADE_CANCEL in names
        assert TOOL_NAME_TRADE_ACCEPT not in names


    def test_tool_format_openai_compatible(self, provider):
        """返却形式が OpenAI の function ツール形式である"""
        tools = provider.get_available_tools(_context_with_moves(1))
        assert tools
        for t in tools:
            assert "type" in t and t["type"] == "function"
            assert "function" in t
            assert "name" in t["function"]
            assert "description" in t["function"]
            assert "parameters" in t["function"]

    def test_init_registry_not_registry_raises_type_error(self):
        """registry が IGameToolRegistry でないとき TypeError"""
        with pytest.raises(TypeError, match="registry must be IGameToolRegistry"):
            DefaultAvailableToolsProvider(None)  # type: ignore[arg-type]
