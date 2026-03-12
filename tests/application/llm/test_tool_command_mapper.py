"""ToolCommandMapper のテスト（正常・例外・失敗時 remediation）"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.tool_command_mapper import ToolCommandMapper
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CANCEL_MOVEMENT,
    TOOL_NAME_CHANGE_ATTENTION,
    TOOL_NAME_CHEST_STORE,
    TOOL_NAME_CHEST_TAKE,
    TOOL_NAME_COMBAT_USE_SKILL,
    TOOL_NAME_CONVERSATION_ADVANCE,
    TOOL_NAME_DESTROY_PLACEABLE,
    TOOL_NAME_DROP_ITEM,
    TOOL_NAME_GUILD_ADD_MEMBER,
    TOOL_NAME_GUILD_CHANGE_ROLE,
    TOOL_NAME_GUILD_CREATE,
    TOOL_NAME_GUILD_DISBAND,
    TOOL_NAME_GUILD_LEAVE,
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
    TOOL_NAME_QUEST_ACCEPT,
    TOOL_NAME_QUEST_ISSUE,
    TOOL_NAME_SAY,
    TOOL_NAME_SKILL_ACCEPT_PROPOSAL,
    TOOL_NAME_SKILL_EQUIP,
    TOOL_NAME_SKILL_REJECT_PROPOSAL,
    TOOL_NAME_SHOP_PURCHASE,
    TOOL_NAME_SUBAGENT,
    TOOL_NAME_TRADE_ACCEPT,
    TOOL_NAME_TRADE_CANCEL,
    TOOL_NAME_TRADE_OFFER,
    TOOL_NAME_TODO_ADD,
    TOOL_NAME_TODO_COMPLETE,
    TOOL_NAME_TODO_LIST,
    TOOL_NAME_WHISPER,
    TOOL_NAME_WORKING_MEMORY_APPEND,
)
from ai_rpg_world.application.speech.contracts.commands import SpeakCommand
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.application.world.contracts.dtos import (
    MoveResultDto,
    PursuitCommandResultDto,
)
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    MovementInvalidException,
    PlayerNotFoundException,
)
from ai_rpg_world.application.world.exceptions.command.pursuit_command_exception import (
    PursuitTargetNotVisibleException,
)
from ai_rpg_world.application.world.exceptions.command.place_command_exception import (
    NoItemInSlotException,
    ItemReservedForDropException,
    PlacementSpotNotFoundException,
)


class TestToolCommandMapperNoOp:
    """no_op ツールの実行"""

    @pytest.fixture
    def mapper(self):
        movement = MagicMock()
        return ToolCommandMapper(movement_service=movement)

    def test_execute_no_op_returns_success(self, mapper):
        """no_op 実行で success=True, message が返る"""
        result = mapper.execute(1, TOOL_NAME_NO_OP, {})
        assert isinstance(result, LlmCommandResultDto)
        assert result.success is True
        assert "何もしません" in result.message

    def test_execute_no_op_with_none_arguments(self, mapper):
        """arguments が None のときも no_op は成功"""
        result = mapper.execute(1, TOOL_NAME_NO_OP, None)
        assert result.success is True

    def test_execute_no_op_returns_was_no_op_true(self, mapper):
        """no_op 実行時は was_no_op=True になる"""
        result = mapper.execute(1, TOOL_NAME_NO_OP, {})
        assert result.was_no_op is True


class TestToolCommandMapperMoveToDestination:
    """move_to_destination ツールの実行（MovementApplicationService.move_to_destination を呼ぶ）"""

    @pytest.fixture
    def movement_service(self):
        return MagicMock()

    @pytest.fixture
    def mapper(self, movement_service):
        return ToolCommandMapper(movement_service=movement_service)

    def test_execute_move_to_destination_success_returns_dto(self, mapper, movement_service):
        """move_to_destination 成功時は MoveResultDto.message を message に"""
        movement_service.move_to_destination.return_value = MoveResultDto(
            success=True,
            player_id=1,
            player_name="P",
            from_spot_id=1,
            from_spot_name="A",
            to_spot_id=1,
            to_spot_name="A",
            from_coordinate={"x": 0, "y": 0, "z": 0},
            to_coordinate={"x": 0, "y": 0, "z": 0},
            moved_at=datetime.now(),
            busy_until_tick=0,
            message="目的地へ向かい始めました",
        )
        result = mapper.execute(
            1,
            TOOL_NAME_MOVE_TO_DESTINATION,
            {"destination_type": "spot", "target_spot_id": 2},
        )
        assert result.success is True
        assert result.message == "目的地へ向かい始めました"

    def test_execute_move_to_destination_invalid_destination_type_returns_failure_dto(
        self, mapper, movement_service
    ):
        """サービスが MovementInvalidException を投げたとき失敗 DTO（error_code=MOVEMENT_INVALID）"""
        movement_service.move_to_destination.side_effect = MovementInvalidException(
            "destination_type は 'spot' または 'location' で指定してください。", 1
        )
        result = mapper.execute(
            1,
            TOOL_NAME_MOVE_TO_DESTINATION,
            {"destination_type": "invalid", "target_spot_id": 2},
        )
        assert result.success is False
        assert result.error_code == "MOVEMENT_INVALID"
        assert result.remediation is not None

    def test_execute_move_to_destination_location_without_area_id_returns_failure(
        self, mapper, movement_service
    ):
        """サービスが target_location_area_id 必須で例外を投げたとき失敗 DTO"""
        movement_service.move_to_destination.side_effect = MovementInvalidException(
            "destination_type が 'location' のときは target_location_area_id が必須です。", 1
        )
        result = mapper.execute(
            1,
            TOOL_NAME_MOVE_TO_DESTINATION,
            {"destination_type": "location", "target_spot_id": 2},
        )
        assert result.success is False
        assert "target_location_area_id" in result.message or "必須" in result.message

    def test_execute_unknown_tool_returns_failure_dto(self, mapper):
        """未知のツール名なら success=False, error_code=UNKNOWN_TOOL"""
        result = mapper.execute(1, "unknown_tool", {})
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"
        assert result.remediation is not None


class TestToolCommandMapperPursuit:
    @pytest.fixture
    def movement_service(self):
        return MagicMock()

    @pytest.fixture
    def pursuit_service(self):
        service = MagicMock()
        service.start_pursuit.return_value = PursuitCommandResultDto(
            success=True,
            message="Bobの追跡を開始しました。",
            target_world_object_id=100,
            target_display_name="Bob",
        )
        service.cancel_pursuit.return_value = PursuitCommandResultDto(
            success=True,
            message="追跡を中断しました。",
        )
        return service

    @pytest.fixture
    def mapper(self, movement_service, pursuit_service):
        return ToolCommandMapper(
            movement_service=movement_service,
            pursuit_service=pursuit_service,
        )

    def test_execute_pursuit_start_success_returns_dto(self, mapper, pursuit_service):
        result = mapper.execute(
            1,
            TOOL_NAME_PURSUIT_START,
            {"target_world_object_id": 100},
        )

        assert result.success is True
        assert "追跡" in result.message
        pursuit_service.start_pursuit.assert_called_once()

    def test_execute_pursuit_start_returns_failure_dto_on_app_exception(
        self, mapper, pursuit_service
    ):
        pursuit_service.start_pursuit.side_effect = PursuitTargetNotVisibleException(1, 100)

        result = mapper.execute(
            1,
            TOOL_NAME_PURSUIT_START,
            {"target_world_object_id": 100},
        )

        assert result.success is False
        assert result.error_code == "PURSUIT_TARGET_NOT_VISIBLE"

    def test_execute_pursuit_cancel_success_returns_dto(self, mapper, pursuit_service):
        result = mapper.execute(1, TOOL_NAME_PURSUIT_CANCEL, {})

        assert result.success is True
        assert "中断" in result.message
        pursuit_service.cancel_pursuit.assert_called_once()

    def test_execute_pursuit_without_service_returns_unknown_tool(self, movement_service):
        mapper = ToolCommandMapper(movement_service=movement_service)

        result = mapper.execute(1, TOOL_NAME_PURSUIT_CANCEL, {})

        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


class TestToolCommandMapperCancelMovement:
    """cancel_movement ツールの実行"""

    @pytest.fixture
    def movement_service(self):
        return MagicMock()

    @pytest.fixture
    def mapper(self, movement_service):
        return ToolCommandMapper(movement_service=movement_service)

    def test_execute_cancel_movement_success_returns_dto(self, mapper, movement_service):
        """cancel_movement 成功時は MoveResultDto.message を message に"""
        movement_service.cancel_movement.return_value = MoveResultDto(
            success=True,
            player_id=1,
            player_name="P",
            from_spot_id=1,
            from_spot_name="A",
            to_spot_id=1,
            to_spot_name="A",
            from_coordinate={},
            to_coordinate={},
            moved_at=datetime.now(),
            busy_until_tick=0,
            message="移動を中断しました",
        )
        result = mapper.execute(1, TOOL_NAME_CANCEL_MOVEMENT, {})
        assert result.success is True
        assert "中断" in result.message
        movement_service.cancel_movement.assert_called_once()
        call_arg = movement_service.cancel_movement.call_args[0][0]
        assert call_arg.player_id == 1

    def test_execute_cancel_movement_player_not_found_returns_failure_dto(
        self, mapper, movement_service
    ):
        """PlayerNotFoundException のとき失敗 DTO（error_code=PLAYER_NOT_FOUND）"""
        movement_service.cancel_movement.side_effect = PlayerNotFoundException(999)
        result = mapper.execute(1, TOOL_NAME_CANCEL_MOVEMENT, {})
        assert result.success is False
        assert result.error_code == "PLAYER_NOT_FOUND"
        assert result.remediation is not None

    def test_execute_cancel_movement_failure_dto_returns_failure(self, mapper, movement_service):
        """サービスが success=False の DTO を返したとき失敗として扱う"""
        movement_service.cancel_movement.return_value = MoveResultDto(
            success=False,
            player_id=1,
            player_name="P",
            from_spot_id=1,
            from_spot_name="A",
            to_spot_id=1,
            to_spot_name="A",
            from_coordinate={},
            to_coordinate={},
            moved_at=datetime.now(),
            busy_until_tick=0,
            message="",
            error_message="現在地が不明です",
        )
        result = mapper.execute(1, TOOL_NAME_CANCEL_MOVEMENT, {})
        assert result.success is False
        assert "現在地が不明" in result.message

    def test_execute_cancel_movement_with_none_arguments_succeeds(self, mapper, movement_service):
        """arguments が None のときも成功する"""
        movement_service.cancel_movement.return_value = MoveResultDto(
            success=True,
            player_id=1,
            player_name="P",
            from_spot_id=1,
            from_spot_name="A",
            to_spot_id=1,
            to_spot_name="A",
            from_coordinate={},
            to_coordinate={},
            moved_at=datetime.now(),
            busy_until_tick=0,
            message="中断しました",
        )
        result = mapper.execute(1, TOOL_NAME_CANCEL_MOVEMENT, None)
        assert result.success is True


class TestToolCommandMapperValidation:
    """execute の引数バリデーション"""

    @pytest.fixture
    def mapper(self):
        return ToolCommandMapper(movement_service=MagicMock())

    def test_execute_player_id_not_int_raises_type_error(self, mapper):
        """player_id が int でないとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be int"):
            mapper.execute("1", TOOL_NAME_NO_OP, {})  # type: ignore[arg-type]

    def test_execute_player_id_zero_raises_value_error(self, mapper):
        """player_id が 0 以下のとき ValueError"""
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            mapper.execute(0, TOOL_NAME_NO_OP, {})

    def test_execute_tool_name_not_str_raises_type_error(self, mapper):
        """tool_name が str でないとき TypeError"""
        with pytest.raises(TypeError, match="tool_name must be str"):
            mapper.execute(1, 123, {})  # type: ignore[arg-type]

    def test_execute_arguments_not_dict_raises_type_error(self, mapper):
        """arguments が dict でないとき（None 以外）TypeError"""
        with pytest.raises(TypeError, match="arguments must be dict or None"):
            mapper.execute(1, TOOL_NAME_NO_OP, "{}")  # type: ignore[arg-type]

    def test_init_movement_service_no_move_to_destination_raises_type_error(self):
        """movement_service に move_to_destination が無いとき TypeError"""
        with pytest.raises(TypeError, match="move_to_destination"):
            ToolCommandMapper(movement_service=object())  # type: ignore[arg-type]

    def test_init_interaction_service_no_interact_world_object_raises_type_error(self):
        """interaction_service に interact_world_object が無いとき（object() 渡し）TypeError"""
        with pytest.raises(TypeError, match="interaction_service must have a callable interact_world_object"):
            ToolCommandMapper(
                movement_service=MagicMock(),
                interaction_service=object(),
            )

    def test_init_harvest_service_no_cancel_harvest_raises_type_error(self):
        """harvest_service に cancel_harvest_by_target が無いとき TypeError"""
        svc = MagicMock()
        del svc.cancel_harvest_by_target
        with pytest.raises(TypeError, match="cancel_harvest_by_target"):
            ToolCommandMapper(
                movement_service=MagicMock(),
                harvest_service=svc,
            )


class TestToolCommandMapperWhisper:
    @pytest.fixture
    def movement_service(self):
        return MagicMock()

    @pytest.fixture
    def speech_service(self):
        return MagicMock()

    @pytest.fixture
    def mapper(self, movement_service, speech_service):
        return ToolCommandMapper(
            movement_service=movement_service,
            speech_service=speech_service,
        )

    def test_execute_whisper_success_returns_dto(self, mapper, speech_service):
        result = mapper.execute(
            1,
            TOOL_NAME_WHISPER,
            {
                "content": "こんにちは",
                "channel": SpeechChannel.WHISPER,
                "target_player_id": 2,
            },
        )
        assert result.success is True
        assert "囁き" in result.message
        speech_service.speak.assert_called_once()
        command = speech_service.speak.call_args[0][0]
        assert isinstance(command, SpeakCommand)
        assert command.speaker_player_id == 1
        assert command.target_player_id == 2

    def test_execute_whisper_without_speech_service_returns_failure(self, movement_service):
        mapper = ToolCommandMapper(movement_service=movement_service)
        result = mapper.execute(
            1,
            TOOL_NAME_WHISPER,
            {
                "content": "こんにちは",
                "channel": SpeechChannel.WHISPER,
                "target_player_id": 2,
            },
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


class TestToolCommandMapperSay:
    @pytest.fixture
    def speech_service(self):
        return MagicMock()

    @pytest.fixture
    def mapper(self, speech_service):
        return ToolCommandMapper(
            movement_service=MagicMock(),
            speech_service=speech_service,
        )

    def test_execute_say_success_returns_dto(self, mapper, speech_service):
        result = mapper.execute(
            1,
            TOOL_NAME_SAY,
            {
                "content": "こんにちは",
                "channel": SpeechChannel.SAY,
            },
        )
        assert result.success is True
        assert "発言" in result.message
        speech_service.speak.assert_called_once()


class TestToolCommandMapperInteract:
    @pytest.fixture
    def interaction_service(self):
        return MagicMock()

    @pytest.fixture
    def mapper(self, interaction_service):
        return ToolCommandMapper(
            movement_service=MagicMock(),
            interaction_service=interaction_service,
        )

    def test_execute_interact_success_returns_dto(self, mapper, interaction_service):
        result = mapper.execute(
            1,
            TOOL_NAME_INTERACT_WORLD_OBJECT,
            {"target_world_object_id": 200, "target_display_name": "老人"},
        )
        assert result.success is True
        assert "老人" in result.message
        interaction_service.interact_world_object.assert_called_once()

    def test_execute_interact_without_service_returns_failure(self):
        mapper = ToolCommandMapper(movement_service=MagicMock())
        result = mapper.execute(
            1,
            TOOL_NAME_INTERACT_WORLD_OBJECT,
            {"target_world_object_id": 200},
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


class TestToolCommandMapperHarvest:
    @pytest.fixture
    def harvest_service(self):
        return MagicMock()

    @pytest.fixture
    def mapper(self, harvest_service):
        return ToolCommandMapper(
            movement_service=MagicMock(),
            harvest_service=harvest_service,
        )

    def test_execute_harvest_start_success_returns_dto(self, mapper, harvest_service):
        harvest_service.start_harvest_by_target.return_value = MagicMock(
            success=True,
            message="採集を開始しました",
        )
        result = mapper.execute(
            1,
            TOOL_NAME_HARVEST_START,
            {"target_world_object_id": 300},
        )
        assert result.success is True
        assert result.message == "採集を開始しました"
        harvest_service.start_harvest_by_target.assert_called_once_with(
            player_id=1,
            target_world_object_id=300,
        )

    def test_execute_harvest_cancel_success_returns_dto(self, mapper, harvest_service):
        harvest_service.cancel_harvest_by_target.return_value = MagicMock(
            success=True,
            message="採集を中断しました",
        )
        result = mapper.execute(
            1,
            TOOL_NAME_HARVEST_CANCEL,
            {"target_world_object_id": 300},
        )
        assert result.success is True
        assert result.message == "採集を中断しました"
        harvest_service.cancel_harvest_by_target.assert_called_once_with(
            player_id=1,
            target_world_object_id=300,
        )

    def test_execute_harvest_without_service_returns_failure(self):
        mapper = ToolCommandMapper(movement_service=MagicMock())
        result = mapper.execute(
            1,
            TOOL_NAME_HARVEST_START,
            {"target_world_object_id": 300},
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


class TestToolCommandMapperExtendedTools:
    @pytest.fixture
    def attention_service(self):
        return MagicMock()

    @pytest.fixture
    def conversation_service(self):
        svc = MagicMock()
        svc.advance_conversation.return_value = MagicMock(success=True, message="会話を進めました")
        return svc

    @pytest.fixture
    def place_object_service(self):
        return MagicMock()

    @pytest.fixture
    def chest_service(self):
        return MagicMock()

    @pytest.fixture
    def skill_tool_service(self):
        return MagicMock()

    @pytest.fixture
    def mapper(
        self,
        attention_service,
        conversation_service,
        place_object_service,
        chest_service,
        skill_tool_service,
    ):
        return ToolCommandMapper(
            movement_service=MagicMock(),
            attention_service=attention_service,
            conversation_service=conversation_service,
            place_object_service=place_object_service,
            chest_service=chest_service,
            skill_tool_service=skill_tool_service,
        )

    def test_execute_change_attention_success(self, mapper, attention_service):
        result = mapper.execute(
            1,
            TOOL_NAME_CHANGE_ATTENTION,
            {"attention_level_value": "FULL"},
        )
        assert result.success is True
        attention_service.change_attention_level.assert_called_once()

    def test_execute_conversation_advance_success(self, mapper, conversation_service):
        result = mapper.execute(
            1,
            TOOL_NAME_CONVERSATION_ADVANCE,
            {"npc_world_object_id": 200, "choice_index": 0},
        )
        assert result.success is True
        conversation_service.advance_conversation.assert_called_once()

    def test_execute_place_object_success(self, mapper, place_object_service):
        result = mapper.execute(
            1,
            TOOL_NAME_PLACE_OBJECT,
            {"inventory_slot_id": 2, "target_display_name": "木箱"},
        )
        assert result.success is True
        assert "木箱" in result.message
        place_object_service.place_from_inventory_slot.assert_called_once_with(
            player_id=1,
            inventory_slot_id=2,
        )

    def test_execute_destroy_placeable_success(self, mapper, place_object_service):
        result = mapper.execute(1, TOOL_NAME_DESTROY_PLACEABLE, {})
        assert result.success is True
        place_object_service.destroy_in_front.assert_called_once_with(player_id=1)

    def test_execute_chest_store_success(self, mapper, chest_service):
        result = mapper.execute(
            1,
            TOOL_NAME_CHEST_STORE,
            {
                "chest_world_object_id": 200,
                "item_instance_id": 400,
                "chest_display_name": "宝箱",
                "item_display_name": "木箱",
            },
        )
        assert result.success is True
        chest_service.store_item_by_target.assert_called_once()

    def test_execute_chest_take_success(self, mapper, chest_service):
        result = mapper.execute(
            1,
            TOOL_NAME_CHEST_TAKE,
            {
                "chest_world_object_id": 200,
                "item_instance_id": 500,
                "chest_display_name": "宝箱",
                "item_display_name": "ポーション",
            },
        )
        assert result.success is True
        chest_service.take_item_by_target.assert_called_once()

    def test_execute_combat_use_skill_success(self, mapper, skill_tool_service):
        result = mapper.execute(
            1,
            TOOL_NAME_COMBAT_USE_SKILL,
            {
                "skill_loadout_id": 10,
                "skill_slot_index": 1,
                "target_direction": "NORTH",
                "auto_aim": False,
                "skill_display_name": "火球",
                "target_display_name": "ゴブリン",
            },
        )
        assert result.success is True
        assert "ゴブリン" in result.message
        skill_tool_service.use_skill.assert_called_once()

    def test_execute_skill_equip_success(self, mapper, skill_tool_service):
        result = mapper.execute(
            1,
            TOOL_NAME_SKILL_EQUIP,
            {
                "loadout_id": 10,
                "deck_tier": DeckTier.NORMAL,
                "slot_index": 0,
                "skill_id": 1001,
                "skill_display_name": "火球",
                "slot_display_name": "通常スロット 1",
            },
        )

        assert result.success is True
        assert result.message == "火球を通常スロット 1に装備しました。"
        skill_tool_service.equip_skill.assert_called_once_with(
            player_id=1,
            loadout_id=10,
            deck_tier=DeckTier.NORMAL,
            slot_index=0,
            skill_id=1001,
        )

    def test_execute_skill_accept_proposal_success(self, mapper, skill_tool_service):
        result = mapper.execute(
            1,
            TOOL_NAME_SKILL_ACCEPT_PROPOSAL,
            {
                "progress_id": 20,
                "proposal_id": 2,
                "proposal_display_name": "新しい攻撃手段",
                "slot_display_name": "通常スロット 1",
            },
        )

        assert result.success is True
        assert result.message == "新しい攻撃手段を受諾し、通常スロット 1に装備しました。"
        skill_tool_service.accept_skill_proposal.assert_called_once_with(
            progress_id=20,
            proposal_id=2,
        )

    def test_execute_skill_reject_proposal_success(self, mapper, skill_tool_service):
        result = mapper.execute(
            1,
            TOOL_NAME_SKILL_REJECT_PROPOSAL,
            {
                "progress_id": 20,
                "proposal_id": 3,
                "proposal_display_name": "新しい攻撃手段",
            },
        )

        assert result.success is True
        assert result.message == "新しい攻撃手段を却下しました。"
        skill_tool_service.reject_skill_proposal.assert_called_once_with(
            progress_id=20,
            proposal_id=3,
        )


class TestToolCommandMapperDropItem:
    """world_drop_item ツールの実行テスト"""

    def test_execute_drop_item_success_returns_dto(self):
        drop_service = MagicMock()
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            drop_item_service=drop_service,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_DROP_ITEM,
            {"inventory_slot_id": 0, "target_display_name": "ポーション"},
        )
        assert result.success is True
        assert "捨て" in result.message
        drop_service.drop_from_slot.assert_called_once_with(
            player_id=1,
            inventory_slot_id=0,
        )

    def test_execute_drop_item_no_item_in_slot_returns_failure_dto(self):
        drop_service = MagicMock()
        drop_service.drop_from_slot.side_effect = NoItemInSlotException(1, 0)
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            drop_item_service=drop_service,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_DROP_ITEM,
            {"inventory_slot_id": 0},
        )
        assert result.success is False
        assert result.error_code == "NO_ITEM_IN_SLOT"
        assert result.remediation is not None

    def test_execute_drop_item_reserved_returns_failure_dto(self):
        drop_service = MagicMock()
        drop_service.drop_from_slot.side_effect = ItemReservedForDropException(1, 0)
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            drop_item_service=drop_service,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_DROP_ITEM,
            {"inventory_slot_id": 0},
        )
        assert result.success is False
        assert result.error_code == "ITEM_RESERVED"
        assert result.remediation is not None

    def test_execute_drop_item_placement_spot_not_found_returns_failure_dto(self):
        """PlacementSpotNotFoundException のとき success=False, error_code=PLACEMENT_SPOT_NOT_FOUND"""
        drop_service = MagicMock()
        drop_service.drop_from_slot.side_effect = PlacementSpotNotFoundException(1, 0)
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            drop_item_service=drop_service,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_DROP_ITEM,
            {"inventory_slot_id": 0},
        )
        assert result.success is False
        assert result.error_code == "PLACEMENT_SPOT_NOT_FOUND"
        assert result.remediation is not None

    def test_execute_drop_item_without_service_returns_unknown_tool(self):
        mapper = ToolCommandMapper(movement_service=MagicMock())
        result = mapper.execute(
            1,
            TOOL_NAME_DROP_ITEM,
            {"inventory_slot_id": 0},
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"

    def test_execute_drop_item_inventory_slot_id_none_returns_invalid_target_label(self):
        """inventory_slot_id が None のとき success=False, error_code=INVALID_TARGET_LABEL"""
        drop_service = MagicMock()
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            drop_item_service=drop_service,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_DROP_ITEM,
            {},
        )
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        assert "inventory_slot_id" in result.message
        drop_service.drop_from_slot.assert_not_called()

    def test_execute_drop_item_inventory_slot_id_invalid_type_returns_invalid_target_label(self):
        """inventory_slot_id が不正な型のとき success=False, error_code=INVALID_TARGET_LABEL"""
        drop_service = MagicMock()
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            drop_item_service=drop_service,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_DROP_ITEM,
            {"inventory_slot_id": "abc"},
        )
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        drop_service.drop_from_slot.assert_not_called()

    def test_execute_drop_item_inventory_slot_id_negative_returns_invalid_target_label(self):
        """inventory_slot_id が負のとき success=False, error_code=INVALID_TARGET_LABEL"""
        drop_service = MagicMock()
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            drop_item_service=drop_service,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_DROP_ITEM,
            {"inventory_slot_id": -1},
        )
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        drop_service.drop_from_slot.assert_not_called()


class TestToolCommandMapperInspectItem:
    """world_inspect_item ツールの実行テスト"""

    @pytest.fixture
    def item_repository(self):
        repo = MagicMock()
        item = MagicMock()
        item.item_spec.description = " magical potion."
        repo.find_by_id.return_value = item
        return repo

    @pytest.fixture
    def mapper(self, item_repository):
        return ToolCommandMapper(
            movement_service=MagicMock(),
            item_repository=item_repository,
        )

    def test_execute_inspect_item_success_returns_description(self, mapper, item_repository):
        """item_repository がアイテムを返すとき、description が message に含まれる"""
        result = mapper.execute(
            1,
            TOOL_NAME_INSPECT_ITEM,
            {"item_instance_id": 400},
        )
        assert result.success is True
        assert " magical potion." in result.message
        item_repository.find_by_id.assert_called_once()

    def test_execute_inspect_item_not_found_returns_failure(self, item_repository):
        """アイテムが存在しないとき success=False, error_code=ITEM_NOT_FOUND"""
        item_repository.find_by_id.return_value = None
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            item_repository=item_repository,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_INSPECT_ITEM,
            {"item_instance_id": 999},
        )
        assert result.success is False
        assert result.error_code == "ITEM_NOT_FOUND"
        assert result.remediation is not None

    def test_execute_inspect_item_without_repo_returns_failure(self):
        """item_repository が None のとき success=False"""
        mapper = ToolCommandMapper(movement_service=MagicMock())
        result = mapper.execute(
            1,
            TOOL_NAME_INSPECT_ITEM,
            {"item_instance_id": 400},
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"

    def test_execute_inspect_item_missing_item_instance_id_returns_invalid_target_label(
        self, item_repository
    ):
        """item_instance_id が省略（None）のとき success=False, error_code=INVALID_TARGET_LABEL"""
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            item_repository=item_repository,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_INSPECT_ITEM,
            {},
        )
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        assert result.remediation is not None
        item_repository.find_by_id.assert_not_called()

    def test_execute_inspect_item_invalid_item_instance_id_type_returns_invalid_target_label(
        self, item_repository
    ):
        """item_instance_id が不正な型（文字列 "abc"）のとき success=False, error_code=INVALID_TARGET_LABEL"""
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            item_repository=item_repository,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_INSPECT_ITEM,
            {"item_instance_id": "abc"},
        )
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        assert "正の整数" in result.message
        item_repository.find_by_id.assert_not_called()

    def test_execute_inspect_item_zero_item_instance_id_returns_invalid_target_label(
        self, item_repository
    ):
        """item_instance_id が 0 のとき success=False, error_code=INVALID_TARGET_LABEL"""
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            item_repository=item_repository,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_INSPECT_ITEM,
            {"item_instance_id": 0},
        )
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        item_repository.find_by_id.assert_not_called()

    def test_execute_inspect_item_negative_item_instance_id_returns_invalid_target_label(
        self, item_repository
    ):
        """item_instance_id が負のとき success=False, error_code=INVALID_TARGET_LABEL"""
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            item_repository=item_repository,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_INSPECT_ITEM,
            {"item_instance_id": -1},
        )
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        item_repository.find_by_id.assert_not_called()


class TestToolCommandMapperInspectTarget:
    """world_inspect_target ツールの実行テスト"""

    @pytest.fixture
    def monster_repository(self):
        repo = MagicMock()
        monster = MagicMock()
        monster.template.description = "A fierce goblin warrior."
        repo.find_by_world_object_id.return_value = monster
        return repo

    @pytest.fixture
    def player_status_repository(self):
        repo = MagicMock()
        status = MagicMock()
        status.current_spot_id = MagicMock()
        status.current_spot_id.value = 1
        status.current_spot_id.__int__ = lambda _: 1
        repo.find_by_id.return_value = status
        return repo

    @pytest.fixture
    def physical_map_repository(self):
        repo = MagicMock()
        physical_map = MagicMock()
        obj = MagicMock()
        obj.interaction_data = {"description": "A wooden door."}
        physical_map.get_object.return_value = obj
        repo.find_by_spot_id.return_value = physical_map
        return repo

    @pytest.fixture
    def mapper(self, monster_repository, player_status_repository, physical_map_repository):
        return ToolCommandMapper(
            movement_service=MagicMock(),
            monster_repository=monster_repository,
            physical_map_repository=physical_map_repository,
            player_status_repository=player_status_repository,
        )

    def test_execute_inspect_target_monster_returns_description(self, mapper, monster_repository):
        """Monster が見つかったとき template.description を返す"""
        result = mapper.execute(
            1,
            TOOL_NAME_INSPECT_TARGET,
            {"target_world_object_id": 200},
        )
        assert result.success is True
        assert "fierce goblin warrior" in result.message
        monster_repository.find_by_world_object_id.assert_called_once()

    def test_execute_inspect_target_object_when_monster_not_found(self, mapper, monster_repository, physical_map_repository):
        """Monster で見つからず、physical_map の object から description を取得"""
        monster_repository.find_by_world_object_id.return_value = None
        result = mapper.execute(
            1,
            TOOL_NAME_INSPECT_TARGET,
            {"target_world_object_id": 210},
        )
        assert result.success is True
        assert "wooden door" in result.message

    def test_execute_inspect_target_without_repos_returns_failure(self):
        """必要な repository が None のとき success=False"""
        mapper = ToolCommandMapper(movement_service=MagicMock())
        result = mapper.execute(
            1,
            TOOL_NAME_INSPECT_TARGET,
            {"target_world_object_id": 200},
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"

    def test_execute_inspect_target_missing_target_world_object_id_returns_invalid_target_label(
        self, monster_repository, player_status_repository, physical_map_repository
    ):
        """target_world_object_id が省略（None）のとき success=False, error_code=INVALID_TARGET_LABEL"""
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            monster_repository=monster_repository,
            physical_map_repository=physical_map_repository,
            player_status_repository=player_status_repository,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_INSPECT_TARGET,
            {},
        )
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        assert result.remediation is not None
        monster_repository.find_by_world_object_id.assert_not_called()

    def test_execute_inspect_target_invalid_target_world_object_id_type_returns_invalid_target_label(
        self, monster_repository, player_status_repository, physical_map_repository
    ):
        """target_world_object_id が不正な型（文字列 "xyz"）のとき success=False, error_code=INVALID_TARGET_LABEL"""
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            monster_repository=monster_repository,
            physical_map_repository=physical_map_repository,
            player_status_repository=player_status_repository,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_INSPECT_TARGET,
            {"target_world_object_id": "xyz"},
        )
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        assert "正の整数" in result.message
        monster_repository.find_by_world_object_id.assert_not_called()

    def test_execute_inspect_target_zero_target_world_object_id_returns_invalid_target_label(
        self, monster_repository, player_status_repository, physical_map_repository
    ):
        """target_world_object_id が 0 のとき success=False, error_code=INVALID_TARGET_LABEL"""
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            monster_repository=monster_repository,
            physical_map_repository=physical_map_repository,
            player_status_repository=player_status_repository,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_INSPECT_TARGET,
            {"target_world_object_id": 0},
        )
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        monster_repository.find_by_world_object_id.assert_not_called()

    def test_execute_inspect_target_object_not_found_returns_target_not_found(
        self, monster_repository, player_status_repository, physical_map_repository
    ):
        """physical_map.get_object が ObjectNotFoundException を投げるとき success=False, error_code=TARGET_NOT_FOUND"""
        from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException

        monster_repository.find_by_world_object_id.return_value = None
        physical_map = MagicMock()
        physical_map.get_object.side_effect = ObjectNotFoundException("not found")
        physical_map_repository.find_by_spot_id.return_value = physical_map
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            monster_repository=monster_repository,
            physical_map_repository=physical_map_repository,
            player_status_repository=player_status_repository,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_INSPECT_TARGET,
            {"target_world_object_id": 999},
        )
        assert result.success is False
        assert result.error_code == "TARGET_NOT_FOUND"
        assert result.remediation is not None

    def test_execute_inspect_target_player_status_none_returns_target_not_found(
        self, monster_repository, player_status_repository, physical_map_repository
    ):
        """player_status が None のとき success=False, error_code=TARGET_NOT_FOUND"""
        player_status_repository.find_by_id.return_value = None
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            monster_repository=monster_repository,
            physical_map_repository=physical_map_repository,
            player_status_repository=player_status_repository,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_INSPECT_TARGET,
            {"target_world_object_id": 200},
        )
        assert result.success is False
        assert result.error_code == "TARGET_NOT_FOUND"
        monster_repository.find_by_world_object_id.assert_not_called()

    def test_execute_inspect_target_player_current_spot_id_none_returns_target_not_found(
        self, monster_repository, player_status_repository, physical_map_repository
    ):
        """player_status.current_spot_id が None のとき success=False, error_code=TARGET_NOT_FOUND"""
        status = MagicMock()
        status.current_spot_id = None
        player_status_repository.find_by_id.return_value = status
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            monster_repository=monster_repository,
            physical_map_repository=physical_map_repository,
            player_status_repository=player_status_repository,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_INSPECT_TARGET,
            {"target_world_object_id": 200},
        )
        assert result.success is False
        assert result.error_code == "TARGET_NOT_FOUND"

    def test_execute_inspect_target_physical_map_none_returns_target_not_found(
        self, monster_repository, player_status_repository, physical_map_repository
    ):
        """physical_map_repository.find_by_spot_id が None のとき success=False, error_code=TARGET_NOT_FOUND"""
        physical_map_repository.find_by_spot_id.return_value = None
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            monster_repository=monster_repository,
            physical_map_repository=physical_map_repository,
            player_status_repository=player_status_repository,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_INSPECT_TARGET,
            {"target_world_object_id": 200},
        )
        assert result.success is False
        assert result.error_code == "TARGET_NOT_FOUND"


class TestToolCommandMapperOptionalToolsWhenNotConfigured:
    """todo_store / working_memory_store / subagent_runner が None のときのツール実行"""

    def test_todo_add_without_todo_store_returns_unknown_tool(self):
        """todo_store が None のとき todo_add は UNKNOWN_TOOL"""
        mapper = ToolCommandMapper(movement_service=MagicMock())
        result = mapper.execute(1, TOOL_NAME_TODO_ADD, {"content": "タスク"})
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"
        assert result.remediation is not None

    def test_todo_list_without_todo_store_returns_unknown_tool(self):
        """todo_store が None のとき todo_list は UNKNOWN_TOOL"""
        mapper = ToolCommandMapper(movement_service=MagicMock())
        result = mapper.execute(1, TOOL_NAME_TODO_LIST, {})
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"
        assert result.remediation is not None

    def test_todo_complete_without_todo_store_returns_unknown_tool(self):
        """todo_store が None のとき todo_complete は UNKNOWN_TOOL"""
        mapper = ToolCommandMapper(movement_service=MagicMock())
        result = mapper.execute(1, TOOL_NAME_TODO_COMPLETE, {"todo_id": "todo-1"})
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"
        assert result.remediation is not None

    def test_working_memory_append_without_working_memory_store_returns_unknown_tool(self):
        """working_memory_store が None のとき working_memory_append は UNKNOWN_TOOL"""
        mapper = ToolCommandMapper(movement_service=MagicMock())
        result = mapper.execute(1, TOOL_NAME_WORKING_MEMORY_APPEND, {"text": "メモ"})
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"
        assert result.remediation is not None

    def test_subagent_without_subagent_runner_returns_unknown_tool(self):
        """subagent_runner が None のとき subagent は UNKNOWN_TOOL"""
        mapper = ToolCommandMapper(movement_service=MagicMock())
        result = mapper.execute(
            1,
            TOOL_NAME_SUBAGENT,
            {"query": "テストクエリ", "bindings": {}},
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"
        assert result.remediation is not None


class TestToolCommandMapperGuildCreate:
    """guild_create ツールのテスト"""

    def test_execute_guild_create_success_returns_dto(self):
        guild_service = MagicMock()
        guild_service.create_guild.return_value = MagicMock(success=True, message="ギルドを作成しました。")
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            guild_service=guild_service,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_GUILD_CREATE,
            {"spot_id": 1, "location_area_id": 10, "name": "冒険者ギルド", "description": "一緒に冒険"},
        )
        assert result.success is True
        assert "作成" in result.message or result.message
        guild_service.create_guild.assert_called_once()
        cmd = guild_service.create_guild.call_args[0][0]
        assert cmd.spot_id == 1
        assert cmd.location_area_id == 10
        assert cmd.name == "冒険者ギルド"
        assert cmd.creator_player_id == 1

    def test_execute_guild_create_without_service_returns_unknown_tool(self):
        mapper = ToolCommandMapper(movement_service=MagicMock())
        result = mapper.execute(
            1,
            TOOL_NAME_GUILD_CREATE,
            {"spot_id": 1, "location_area_id": 10, "name": "テスト"},
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


class TestToolCommandMapperGuildAddMember:
    """guild_add_member ツールのテスト"""

    def test_execute_guild_add_member_success_returns_dto(self):
        guild_service = MagicMock()
        guild_service.add_member.return_value = MagicMock(success=True, message="招待しました。")
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            guild_service=guild_service,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_GUILD_ADD_MEMBER,
            {"guild_id": 10, "new_member_player_id": 2},
        )
        assert result.success is True
        guild_service.add_member.assert_called_once()
        cmd = guild_service.add_member.call_args[0][0]
        assert cmd.guild_id == 10
        assert cmd.inviter_player_id == 1
        assert cmd.new_member_player_id == 2


class TestToolCommandMapperGuildDisband:
    """guild_disband ツールのテスト"""

    def test_execute_guild_disband_success_returns_dto(self):
        guild_service = MagicMock()
        guild_service.disband_guild.return_value = MagicMock(success=True, message="ギルドを解散しました。")
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            guild_service=guild_service,
        )
        result = mapper.execute(1, TOOL_NAME_GUILD_DISBAND, {"guild_id": 10})
        assert result.success is True
        guild_service.disband_guild.assert_called_once()
        cmd = guild_service.disband_guild.call_args[0][0]
        assert cmd.guild_id == 10
        assert cmd.player_id == 1


class TestToolCommandMapperQuestIssue:
    """quest_issue ツールのテスト"""

    def test_execute_quest_issue_success_returns_dto(self):
        quest_service = MagicMock()
        quest_service.issue_quest.return_value = MagicMock(
            success=True, message="クエストを発行しました。"
        )
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            quest_service=quest_service,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_QUEST_ISSUE,
            {
                "objectives": [("kill_monster", 101, 2)],
                "reward_gold": 50,
                "reward_exp": 0,
                "reward_items": None,
                "guild_id": None,
            },
        )
        assert result.success is True
        assert "発行" in result.message
        quest_service.issue_quest.assert_called_once()
        cmd = quest_service.issue_quest.call_args[0][0]
        assert cmd.objectives == [("kill_monster", 101, 2)]
        assert cmd.reward_gold == 50
        assert cmd.issuer_player_id == 1
        assert cmd.guild_id is None

    def test_execute_quest_issue_without_service_returns_unknown_tool(self):
        mapper = ToolCommandMapper(movement_service=MagicMock())
        result = mapper.execute(
            1,
            TOOL_NAME_QUEST_ISSUE,
            {"objectives": [("kill_monster", 101, 2)]},
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


class TestToolCommandMapperRequiredArgsValidation:
    """quest / guild / shop / trade の必須引数欠如時の検証"""

    def test_quest_accept_missing_quest_id_returns_invalid_target_label(self):
        quest_service = MagicMock()
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            quest_service=quest_service,
        )
        result = mapper.execute(1, TOOL_NAME_QUEST_ACCEPT, {})
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        assert "quest_id" in result.message
        quest_service.accept_quest.assert_not_called()

    def test_quest_issue_missing_objectives_returns_invalid_arg(self):
        quest_service = MagicMock()
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            quest_service=quest_service,
        )
        result = mapper.execute(1, TOOL_NAME_QUEST_ISSUE, {})
        assert result.success is False
        assert "objectives" in result.message.lower() or "INVALID" in str(result.error_code)
        quest_service.issue_quest.assert_not_called()

    def test_guild_leave_missing_guild_id_returns_invalid_target_label(self):
        guild_service = MagicMock()
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            guild_service=guild_service,
        )
        result = mapper.execute(1, TOOL_NAME_GUILD_LEAVE, {})
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        assert "guild_id" in result.message
        guild_service.leave_guild.assert_not_called()

    def test_shop_purchase_missing_shop_id_returns_invalid_target_label(self):
        shop_service = MagicMock()
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            shop_service=shop_service,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_SHOP_PURCHASE,
            {"listing_id": 5, "quantity": 1},
        )
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        assert "shop_id" in result.message
        shop_service.purchase_from_shop.assert_not_called()

    def test_shop_purchase_missing_listing_id_returns_invalid_target_label(self):
        shop_service = MagicMock()
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            shop_service=shop_service,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_SHOP_PURCHASE,
            {"shop_id": 10, "quantity": 1},
        )
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        assert "listing_id" in result.message
        shop_service.purchase_from_shop.assert_not_called()

    def test_trade_offer_missing_item_instance_id_returns_invalid_target_label(self):
        trade_service = MagicMock()
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            trade_service=trade_service,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_TRADE_OFFER,
            {"slot_id": 0, "requested_gold": 100},
        )
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        trade_service.offer_item.assert_not_called()

    def test_trade_accept_missing_trade_id_returns_invalid_target_label(self):
        trade_service = MagicMock()
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            trade_service=trade_service,
        )
        result = mapper.execute(1, TOOL_NAME_TRADE_ACCEPT, {})
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        assert "trade_id" in result.message
        trade_service.accept_trade.assert_not_called()

    def test_guild_create_missing_spot_id_returns_invalid_target_label(self):
        guild_service = MagicMock()
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            guild_service=guild_service,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_GUILD_CREATE,
            {"location_area_id": 10, "name": "テストギルド"},
        )
        assert result.success is False
        assert "spot_id" in result.message or "INVALID" in result.error_code
        guild_service.create_guild.assert_not_called()

    def test_guild_add_member_missing_guild_id_returns_invalid_target_label(self):
        guild_service = MagicMock()
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            guild_service=guild_service,
        )
        result = mapper.execute(
            1,
            TOOL_NAME_GUILD_ADD_MEMBER,
            {"new_member_player_id": 2},
        )
        assert result.success is False
        assert "guild_id" in result.message
        guild_service.add_member.assert_not_called()

    def test_guild_disband_missing_guild_id_returns_invalid_target_label(self):
        guild_service = MagicMock()
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            guild_service=guild_service,
        )
        result = mapper.execute(1, TOOL_NAME_GUILD_DISBAND, {})
        assert result.success is False
        assert "guild_id" in result.message
        guild_service.disband_guild.assert_not_called()

    def test_trade_cancel_missing_trade_id_returns_invalid_target_label(self):
        trade_service = MagicMock()
        mapper = ToolCommandMapper(
            movement_service=MagicMock(),
            trade_service=trade_service,
        )
        result = mapper.execute(1, TOOL_NAME_TRADE_CANCEL, {})
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
        assert "trade_id" in result.message
        trade_service.cancel_trade.assert_not_called()
