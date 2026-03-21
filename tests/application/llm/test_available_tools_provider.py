"""DefaultAvailableToolsProvider のテスト（正常・例外）"""

import pytest

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.services.availability_resolvers import (
    NoOpAvailabilityResolver,
    SetDestinationAvailabilityResolver,
)
from ai_rpg_world.application.llm.services.available_tools_provider import (
    DefaultAvailableToolsProvider,
)
from ai_rpg_world.application.llm.services.game_tool_registry import (
    DefaultGameToolRegistry,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CHANGE_ATTENTION,
    TOOL_NAME_CHEST_STORE,
    TOOL_NAME_COMBAT_USE_SKILL,
    TOOL_NAME_CONVERSATION_ADVANCE,
    TOOL_NAME_DESTROY_PLACEABLE,
    TOOL_NAME_HARVEST_CANCEL,
    TOOL_NAME_HARVEST_START,
    TOOL_NAME_INTERACT_WORLD_OBJECT,
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_NO_OP,
    TOOL_NAME_PLACE_OBJECT,
    TOOL_NAME_SAY,
    TOOL_NAME_SKILL_ACCEPT_PROPOSAL,
    TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE,
    TOOL_NAME_SKILL_EQUIP,
    TOOL_NAME_SKILL_REJECT_PROPOSAL,
    TOOL_NAME_SNS_CREATE_POST,
    TOOL_NAME_SNS_ENTER,
    TOOL_NAME_SNS_LOGOUT,
    TOOL_NAME_TRADE_OFFER,
)
from ai_rpg_world.application.llm.services.tool_catalog import (
    register_default_tools,
)
from ai_rpg_world.application.world.contracts.dtos import (
    ActiveHarvestDto,
    ActiveConversationDto,
    AvailableMoveDto,
    AvailableTradeSummaryDto,
    AttentionLevelOptionDto,
    AwakenedActionDto,
    ChestItemDto,
    ConversationChoiceDto,
    EquipableSkillCandidateDto,
    InventoryItemDto,
    PendingSkillProposalDto,
    PlayerCurrentStateDto,
    SkillEquipSlotDto,
    UsableSkillDto,
    VisibleObjectDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillProposalType


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
            interaction_enabled=True,
            harvest_enabled=True,
            attention_enabled=True,
            conversation_enabled=True,
            place_enabled=True,
            chest_enabled=True,
            combat_enabled=True,
        )
        return r

    @pytest.fixture
    def provider(self, registry):
        return DefaultAvailableToolsProvider(registry)

    @pytest.fixture
    def registry_sns_trade(self):
        r = DefaultGameToolRegistry()
        register_default_tools(
            r,
            speech_enabled=True,
            sns_enabled=True,
            trade_enabled=True,
        )
        return r

    @pytest.fixture
    def provider_sns_trade(self, registry_sns_trade):
        return DefaultAvailableToolsProvider(registry_sns_trade)

    def test_sns_mode_off_shows_only_sns_enter_among_sns_tools(self, provider_sns_trade):
        """SNS モード OFF では SNS 系は sns_enter のみ（投稿・取引は出ない）"""
        ctx = _context_with_moves(1)
        ctx.is_sns_mode_active = False
        ctx.inventory_items = [InventoryItemDto(1, 10, "剣", 1)]
        ctx.available_trades = [AvailableTradeSummaryDto(trade_id=1, item_name="盾", requested_gold=10)]
        tools = provider_sns_trade.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_SNS_ENTER in names
        assert TOOL_NAME_SNS_LOGOUT not in names
        assert TOOL_NAME_SNS_CREATE_POST not in names
        assert TOOL_NAME_TRADE_OFFER not in names

    def test_sns_mode_on_shows_sns_interaction_and_trade_not_enter(self, provider_sns_trade):
        """SNS モード ON では操作系 SNS・取引が出るが sns_enter は出ない"""
        ctx = _context_with_moves(1)
        ctx.is_sns_mode_active = True
        ctx.inventory_items = [InventoryItemDto(1, 10, "剣", 1)]
        ctx.available_trades = [AvailableTradeSummaryDto(trade_id=1, item_name="盾", requested_gold=10)]
        tools = provider_sns_trade.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_SNS_ENTER not in names
        assert TOOL_NAME_SNS_LOGOUT in names
        assert TOOL_NAME_SNS_CREATE_POST in names
        assert TOOL_NAME_TRADE_OFFER in names

    def test_get_available_tools_context_none_returns_no_op_only(self, provider):
        """context が None のときは no_op のみ（move_to_destination は利用不可）"""
        tools = provider.get_available_tools(None)
        assert isinstance(tools, list)
        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == TOOL_NAME_NO_OP

    def test_get_available_tools_context_with_moves_returns_both(self, provider):
        """context に移動先があるときは no_op と move_to_destination の両方"""
        ctx = _context_with_moves(1)
        tools = provider.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_NO_OP in names
        assert TOOL_NAME_MOVE_TO_DESTINATION in names
        assert TOOL_NAME_SAY in names

    def test_get_available_tools_when_busy_hides_move_tool(self, provider):
        ctx = _context_with_moves(1, is_busy=True)
        tools = provider.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_NO_OP in names
        assert TOOL_NAME_MOVE_TO_DESTINATION not in names

    def test_get_available_tools_with_interaction_targets_adds_interact_and_harvest(self, provider):
        visible_objects = [
            VisibleObjectDto(
                object_id=10,
                object_type="NPC",
                x=1,
                y=0,
                z=0,
                distance=1,
                display_name="老人",
                object_kind="npc",
                available_interactions=["interact"],
            ),
            VisibleObjectDto(
                object_id=11,
                object_type="RESOURCE",
                x=0,
                y=1,
                z=0,
                distance=1,
                display_name="薬草",
                object_kind="resource",
                available_interactions=["harvest"],
            ),
        ]
        ctx = _context_with_moves(0, visible_objects=visible_objects)
        tools = provider.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_INTERACT_WORLD_OBJECT in names
        assert TOOL_NAME_HARVEST_START in names

    def test_get_available_tools_with_active_harvest_hides_start_and_shows_cancel(self, provider):
        ctx = _context_with_moves(0, is_busy=True)
        ctx.active_harvest = ActiveHarvestDto(
            target_world_object_id=11,
            target_display_name="薬草",
            finish_tick=15,
        )
        tools = provider.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_HARVEST_START not in names
        assert TOOL_NAME_HARVEST_CANCEL in names

    def test_get_available_tools_with_extended_context_adds_extended_tools(self, provider):
        visible_objects = [
            VisibleObjectDto(
                object_id=10,
                object_type="CHEST",
                x=1,
                y=0,
                z=0,
                distance=1,
                display_name="宝箱",
                object_kind="chest",
                available_interactions=["interact", "store_in_chest", "take_from_chest"],
            ),
        ]
        ctx = _context_with_moves(
            0,
            visible_objects=visible_objects,
        )
        ctx.inventory_items = [InventoryItemDto(2, 400, "木箱", 1, is_placeable=True)]
        ctx.chest_items = [ChestItemDto(10, "宝箱", 500, "ポーション", 1)]
        ctx.active_conversation = ActiveConversationDto(
            npc_world_object_id=20,
            npc_display_name="老人",
            node_text="どうする？",
            choices=[ConversationChoiceDto(display_text="はい", choice_index=0)],
            is_terminal=False,
        )
        ctx.usable_skills = [UsableSkillDto(10, 1, 100, "火球")]
        ctx.equipable_skill_candidates = [
            EquipableSkillCandidateDto(10, 100, "火球", DeckTier.NORMAL)
        ]
        ctx.skill_equip_slots = [
            SkillEquipSlotDto(10, DeckTier.NORMAL, 0, "通常スロット 1")
        ]
        ctx.pending_skill_proposals = [
            PendingSkillProposalDto(
                progress_id=20,
                proposal_id=1,
                offered_skill_id=300,
                display_name="300: 新しい攻撃手段",
                proposal_type=SkillProposalType.ADD,
                deck_tier=DeckTier.NORMAL,
            )
        ]
        ctx.awakened_action = AwakenedActionDto(10, "覚醒モードを発動")
        ctx.attention_level_options = [
            AttentionLevelOptionDto("FULL", "フル", "すべて受け取る"),
        ]
        ctx.can_destroy_placeable = True
        tools = provider.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_CHANGE_ATTENTION in names
        assert TOOL_NAME_CONVERSATION_ADVANCE in names
        assert TOOL_NAME_PLACE_OBJECT in names
        assert TOOL_NAME_DESTROY_PLACEABLE in names
        assert TOOL_NAME_CHEST_STORE in names
        assert TOOL_NAME_COMBAT_USE_SKILL in names
        assert TOOL_NAME_SKILL_EQUIP in names
        assert TOOL_NAME_SKILL_ACCEPT_PROPOSAL in names
        assert TOOL_NAME_SKILL_REJECT_PROPOSAL in names
        assert TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE in names

    def test_get_available_tools_hides_skill_management_tools_without_matching_labels(self, provider):
        ctx = _context_with_moves(0)
        ctx.usable_skills = [UsableSkillDto(10, 1, 100, "火球")]

        tools = provider.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]

        assert TOOL_NAME_COMBAT_USE_SKILL in names
        assert TOOL_NAME_SKILL_EQUIP not in names
        assert TOOL_NAME_SKILL_ACCEPT_PROPOSAL not in names
        assert TOOL_NAME_SKILL_REJECT_PROPOSAL not in names
        assert TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE not in names

    def test_get_available_tools_hides_awakened_tool_when_action_missing(self, provider):
        ctx = _context_with_moves(0)
        ctx.equipable_skill_candidates = [
            EquipableSkillCandidateDto(10, 100, "火球", DeckTier.NORMAL)
        ]
        ctx.skill_equip_slots = [
            SkillEquipSlotDto(10, DeckTier.NORMAL, 0, "通常スロット 1")
        ]
        ctx.awakened_action = None

        tools = provider.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]

        assert TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE not in names

    def test_get_available_tools_exposes_proposal_decisions_without_equip_labels(self, provider):
        ctx = _context_with_moves(0)
        ctx.pending_skill_proposals = [
            PendingSkillProposalDto(
                progress_id=20,
                proposal_id=1,
                offered_skill_id=300,
                display_name="300: 新しい攻撃手段",
                proposal_type=SkillProposalType.ADD,
                deck_tier=DeckTier.NORMAL,
            )
        ]

        tools = provider.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]

        assert TOOL_NAME_SKILL_ACCEPT_PROPOSAL in names
        assert TOOL_NAME_SKILL_REJECT_PROPOSAL in names
        assert TOOL_NAME_SKILL_EQUIP not in names

    def test_get_available_tools_exposes_equip_without_proposals(self, provider):
        ctx = _context_with_moves(0)
        ctx.equipable_skill_candidates = [
            EquipableSkillCandidateDto(10, 100, "火球", DeckTier.NORMAL)
        ]
        ctx.skill_equip_slots = [
            SkillEquipSlotDto(10, DeckTier.NORMAL, 0, "通常スロット 1")
        ]

        tools = provider.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]

        assert TOOL_NAME_SKILL_EQUIP in names
        assert TOOL_NAME_SKILL_ACCEPT_PROPOSAL not in names
        assert TOOL_NAME_SKILL_REJECT_PROPOSAL not in names

    def test_tool_format_openai_compatible(self, provider):
        """返却形式が OpenAI の function ツール形式である"""
        tools = provider.get_available_tools(None)
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
