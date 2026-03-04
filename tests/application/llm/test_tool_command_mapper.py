"""ToolCommandMapper のテスト（正常・例外・失敗時 remediation）"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.tool_command_mapper import ToolCommandMapper
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_NO_OP,
    TOOL_NAME_SET_DESTINATION,
)
from ai_rpg_world.application.world.contracts.dtos import MoveResultDto
from datetime import datetime


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


class TestToolCommandMapperSetDestination:
    """set_destination ツールの実行（MovementService モック）"""

    @pytest.fixture
    def movement_service(self):
        return MagicMock()

    @pytest.fixture
    def mapper(self, movement_service):
        return ToolCommandMapper(movement_service=movement_service)

    def test_execute_set_destination_success_returns_dto(self, mapper, movement_service):
        """set_destination 成功時は MoveResultDto.message を message に"""
        movement_service.set_destination.return_value = MoveResultDto(
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
            message="目的地を設定しました。",
        )
        result = mapper.execute(
            1,
            TOOL_NAME_SET_DESTINATION,
            {"destination_type": "spot", "target_spot_id": 2},
        )
        assert result.success is True
        assert result.message == "目的地を設定しました。"

    def test_execute_set_destination_invalid_destination_type_returns_failure_dto(self, mapper):
        """destination_type が spot/location 以外なら失敗 DTO"""
        result = mapper.execute(
            1,
            TOOL_NAME_SET_DESTINATION,
            {"destination_type": "invalid", "target_spot_id": 2},
        )
        assert result.success is False
        assert result.error_code == "INVALID_DESTINATION"
        assert result.remediation is not None

    def test_execute_set_destination_location_without_area_id_returns_failure(self, mapper):
        """destination_type=location で target_location_area_id なしなら失敗"""
        result = mapper.execute(
            1,
            TOOL_NAME_SET_DESTINATION,
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

    def test_init_movement_service_no_set_destination_raises_type_error(self):
        """movement_service に set_destination が無いとき TypeError"""
        with pytest.raises(TypeError, match="set_destination"):
            ToolCommandMapper(movement_service=object())  # type: ignore[arg-type]
