"""DefaultToolArgumentResolver のテスト。"""

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    ActiveHarvestToolRuntimeTargetDto,
    AttentionLevelToolRuntimeTargetDto,
    AwakenedActionToolRuntimeTargetDto,
    ChestItemToolRuntimeTargetDto,
    ChestToolRuntimeTargetDto,
    ConversationChoiceToolRuntimeTargetDto,
    DestinationToolRuntimeTargetDto,
    GuildToolRuntimeTargetDto,
    InventoryToolRuntimeTargetDto,
    MonsterToolRuntimeTargetDto,
    NpcToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ResourceToolRuntimeTargetDto,
    ShopListingToolRuntimeTargetDto,
    ShopToolRuntimeTargetDto,
    SkillEquipCandidateToolRuntimeTargetDto,
    SkillEquipSlotToolRuntimeTargetDto,
    SkillProposalToolRuntimeTargetDto,
    SkillToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    TradeToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services.tool_argument_resolver import (
    DefaultToolArgumentResolver,
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CHANGE_ATTENTION,
    TOOL_NAME_CANCEL_MOVEMENT,
    TOOL_NAME_CHEST_STORE,
    TOOL_NAME_CHEST_TAKE,
    TOOL_NAME_COMBAT_USE_SKILL,
    TOOL_NAME_CONVERSATION_ADVANCE,
    TOOL_NAME_DESTROY_PLACEABLE,
    TOOL_NAME_DROP_ITEM,
    TOOL_NAME_GUILD_ADD_MEMBER,
    TOOL_NAME_GUILD_CHANGE_ROLE,
    TOOL_NAME_GUILD_CREATE,
    TOOL_NAME_GUILD_DEPOSIT_BANK,
    TOOL_NAME_GUILD_DISBAND,
    TOOL_NAME_HARVEST_CANCEL,
    TOOL_NAME_HARVEST_START,
    TOOL_NAME_INSPECT_ITEM,
    TOOL_NAME_INSPECT_TARGET,
    TOOL_NAME_INTERACT_WORLD_OBJECT,
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_NO_OP,
    TOOL_NAME_PLACE_OBJECT,
    TOOL_NAME_PURSUIT_CANCEL,
    TOOL_NAME_PURSUIT_START,
    TOOL_NAME_QUEST_ISSUE,
    TOOL_NAME_SAY,
    TOOL_NAME_SHOP_LIST_ITEM,
    TOOL_NAME_SKILL_ACCEPT_PROPOSAL,
    TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE,
    TOOL_NAME_SKILL_EQUIP,
    TOOL_NAME_SKILL_REJECT_PROPOSAL,
    TOOL_NAME_TRADE_OFFER,
    TOOL_NAME_WHISPER,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier


def _make_context() -> ToolRuntimeContextDto:
    return ToolRuntimeContextDto(
        targets={
            "S1": DestinationToolRuntimeTargetDto(
                label="S1",
                kind="destination",
                display_name="港町",
                spot_id=2,
                destination_type="spot",
            ),
            "L1": DestinationToolRuntimeTargetDto(
                label="L1",
                kind="destination",
                display_name="ギルドエリア",
                spot_id=1,
                location_area_id=10,
                destination_type="location",
            ),
            "D1": DestinationToolRuntimeTargetDto(
                label="D1",
                kind="destination",
                display_name="老人",
                spot_id=1,
                world_object_id=200,
                target_x=0,
                target_y=1,
                target_z=0,
                destination_type="object",
            ),
            "P1": PlayerToolRuntimeTargetDto(
                label="P1",
                kind="player",
                display_name="Bob",
                player_id=2,
                world_object_id=100,
            ),
            "N1": NpcToolRuntimeTargetDto(
                label="N1",
                kind="npc",
                display_name="老人",
                world_object_id=200,
            ),
            "O2": ChestToolRuntimeTargetDto(
                label="O2",
                kind="chest",
                display_name="宝箱",
                world_object_id=210,
            ),
            "O1": ResourceToolRuntimeTargetDto(
                label="O1",
                kind="resource",
                display_name="薬草",
                world_object_id=300,
            ),
            "H1": ActiveHarvestToolRuntimeTargetDto(
                label="H1",
                kind="active_harvest",
                display_name="薬草",
                world_object_id=300,
            ),
            "I1": InventoryToolRuntimeTargetDto(
                label="I1",
                kind="inventory_item",
                display_name="木箱",
                item_instance_id=400,
                inventory_slot_id=2,
                is_placeable=True,
                available_interactions=("place_object",),
            ),
            "C1": ChestItemToolRuntimeTargetDto(
                label="C1",
                kind="chest_item",
                display_name="ポーション",
                item_instance_id=500,
                chest_world_object_id=210,
            ),
            "R1": ConversationChoiceToolRuntimeTargetDto(
                label="R1",
                kind="conversation_choice",
                display_name="はい",
                world_object_id=200,
                conversation_choice_index=0,
            ),
            "K1": SkillToolRuntimeTargetDto(
                label="K1",
                kind="skill",
                display_name="火球",
                skill_loadout_id=10,
                skill_slot_index=1,
            ),
            "EK1": SkillEquipCandidateToolRuntimeTargetDto(
                label="EK1",
                kind="skill_equip_candidate",
                display_name="火球",
                skill_loadout_id=10,
                skill_id=1001,
            ),
            "ES1": SkillEquipSlotToolRuntimeTargetDto(
                label="ES1",
                kind="skill_equip_slot",
                display_name="通常スロット 1",
                skill_loadout_id=10,
                deck_tier=DeckTier.NORMAL,
                skill_slot_index=0,
            ),
            "SP1": SkillProposalToolRuntimeTargetDto(
                label="SP1",
                kind="skill_proposal",
                display_name="新しい攻撃手段",
                progress_id=20,
                proposal_id=2,
                target_slot_index=0,
                target_slot_display_name="通常スロット 1",
            ),
            "AW1": AwakenedActionToolRuntimeTargetDto(
                label="AW1",
                kind="awakened_action",
                display_name="覚醒モードを発動",
                skill_loadout_id=10,
            ),
            "A1": AttentionLevelToolRuntimeTargetDto(
                label="A1",
                kind="attention_level",
                display_name="フル",
                attention_level_value="FULL",
            ),
        }
    )


class TestDefaultToolArgumentResolver:
    def test_resolve_move_destination_label(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_MOVE_TO_DESTINATION,
            {"destination_label": "S1"},
            _make_context(),
        )

        assert result == {
            "destination_type": "spot",
            "target_spot_id": 2,
            "target_location_area_id": None,
        }

    def test_resolve_move_destination_location_label(self):
        """destination_label が L1（ロケーション）のとき destination_type=location, target_location_area_id が解決される"""
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_MOVE_TO_DESTINATION,
            {"destination_label": "L1"},
            _make_context(),
        )

        assert result["destination_type"] == "location"
        assert result["target_spot_id"] == 1
        assert result["target_location_area_id"] == 10

    def test_resolve_move_destination_object_label(self):
        """destination_label が D1（オブジェクト）のとき destination_type=object, target_world_object_id が解決される"""
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_MOVE_TO_DESTINATION,
            {"destination_label": "D1"},
            _make_context(),
        )

        assert result["destination_type"] == "object"
        assert result["target_spot_id"] == 1
        assert result["target_world_object_id"] == 200

    def test_resolve_whisper_target_label(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_WHISPER,
            {"target_label": "P1", "content": "こんにちは"},
            _make_context(),
        )

        assert result["target_player_id"] == 2
        assert result["content"] == "こんにちは"
        assert result["channel"] == SpeechChannel.WHISPER

    def test_resolve_pursuit_start_player_label(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_PURSUIT_START,
            {"target_label": "P1"},
            _make_context(),
        )

        assert result["target_world_object_id"] == 100

    def test_resolve_pursuit_start_monster_label(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_PURSUIT_START,
            {"target_label": "M1"},
            ToolRuntimeContextDto(
                targets={
                    **_make_context().targets,
                    "M1": MonsterToolRuntimeTargetDto(
                        label="M1",
                        kind="monster",
                        display_name="スライム",
                        world_object_id=301,
                    ),
                }
            ),
        )

        assert result["target_world_object_id"] == 301

    def test_resolve_pursuit_cancel_returns_empty_args(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_PURSUIT_CANCEL,
            {},
            _make_context(),
        )

        assert result == {}

    def test_resolve_cancel_movement_returns_empty_args(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_CANCEL_MOVEMENT,
            {},
            _make_context(),
        )

        assert result == {}

    def test_resolve_move_unknown_label_raises(self):
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_MOVE_TO_DESTINATION,
                {"destination_label": "S9"},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_DESTINATION_LABEL"

    def test_resolve_say_sets_say_channel(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_SAY,
            {"content": "やあ"},
            _make_context(),
        )

        assert result["content"] == "やあ"
        assert result["channel"] == SpeechChannel.SAY

    def test_resolve_interact_target_label(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_INTERACT_WORLD_OBJECT,
            {"target_label": "N1"},
            _make_context(),
        )

        assert result["target_world_object_id"] == 200

    def test_resolve_skill_equip_from_action_first_labels(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_SKILL_EQUIP,
            {"skill_label": "EK1", "slot_label": "ES1"},
            _make_context(),
        )

        assert result == {
            "loadout_id": 10,
            "deck_tier": DeckTier.NORMAL,
            "slot_index": 0,
            "skill_id": 1001,
            "skill_display_name": "火球",
            "slot_display_name": "通常スロット 1",
        }

    def test_resolve_skill_equip_rejects_mismatched_label_kind(self):
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_SKILL_EQUIP,
                {"skill_label": "K1", "slot_label": "ES1"},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_KIND"

    def test_resolve_skill_proposal_for_accept_and_reject(self):
        resolver = DefaultToolArgumentResolver()

        accepted = resolver.resolve(
            TOOL_NAME_SKILL_ACCEPT_PROPOSAL,
            {"proposal_label": "SP1"},
            _make_context(),
        )
        rejected = resolver.resolve(
            TOOL_NAME_SKILL_REJECT_PROPOSAL,
            {"proposal_label": "SP1"},
            _make_context(),
        )

        assert accepted == {
            "progress_id": 20,
            "proposal_id": 2,
            "proposal_display_name": "新しい攻撃手段",
            "slot_display_name": "通常スロット 1",
        }
        assert rejected == {
            "progress_id": 20,
            "proposal_id": 2,
            "proposal_display_name": "新しい攻撃手段",
            "slot_display_name": "通常スロット 1",
        }

    def test_resolve_activate_awakened_mode_without_numeric_payload(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE,
            {"awakened_action_label": "AW1"},
            _make_context(),
        )

        assert result == {"loadout_id": 10}

    def test_resolve_harvest_target_label(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_HARVEST_START,
            {"target_label": "O1"},
            _make_context(),
        )

        assert result["target_world_object_id"] == 300
        assert result["target_display_name"] == "薬草"

    def test_resolve_harvest_cancel_target_label(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_HARVEST_CANCEL,
            {"target_label": "H1"},
            _make_context(),
        )

        assert result["target_world_object_id"] == 300
        assert result["target_display_name"] == "薬草"

    def test_resolve_change_attention_level_label(self):
        """level_label が有効なとき attention_level_value が返る"""
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_CHANGE_ATTENTION,
            {"level_label": "A1"},
            _make_context(),
        )

        assert result["attention_level_value"] == "FULL"

    def test_resolve_change_attention_empty_label_raises(self):
        """level_label が空文字のとき INVALID_TARGET_LABEL"""
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_CHANGE_ATTENTION,
                {"level_label": ""},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "指定されていません" in str(exc_info.value)

    def test_resolve_change_attention_none_label_raises(self):
        """level_label が None（args に含まれない）のとき INVALID_TARGET_LABEL"""
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_CHANGE_ATTENTION,
                {},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"

    def test_resolve_change_attention_invalid_label_raises(self):
        """level_label が候補に存在しないラベルのとき INVALID_TARGET_LABEL"""
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_CHANGE_ATTENTION,
                {"level_label": "X99"},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "候補にありません" in str(exc_info.value)

    def test_resolve_change_attention_wrong_type_label_raises(self):
        """level_label が注意レベル以外（例: プレイヤーラベル）のとき INVALID_TARGET_KIND"""
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_CHANGE_ATTENTION,
                {"level_label": "P1"},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_KIND"
        assert "使えないラベル" in str(exc_info.value)

    def test_resolve_conversation_advance_labels(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_CONVERSATION_ADVANCE,
            {"target_label": "N1", "choice_label": "R1"},
            _make_context(),
        )

        assert result["npc_world_object_id"] == 200
        assert result["choice_index"] == 0

    def test_resolve_place_object_inventory_label(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_PLACE_OBJECT,
            {"inventory_item_label": "I1"},
            _make_context(),
        )

        assert result["inventory_slot_id"] == 2

    def test_resolve_drop_item_inventory_label(self):
        """inventory_item_label が I1（在庫アイテム）のとき inventory_slot_id, target_display_name が解決される"""
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_DROP_ITEM,
            {"inventory_item_label": "I1"},
            _make_context(),
        )

        assert result["inventory_slot_id"] == 2
        assert result["target_display_name"] == "木箱"

    def test_resolve_drop_item_invalid_label_raises(self):
        """存在しない在庫ラベルのとき ToolArgumentResolutionException"""
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_DROP_ITEM,
                {"inventory_item_label": "X99"},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"

    def test_resolve_drop_item_empty_label_raises(self):
        """inventory_item_label が空文字のとき INVALID_TARGET_LABEL"""
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_DROP_ITEM,
                {"inventory_item_label": ""},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "指定されていません" in str(exc_info.value)

    def test_resolve_drop_item_none_label_raises(self):
        """inventory_item_label が None（args に含まれない）のとき INVALID_TARGET_LABEL"""
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_DROP_ITEM,
                {},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"

    def test_resolve_drop_item_inventory_slot_none_raises(self):
        """inventory_slot_id が None の在庫ラベルは捨てられないため INVALID_TARGET_KIND"""
        resolver = DefaultToolArgumentResolver()
        ctx = _make_context()
        ctx.targets["I_NO_SLOT"] = InventoryToolRuntimeTargetDto(
            label="I_NO_SLOT",
            kind="inventory_item",
            display_name="特殊アイテム",
            item_instance_id=401,
            inventory_slot_id=None,
            is_placeable=False,
            available_interactions=(),
        )
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_DROP_ITEM,
                {"inventory_item_label": "I_NO_SLOT"},
                ctx,
            )

        assert exc_info.value.error_code == "INVALID_TARGET_KIND"
        assert "捨てられない" in str(exc_info.value)

    def test_resolve_inspect_item_inventory_label(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_INSPECT_ITEM,
            {"inventory_item_label": "I1"},
            _make_context(),
        )

        assert result["item_instance_id"] == 400

    def test_resolve_inspect_target_npc_label(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_INSPECT_TARGET,
            {"target_label": "N1"},
            _make_context(),
        )

        assert result["target_world_object_id"] == 200

    def test_resolve_inspect_item_invalid_label_raises(self):
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_INSPECT_ITEM,
                {"inventory_item_label": "X99"},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"

    def test_resolve_inspect_item_empty_label_raises(self):
        """inventory_item_label が空文字のとき INVALID_TARGET_LABEL"""
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_INSPECT_ITEM,
                {"inventory_item_label": ""},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "指定されていません" in str(exc_info.value)

    def test_resolve_inspect_item_none_label_raises(self):
        """inventory_item_label が None（args に含まれない）のとき INVALID_TARGET_LABEL"""
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_INSPECT_ITEM,
                {},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"

    def test_resolve_inspect_target_invalid_label_raises(self):
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_INSPECT_TARGET,
                {"target_label": "X99"},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"

    def test_resolve_inspect_target_empty_label_raises(self):
        """target_label が空文字のとき INVALID_TARGET_LABEL"""
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_INSPECT_TARGET,
                {"target_label": ""},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "指定されていません" in str(exc_info.value)

    def test_resolve_inspect_target_none_label_raises(self):
        """target_label が None（args に含まれない）のとき INVALID_TARGET_LABEL"""
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_INSPECT_TARGET,
                {},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"

    def test_resolve_destroy_placeable_returns_empty(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_DESTROY_PLACEABLE,
            {},
            _make_context(),
        )

        assert result == {}

    def test_resolve_chest_store_labels(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_CHEST_STORE,
            {"target_label": "O2", "inventory_item_label": "I1"},
            _make_context(),
        )

        assert result["item_instance_id"] == 400

    def test_resolve_chest_take_labels(self):
        resolver = DefaultToolArgumentResolver()

        ctx = _make_context()
        result = resolver.resolve(
            TOOL_NAME_CHEST_TAKE,
            {"target_label": "O2", "chest_item_label": "C1"},
            ctx,
        )

        assert result["item_instance_id"] == 500

    def test_resolve_combat_use_skill_with_target(self):
        resolver = DefaultToolArgumentResolver()
        ctx = _make_context()
        ctx.targets["M1"] = MonsterToolRuntimeTargetDto(
            label="M1",
            kind="monster",
            display_name="ゴブリン",
            relative_dx=1,
            relative_dy=-1,
            relative_dz=0,
        )

        result = resolver.resolve(
            TOOL_NAME_COMBAT_USE_SKILL,
            {"skill_label": "K1", "target_label": "M1"},
            ctx,
        )

        assert result["skill_loadout_id"] == 10
        assert result["skill_slot_index"] == 1
        assert result["target_direction"] == "NORTHEAST"
        assert result["auto_aim"] is False

    def test_resolve_whisper_non_player_label_raises(self):
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_WHISPER,
                {"target_label": "N1", "content": "こんにちは"},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_KIND"

    def test_resolve_interact_destination_label_raises(self):
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_INTERACT_WORLD_OBJECT,
                {"target_label": "S1"},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_KIND"

    def test_resolve_harvest_non_resource_label_raises(self):
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_HARVEST_START,
                {"target_label": "N1"},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_KIND"

    def test_resolve_place_object_non_placeable_label_raises(self):
        resolver = DefaultToolArgumentResolver()
        ctx = _make_context()
        ctx.targets["I2"] = InventoryToolRuntimeTargetDto(
            label="I2",
            kind="inventory_item",
            display_name="石",
            item_instance_id=401,
            inventory_slot_id=3,
        )
        with pytest.raises(ToolArgumentResolutionException):
            resolver.resolve(
                TOOL_NAME_PLACE_OBJECT,
                {"inventory_item_label": "I2"},
                ctx,
            )


class TestDefaultToolArgumentResolverInputValidation:
    """resolve() の入力バリデーション（TypeError）"""

    def test_resolve_tool_name_not_str_raises_type_error(self):
        resolver = DefaultToolArgumentResolver()
        with pytest.raises(TypeError, match="tool_name must be str"):
            resolver.resolve(123, {}, _make_context())  # type: ignore[arg-type]

    def test_resolve_arguments_not_dict_raises_type_error(self):
        resolver = DefaultToolArgumentResolver()
        with pytest.raises(TypeError, match="arguments must be dict or None"):
            resolver.resolve(
                TOOL_NAME_NO_OP,
                "invalid",  # type: ignore[arg-type]
                _make_context(),
            )

    def test_resolve_runtime_context_invalid_raises_type_error(self):
        resolver = DefaultToolArgumentResolver()
        with pytest.raises(TypeError, match="runtime_context must be ToolRuntimeContextDto"):
            resolver.resolve(
                TOOL_NAME_NO_OP,
                {},
                None,  # type: ignore[arg-type]
            )


class TestDefaultToolArgumentResolverConversationAdvance:
    """conversation_advance の例外ケース"""

    def test_resolve_conversation_advance_target_label_none_raises(self):
        resolver = DefaultToolArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_CONVERSATION_ADVANCE,
                {},
                _make_context(),
            )
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "会話対象ラベル" in str(exc_info.value)


def _make_shop_guild_trade_context() -> ToolRuntimeContextDto:
    """ショップ・ギルド・取引テスト用の拡張コンテキスト"""
    base = _make_context()
    extra = {
        "G1": GuildToolRuntimeTargetDto(
            label="G1",
            kind="guild",
            display_name="冒険者ギルド",
            guild_id=1,
        ),
        "SH1": ShopToolRuntimeTargetDto(
            label="SH1",
            kind="shop",
            display_name="港町ショップ",
            shop_id=10,
        ),
        "SL1": ShopListingToolRuntimeTargetDto(
            label="SL1",
            kind="shop_listing",
            display_name="木箱 100G",
            shop_id=10,
            listing_id=5,
        ),
        "T1": TradeToolRuntimeTargetDto(
            label="T1",
            kind="trade",
            display_name="取引 #1",
            trade_id=100,
        ),
    }
    return ToolRuntimeContextDto(targets={**base.targets, **extra})


class TestDefaultToolArgumentResolverSafeInt:
    """_safe_int 経由の数値変換（不正値で ToolArgumentResolutionException）"""

    def test_resolve_shop_list_item_price_invalid_raises(self):
        resolver = DefaultToolArgumentResolver()
        ctx = _make_shop_guild_trade_context()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_SHOP_LIST_ITEM,
                {
                    "shop_label": "SH1",
                    "inventory_item_label": "I1",
                    "price_per_unit": "not_a_number",
                },
                ctx,
            )
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "整数" in str(exc_info.value)

    def test_resolve_trade_offer_requested_gold_invalid_raises(self):
        resolver = DefaultToolArgumentResolver()
        ctx = _make_shop_guild_trade_context()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_TRADE_OFFER,
                {
                    "inventory_item_label": "I1",
                    "requested_gold": "abc",
                },
                ctx,
            )
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "整数" in str(exc_info.value)

    def test_resolve_guild_label_amount_invalid_raises(self):
        resolver = DefaultToolArgumentResolver()
        ctx = _make_shop_guild_trade_context()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_GUILD_DEPOSIT_BANK,
                {"guild_label": "G1", "amount": "invalid"},
                ctx,
            )
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "整数" in str(exc_info.value)


class TestToolArgumentResolverGuildCreate:
    """guild_create の resolve テスト"""

    def test_resolve_guild_create_success(self):
        resolver = DefaultToolArgumentResolver()
        ctx = ToolRuntimeContextDto(
            targets={},
            current_spot_id=1,
            current_area_ids=(10, 20),
        )
        result = resolver.resolve(
            TOOL_NAME_GUILD_CREATE,
            {"name": "冒険者ギルド", "description": "一緒に冒険"},
            ctx,
        )
        assert result["spot_id"] == 1
        assert result["location_area_id"] == 10
        assert result["name"] == "冒険者ギルド"
        assert result["description"] == "一緒に冒険"

    def test_resolve_guild_create_missing_area_ids_raises(self):
        resolver = DefaultToolArgumentResolver()
        ctx = ToolRuntimeContextDto(targets={}, current_spot_id=1, current_area_ids=None)
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_GUILD_CREATE,
                {"name": "テスト"},
                ctx,
            )
        assert exc_info.value.error_code == "MISSING_CURRENT_AREA"


class TestToolArgumentResolverGuildDisband:
    """guild_disband の resolve テスト"""

    def test_resolve_guild_disband_success(self):
        resolver = DefaultToolArgumentResolver()
        ctx = _make_shop_guild_trade_context()
        result = resolver.resolve(TOOL_NAME_GUILD_DISBAND, {"guild_label": "G1"}, ctx)
        assert result["guild_id"] == 1


class TestToolArgumentResolverQuestIssue:
    """quest_issue の resolve テスト"""

    def test_resolve_quest_issue_success_public(self):
        """公開クエスト（guild_label なし）の解決"""
        resolver = DefaultToolArgumentResolver()
        ctx = ToolRuntimeContextDto(targets={})
        result = resolver.resolve(
            TOOL_NAME_QUEST_ISSUE,
            {
                "objectives": [
                    {"objective_type": "kill_monster", "target_id": 101, "required_count": 2},
                ],
                "reward_gold": 50,
            },
            ctx,
        )
        assert result["objectives"] == [("kill_monster", 101, 2)]
        assert result["reward_gold"] == 50
        assert result["reward_exp"] == 0
        assert result["reward_items"] is None
        assert result["guild_id"] is None

    def test_resolve_quest_issue_with_guild_label(self):
        """ギルド掲示クエストの解決"""
        resolver = DefaultToolArgumentResolver()
        ctx = _make_shop_guild_trade_context()
        result = resolver.resolve(
            TOOL_NAME_QUEST_ISSUE,
            {
                "objectives": [
                    {"objective_type": "talk_to_npc", "target_id": 5, "required_count": 1},
                ],
                "guild_label": "G1",
            },
            ctx,
        )
        assert result["objectives"] == [("talk_to_npc", 5, 1)]
        assert result["guild_id"] == 1

    def test_resolve_quest_issue_empty_objectives_raises(self):
        """objectives が空のとき INVALID_OBJECTIVES"""
        resolver = DefaultToolArgumentResolver()
        ctx = ToolRuntimeContextDto(targets={})
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_QUEST_ISSUE,
                {"objectives": []},
                ctx,
            )
        assert exc_info.value.error_code == "INVALID_OBJECTIVES"

    def test_resolve_quest_issue_with_reward_items(self):
        """報酬アイテム付きの解決"""
        resolver = DefaultToolArgumentResolver()
        ctx = ToolRuntimeContextDto(targets={})
        result = resolver.resolve(
            TOOL_NAME_QUEST_ISSUE,
            {
                "objectives": [
                    {"objective_type": "obtain_item", "target_id": 201, "required_count": 1},
                ],
                "reward_items": [{"item_spec_id": 301, "quantity": 2}],
            },
            ctx,
        )
        assert result["objectives"] == [("obtain_item", 201, 1)]
        assert result["reward_items"] == [(301, 2)]
