"""ToolCommandMapper のテスト（正常・例外・失敗時 remediation）"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.tool_command_mapper import ToolCommandMapper
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CHANGE_ATTENTION,
    TOOL_NAME_CHEST_STORE,
    TOOL_NAME_CHEST_TAKE,
    TOOL_NAME_COMBAT_USE_SKILL,
    TOOL_NAME_CONVERSATION_ADVANCE,
    TOOL_NAME_DESTROY_PLACEABLE,
    TOOL_NAME_HARVEST_START,
    TOOL_NAME_INSPECT_ITEM,
    TOOL_NAME_INSPECT_TARGET,
    TOOL_NAME_INTERACT_WORLD_OBJECT,
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_NO_OP,
    TOOL_NAME_PLACE_OBJECT,
    TOOL_NAME_SAY,
    TOOL_NAME_WHISPER,
)
from ai_rpg_world.application.speech.contracts.commands import SpeakCommand
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.application.world.contracts.dtos import MoveResultDto
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    MovementInvalidException,
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
    def mapper(self):
        return ToolCommandMapper(
            movement_service=MagicMock(),
            speech_service=MagicMock(),
        )

    def test_execute_say_success_returns_dto(self, mapper):
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
        mapper._speech_service.speak.assert_called_once()


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
    def mapper(self):
        return ToolCommandMapper(
            movement_service=MagicMock(),
            attention_service=MagicMock(),
            conversation_service=MagicMock(),
            place_object_service=MagicMock(),
            chest_service=MagicMock(),
            skill_tool_service=MagicMock(),
        )

    def test_execute_change_attention_success(self, mapper):
        result = mapper.execute(
            1,
            TOOL_NAME_CHANGE_ATTENTION,
            {"attention_level_value": "FULL"},
        )
        assert result.success is True
        mapper._attention_service.change_attention_level.assert_called_once()

    def test_execute_conversation_advance_success(self, mapper):
        mapper._conversation_service.advance_conversation.return_value = MagicMock(
            success=True,
            message="会話を進めました",
        )
        result = mapper.execute(
            1,
            TOOL_NAME_CONVERSATION_ADVANCE,
            {"npc_world_object_id": 200, "choice_index": 0},
        )
        assert result.success is True
        mapper._conversation_service.advance_conversation.assert_called_once()

    def test_execute_place_object_success(self, mapper):
        result = mapper.execute(
            1,
            TOOL_NAME_PLACE_OBJECT,
            {"inventory_slot_id": 2, "target_display_name": "木箱"},
        )
        assert result.success is True
        assert "木箱" in result.message
        mapper._place_object_service.place_from_inventory_slot.assert_called_once_with(
            player_id=1,
            inventory_slot_id=2,
        )

    def test_execute_destroy_placeable_success(self, mapper):
        result = mapper.execute(1, TOOL_NAME_DESTROY_PLACEABLE, {})
        assert result.success is True
        mapper._place_object_service.destroy_in_front.assert_called_once_with(player_id=1)

    def test_execute_chest_store_success(self, mapper):
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
        mapper._chest_service.store_item_by_target.assert_called_once()

    def test_execute_chest_take_success(self, mapper):
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
        mapper._chest_service.take_item_by_target.assert_called_once()

    def test_execute_combat_use_skill_success(self, mapper):
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
        mapper._skill_tool_service.use_skill.assert_called_once()


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
