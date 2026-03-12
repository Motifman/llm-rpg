"""availability_resolvers（NoOp, SetDestination）のテスト（正常・境界）"""

import pytest

from ai_rpg_world.application.llm.services.availability_resolvers import (
    CancelMovementAvailabilityResolver,
    ChangeAttentionAvailabilityResolver,
    ChestStoreAvailabilityResolver,
    CombatUseSkillAvailabilityResolver,
    ConversationAdvanceAvailabilityResolver,
    DestroyPlaceableAvailabilityResolver,
    GuildAddMemberAvailabilityResolver,
    GuildChangeRoleAvailabilityResolver,
    GuildCreateAvailabilityResolver,
    GuildDisbandAvailabilityResolver,
    InspectItemAvailabilityResolver,
    InspectTargetAvailabilityResolver,
    NoOpAvailabilityResolver,
    PlaceObjectAvailabilityResolver,
    PursuitCancelAvailabilityResolver,
    PursuitStartAvailabilityResolver,
    SetDestinationAvailabilityResolver,
    SkillAcceptProposalAvailabilityResolver,
    SkillActivateAwakenedModeAvailabilityResolver,
    SkillEquipAvailabilityResolver,
    SkillRejectProposalAvailabilityResolver,
    WhisperAvailabilityResolver,
)
from ai_rpg_world.application.world.contracts.dtos import (
    ActiveConversationDto,
    AvailableLocationAreaDto,
    AvailableMoveDto,
    AttentionLevelOptionDto,
    AwakenedActionDto,
    ChestItemDto,
    ConversationChoiceDto,
    EquipableSkillCandidateDto,
    GuildMembershipSummaryDto,
    InventoryItemDto,
    PendingSkillProposalDto,
    PlayerCurrentStateDto,
    SkillEquipSlotDto,
    UsableSkillDto,
    VisibleObjectDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillProposalType


def _minimal_current_state(
    current_spot_id: int | None = 1,
    available_moves: list | None = None,
    total_available_moves: int | None = 0,
    available_location_areas: list | None = None,
    visible_objects: list | None = None,
) -> PlayerCurrentStateDto:
    """テスト用の最小限の PlayerCurrentStateDto"""
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="Test",
        current_spot_id=current_spot_id,
        current_spot_name="Spot",
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
        visible_objects=visible_objects or [],
        view_distance=5,
        available_moves=available_moves,
        total_available_moves=total_available_moves,
        available_location_areas=available_location_areas,
        attention_level=AttentionLevel.FULL,
    )


class TestNoOpAvailabilityResolver:
    """NoOpAvailabilityResolver は常に True"""

    def test_available_when_context_is_none(self):
        """context が None でも利用可能"""
        resolver = NoOpAvailabilityResolver()
        assert resolver.is_available(None) is True

    def test_available_when_context_present(self):
        """context があっても利用可能"""
        resolver = NoOpAvailabilityResolver()
        ctx = _minimal_current_state()
        assert resolver.is_available(ctx) is True


class TestSetDestinationAvailabilityResolver:
    """SetDestinationAvailabilityResolver の境界・正常"""

    def test_not_available_when_context_none(self):
        """context が None のとき利用不可"""
        resolver = SetDestinationAvailabilityResolver()
        assert resolver.is_available(None) is False

    def test_not_available_when_current_spot_id_none(self):
        """current_spot_id が None のとき利用不可"""
        resolver = SetDestinationAvailabilityResolver()
        ctx = _minimal_current_state(current_spot_id=None)
        assert resolver.is_available(ctx) is False

    def test_not_available_when_available_moves_none(self):
        """available_moves が None のとき利用不可"""
        resolver = SetDestinationAvailabilityResolver()
        ctx = _minimal_current_state(available_moves=None, total_available_moves=None)
        assert resolver.is_available(ctx) is False

    def test_not_available_when_has_active_path(self):
        """移動計画が残っているとき利用不可"""
        resolver = SetDestinationAvailabilityResolver()
        move = AvailableMoveDto(
            spot_id=2,
            spot_name="Next",
            road_id=1,
            road_description="",
            conditions_met=True,
            failed_conditions=[],
        )
        ctx = _minimal_current_state(available_moves=[move], total_available_moves=1)
        ctx.has_active_path = True
        assert resolver.is_available(ctx) is False

    def test_not_available_when_is_busy(self):
        """is_busy が True のとき利用不可"""
        resolver = SetDestinationAvailabilityResolver()
        move = AvailableMoveDto(
            spot_id=2,
            spot_name="Next",
            road_id=1,
            road_description="",
            conditions_met=True,
            failed_conditions=[],
        )
        ctx = _minimal_current_state(available_moves=[move], total_available_moves=1)
        ctx.is_busy = True
        assert resolver.is_available(ctx) is False

    def test_not_available_when_total_zero(self):
        """total_available_moves が 0 のとき利用不可"""
        resolver = SetDestinationAvailabilityResolver()
        ctx = _minimal_current_state(available_moves=[], total_available_moves=0)
        assert resolver.is_available(ctx) is False

    def test_available_when_has_moves(self):
        """現在地があり移動先が 1 件以上あるとき利用可能"""
        resolver = SetDestinationAvailabilityResolver()
        move = AvailableMoveDto(
            spot_id=2,
            spot_name="Next",
            road_id=1,
            road_description="",
            conditions_met=True,
            failed_conditions=[],
        )
        ctx = _minimal_current_state(
            available_moves=[move],
            total_available_moves=1,
        )
        assert resolver.is_available(ctx) is True

    def test_available_when_has_location_areas_only(self):
        """available_moves がなく available_location_areas のみあるときも利用可能"""
        resolver = SetDestinationAvailabilityResolver()
        ctx = _minimal_current_state(
            available_moves=[],
            total_available_moves=0,
            available_location_areas=[
                AvailableLocationAreaDto(location_area_id=10, name="ギルド"),
            ],
        )
        assert resolver.is_available(ctx) is True

    def test_not_available_when_location_areas_empty(self):
        """available_location_areas が空リストのとき利用不可"""
        resolver = SetDestinationAvailabilityResolver()
        ctx = _minimal_current_state(
            available_moves=[],
            total_available_moves=0,
            available_location_areas=[],
        )
        assert resolver.is_available(ctx) is False

    def test_not_available_when_location_areas_none(self):
        """available_location_areas が None で moves もないとき利用不可"""
        resolver = SetDestinationAvailabilityResolver()
        ctx = _minimal_current_state(
            available_moves=[],
            total_available_moves=0,
            available_location_areas=None,
        )
        assert resolver.is_available(ctx) is False

    def test_available_when_has_actionable_objects_only(self):
        """available_moves も available_location_areas もなく actionable_objects のみあるときも利用可能"""
        resolver = SetDestinationAvailabilityResolver()
        ctx = _minimal_current_state(
            available_moves=[],
            total_available_moves=0,
            available_location_areas=None,
            visible_objects=[],
        )
        ctx.actionable_objects = [
            VisibleObjectDto(
                object_id=200,
                object_type="NPC",
                x=0,
                y=1,
                z=0,
                distance=1,
                display_name="老人",
                object_kind="npc",
                available_interactions=["interact"],
            ),
        ]
        assert resolver.is_available(ctx) is True


class TestCancelMovementAvailabilityResolver:
    """CancelMovementAvailabilityResolver の境界・正常"""

    def test_not_available_when_context_none(self):
        """context が None のとき利用不可"""
        resolver = CancelMovementAvailabilityResolver()
        assert resolver.is_available(None) is False

    def test_not_available_when_has_active_path_false(self):
        """has_active_path が False のとき利用不可"""
        resolver = CancelMovementAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.has_active_path = False
        assert resolver.is_available(ctx) is False

    def test_available_when_has_active_path_true(self):
        """has_active_path が True のとき利用可能"""
        resolver = CancelMovementAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.has_active_path = True
        assert resolver.is_available(ctx) is True


class TestWhisperAvailabilityResolver:
    def test_not_available_when_context_none(self):
        resolver = WhisperAvailabilityResolver()
        assert resolver.is_available(None) is False

    def test_not_available_when_no_other_player_visible(self):
        resolver = WhisperAvailabilityResolver()
        ctx = _minimal_current_state(
            visible_objects=[
                VisibleObjectDto(
                    object_id=1,
                    object_type="PLAYER",
                    x=0,
                    y=0,
                    z=0,
                    distance=0,
                    object_kind="player",
                    is_self=True,
                )
            ]
        )
        assert resolver.is_available(ctx) is False

    def test_available_when_other_player_visible(self):
        resolver = WhisperAvailabilityResolver()
        ctx = _minimal_current_state(
            visible_objects=[
                VisibleObjectDto(
                    object_id=2,
                    object_type="PLAYER",
                    x=1,
                    y=0,
                    z=0,
                    distance=1,
                    object_kind="player",
                    is_self=False,
                )
            ]
        )
        assert resolver.is_available(ctx) is True


class TestPursuitStartAvailabilityResolver:
    """PursuitStartAvailabilityResolver の境界・正常"""

    def test_not_available_when_context_none(self):
        resolver = PursuitStartAvailabilityResolver()
        assert resolver.is_available(None) is False

    def test_not_available_when_is_busy(self):
        resolver = PursuitStartAvailabilityResolver()
        ctx = _minimal_current_state(
            visible_objects=[
                VisibleObjectDto(
                    object_id=2,
                    object_type="PLAYER",
                    x=1,
                    y=0,
                    z=0,
                    distance=1,
                    object_kind="player",
                    is_self=False,
                )
            ]
        )
        ctx.is_busy = True
        assert resolver.is_available(ctx) is False

    def test_not_available_when_no_player_or_monster_visible(self):
        resolver = PursuitStartAvailabilityResolver()
        ctx = _minimal_current_state(
            visible_objects=[
                VisibleObjectDto(
                    object_id=2,
                    object_type="NPC",
                    x=1,
                    y=0,
                    z=0,
                    distance=1,
                    object_kind="npc",
                    is_self=False,
                )
            ]
        )
        assert resolver.is_available(ctx) is False

    def test_available_when_player_visible(self):
        resolver = PursuitStartAvailabilityResolver()
        ctx = _minimal_current_state(
            visible_objects=[
                VisibleObjectDto(
                    object_id=2,
                    object_type="PLAYER",
                    x=1,
                    y=0,
                    z=0,
                    distance=1,
                    object_kind="player",
                    is_self=False,
                )
            ]
        )
        assert resolver.is_available(ctx) is True

    def test_available_when_monster_visible(self):
        resolver = PursuitStartAvailabilityResolver()
        ctx = _minimal_current_state(
            visible_objects=[
                VisibleObjectDto(
                    object_id=3,
                    object_type="MONSTER",
                    x=1,
                    y=0,
                    z=0,
                    distance=1,
                    object_kind="monster",
                    is_self=False,
                )
            ]
        )
        assert resolver.is_available(ctx) is True

    def test_not_available_when_visible_objects_none(self):
        """visible_objects が None のとき TypeError を避けて False を返す"""
        resolver = PursuitStartAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.visible_objects = None  # type: ignore[assignment]
        assert resolver.is_available(ctx) is False


class TestPursuitCancelAvailabilityResolver:
    """PursuitCancelAvailabilityResolver の境界・正常"""

    def test_not_available_when_context_none(self):
        resolver = PursuitCancelAvailabilityResolver()
        assert resolver.is_available(None) is False

    def test_available_when_context_present(self):
        resolver = PursuitCancelAvailabilityResolver()
        ctx = _minimal_current_state()
        assert resolver.is_available(ctx) is True


class TestWhisperVisibilityNone:
    """WhisperAvailabilityResolver の visible_objects=None 防御"""

    def test_not_available_when_visible_objects_none(self):
        """visible_objects が None のとき TypeError を避けて False を返す"""
        resolver = WhisperAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.visible_objects = None  # type: ignore[assignment]
        assert resolver.is_available(ctx) is False


class TestExtendedAvailabilityResolvers:
    def test_change_attention_available_when_options_exist(self):
        resolver = ChangeAttentionAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.attention_level_options = [AttentionLevelOptionDto("FULL", "フル", "すべて")]
        assert resolver.is_available(ctx) is True

    def test_conversation_advance_available_when_active_conversation_exists(self):
        resolver = ConversationAdvanceAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.active_conversation = ActiveConversationDto(
            npc_world_object_id=1,
            npc_display_name="老人",
            node_text="やあ",
            choices=[ConversationChoiceDto(display_text="はい", choice_index=0)],
            is_terminal=False,
        )
        assert resolver.is_available(ctx) is True

    def test_place_object_available_when_placeable_inventory_exists(self):
        resolver = PlaceObjectAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.inventory_items = [InventoryItemDto(0, 1, "木箱", 1, is_placeable=True)]
        assert resolver.is_available(ctx) is True

    def test_destroy_placeable_available_when_flag_true(self):
        resolver = DestroyPlaceableAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.can_destroy_placeable = True
        assert resolver.is_available(ctx) is True

    def test_chest_store_available_with_open_chest_and_inventory(self):
        resolver = ChestStoreAvailabilityResolver()
        ctx = _minimal_current_state(
            visible_objects=[
                VisibleObjectDto(
                    object_id=2,
                    object_type="CHEST",
                    x=1,
                    y=0,
                    z=0,
                    distance=1,
                    object_kind="chest",
                    can_store_in_chest=True,
                    available_interactions=["store_in_chest"],
                )
            ]
        )
        ctx.inventory_items = [InventoryItemDto(0, 1, "木箱", 1)]
        assert resolver.is_available(ctx) is True

    def test_combat_use_skill_available_when_usable_skill_exists(self):
        resolver = CombatUseSkillAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.usable_skills = [UsableSkillDto(10, 1, 100, "火球")]
        assert resolver.is_available(ctx) is True

    def test_inspect_item_not_available_when_context_none(self):
        resolver = InspectItemAvailabilityResolver()
        assert resolver.is_available(None) is False

    def test_inspect_item_not_available_when_no_inventory(self):
        resolver = InspectItemAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.inventory_items = []
        assert resolver.is_available(ctx) is False

    def test_inspect_item_available_when_has_inventory_items(self):
        resolver = InspectItemAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.inventory_items = [InventoryItemDto(0, 1, "木箱", 1)]
        assert resolver.is_available(ctx) is True

    def test_inspect_target_not_available_when_context_none(self):
        resolver = InspectTargetAvailabilityResolver()
        assert resolver.is_available(None) is False

    def test_inspect_target_not_available_when_no_actionable_objects(self):
        resolver = InspectTargetAvailabilityResolver()
        ctx = _minimal_current_state(visible_objects=[])
        assert resolver.is_available(ctx) is False

    def test_inspect_target_available_when_interactable_object_exists(self):
        resolver = InspectTargetAvailabilityResolver()
        ctx = _minimal_current_state(
            visible_objects=[
                VisibleObjectDto(
                    object_id=2,
                    object_type="CHEST",
                    x=1,
                    y=0,
                    z=0,
                    distance=1,
                    object_kind="chest",
                    can_interact=True,
                    available_interactions=["interact"],
                )
            ]
        )
        assert resolver.is_available(ctx) is True

    def test_inspect_target_available_when_harvestable_object_exists(self):
        resolver = InspectTargetAvailabilityResolver()
        ctx = _minimal_current_state(
            visible_objects=[
                VisibleObjectDto(
                    object_id=3,
                    object_type="RESOURCE",
                    x=1,
                    y=0,
                    z=0,
                    distance=1,
                    object_kind="resource",
                    can_harvest=True,
                    available_interactions=["harvest"],
                )
            ]
        )
        assert resolver.is_available(ctx) is True


class TestGuildCreateAvailabilityResolver:
    """GuildCreateAvailabilityResolver のテスト"""

    def test_not_available_when_context_none(self):
        resolver = GuildCreateAvailabilityResolver()
        assert resolver.is_available(None) is False

    def test_not_available_when_area_ids_empty(self):
        resolver = GuildCreateAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.area_ids = []
        assert resolver.is_available(ctx) is False

    def test_not_available_when_already_in_guild(self):
        resolver = GuildCreateAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.area_ids = [10]
        ctx.guild_memberships = [GuildMembershipSummaryDto(1, "テスト", "leader")]
        assert resolver.is_available(ctx) is False

    def test_available_when_no_guild_and_has_area_ids(self):
        resolver = GuildCreateAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.area_ids = [10]
        ctx.guild_memberships = []
        assert resolver.is_available(ctx) is True


class TestGuildDisbandAvailabilityResolver:
    """GuildDisbandAvailabilityResolver のテスト"""

    def test_not_available_when_no_leader(self):
        resolver = GuildDisbandAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.guild_memberships = [GuildMembershipSummaryDto(1, "テスト", "member")]
        assert resolver.is_available(ctx) is False

    def test_available_when_leader(self):
        resolver = GuildDisbandAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.guild_memberships = [GuildMembershipSummaryDto(1, "テスト", "leader")]
        assert resolver.is_available(ctx) is True


class TestSkillAvailabilityResolvers:
    def test_skill_equip_available_when_candidates_and_slots_exist(self):
        resolver = SkillEquipAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.equipable_skill_candidates = [
            EquipableSkillCandidateDto(10, 1001, "火球", DeckTier.NORMAL)
        ]
        ctx.skill_equip_slots = [
            SkillEquipSlotDto(10, DeckTier.NORMAL, 0, "通常スロット 1")
        ]

        assert resolver.is_available(ctx) is True

    def test_skill_equip_not_available_when_missing_slots(self):
        resolver = SkillEquipAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.equipable_skill_candidates = [
            EquipableSkillCandidateDto(10, 1001, "火球", DeckTier.NORMAL)
        ]
        ctx.skill_equip_slots = []

        assert resolver.is_available(ctx) is False

    def test_skill_proposal_resolvers_follow_pending_proposals_presence(self):
        accept_resolver = SkillAcceptProposalAvailabilityResolver()
        reject_resolver = SkillRejectProposalAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.pending_skill_proposals = [
            PendingSkillProposalDto(
                progress_id=20,
                proposal_id=1,
                offered_skill_id=3001,
                display_name="3001: 新しい攻撃手段",
                proposal_type=SkillProposalType.ADD,
                deck_tier=DeckTier.NORMAL,
            )
        ]

        assert accept_resolver.is_available(ctx) is True
        assert reject_resolver.is_available(ctx) is True

    def test_awakened_mode_availability_requires_action_label(self):
        resolver = SkillActivateAwakenedModeAvailabilityResolver()
        ctx = _minimal_current_state()
        assert resolver.is_available(ctx) is False

        ctx.awakened_action = AwakenedActionDto(
            skill_loadout_id=10,
            display_name="覚醒モードを発動",
        )
        assert resolver.is_available(ctx) is True
