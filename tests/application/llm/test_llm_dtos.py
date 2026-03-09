"""LLM 向け DTO（SystemPromptPlayerInfoDto, ActionResultEntry, LlmCommandResultDto, ToolDefinitionDto, EpisodeMemoryEntry, LongTermFactEntry, MemoryLawEntry）のテスト（正常・例外）"""

import pytest
from datetime import datetime

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    EpisodeMemoryEntry,
    is_reschedulable_error_code,
    LlmUiContextDto,
    LlmCommandResultDto,
    LongTermFactEntry,
    MemoryLawEntry,
    should_reschedule_for_next_tick,
    SystemPromptPlayerInfoDto,
    ToolDefinitionDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)


class TestSystemPromptPlayerInfoDto:
    """SystemPromptPlayerInfoDto の正常・例外ケース"""

    def test_create_with_valid_fields(self):
        """全フィールドが str なら正常に生成される"""
        dto = SystemPromptPlayerInfoDto(
            player_name="TestPlayer",
            role="citizen",
            race="human",
            element="neutral",
            game_description="A game.",
        )
        assert dto.player_name == "TestPlayer"
        assert dto.role == "citizen"
        assert dto.race == "human"
        assert dto.element == "neutral"
        assert dto.game_description == "A game."

    def test_game_description_can_be_empty(self):
        """game_description は空文字可"""
        dto = SystemPromptPlayerInfoDto(
            player_name="P",
            role="r",
            race="r",
            element="e",
            game_description="",
        )
        assert dto.game_description == ""

    def test_player_name_not_str_raises_type_error(self):
        """player_name が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="player_name must be str"):
            SystemPromptPlayerInfoDto(
                player_name=123,  # type: ignore[arg-type]
                role="r",
                race="r",
                element="e",
                game_description="",
            )

    def test_role_not_str_raises_type_error(self):
        """role が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="role must be str"):
            SystemPromptPlayerInfoDto(
                player_name="P",
                role=None,  # type: ignore[arg-type]
                race="r",
                element="e",
                game_description="",
            )

    def test_race_not_str_raises_type_error(self):
        """race が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="race must be str"):
            SystemPromptPlayerInfoDto(
                player_name="P",
                role="r",
                race=1,  # type: ignore[arg-type]
                element="e",
                game_description="",
            )

    def test_element_not_str_raises_type_error(self):
        """element が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="element must be str"):
            SystemPromptPlayerInfoDto(
                player_name="P",
                role="r",
                race="r",
                element=[],  # type: ignore[arg-type]
                game_description="",
            )

    def test_game_description_not_str_raises_type_error(self):
        """game_description が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="game_description must be str"):
            SystemPromptPlayerInfoDto(
                player_name="P",
                role="r",
                race="r",
                element="e",
                game_description=0.0,  # type: ignore[arg-type]
            )


class TestActionResultEntry:
    """ActionResultEntry の正常・例外ケース"""

    def test_create_with_valid_fields(self):
        """occurred_at / action_summary / result_summary が正しい型なら正常"""
        now = datetime.now()
        entry = ActionResultEntry(
            occurred_at=now,
            action_summary="move_to を実行",
            result_summary="スポットAに到着しました。",
        )
        assert entry.occurred_at == now
        assert entry.action_summary == "move_to を実行"
        assert entry.result_summary == "スポットAに到着しました。"

    def test_occurred_at_not_datetime_raises_type_error(self):
        """occurred_at が datetime でない場合 TypeError"""
        with pytest.raises(TypeError, match="occurred_at must be datetime"):
            ActionResultEntry(
                occurred_at="2025-01-01",  # type: ignore[arg-type]
                action_summary="a",
                result_summary="b",
            )

    def test_action_summary_not_str_raises_type_error(self):
        """action_summary が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="action_summary must be str"):
            ActionResultEntry(
                occurred_at=datetime.now(),
                action_summary=123,  # type: ignore[arg-type]
                result_summary="b",
            )

    def test_result_summary_not_str_raises_type_error(self):
        """result_summary が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="result_summary must be str"):
            ActionResultEntry(
                occurred_at=datetime.now(),
                action_summary="a",
                result_summary=None,  # type: ignore[arg-type]
            )


class TestLlmCommandResultDto:
    """LlmCommandResultDto の正常・例外ケース"""

    def test_create_success_minimal(self):
        """成功時は message のみで error_code / remediation は None"""
        dto = LlmCommandResultDto(success=True, message="完了しました。")
        assert dto.success is True
        assert dto.message == "完了しました。"
        assert dto.error_code is None
        assert dto.remediation is None
        assert dto.should_reschedule is False
        assert dto.was_no_op is False

    def test_create_with_was_no_op(self):
        """was_no_op=True で world_no_op 実行を表す"""
        dto = LlmCommandResultDto(
            success=True, message="何もしませんでした。", was_no_op=True
        )
        assert dto.was_no_op is True

    def test_was_no_op_default_is_false(self):
        """was_no_op 省略時は False"""
        dto = LlmCommandResultDto(success=True, message="完了")
        assert dto.was_no_op is False

    def test_create_failure_with_should_reschedule(self):
        """失敗時は should_reschedule で次 tick 再試行を指定できる"""
        dto = LlmCommandResultDto(
            success=False,
            message="LLM がツールを返しませんでした。",
            error_code="NO_TOOL_CALL",
            remediation="必ずいずれか 1 つのツールを呼び出してください。",
            should_reschedule=True,
        )
        assert dto.should_reschedule is True

    def test_create_failure_with_remediation(self):
        """失敗時は message / error_code / remediation を指定できる"""
        dto = LlmCommandResultDto(
            success=False,
            message="移動に失敗しました。",
            error_code="MOVEMENT_INVALID",
            remediation="接続先を確認してください。",
        )
        assert dto.success is False
        assert dto.message == "移動に失敗しました。"
        assert dto.error_code == "MOVEMENT_INVALID"
        assert dto.remediation == "接続先を確認してください。"

    def test_success_not_bool_raises_type_error(self):
        """success が bool でない場合 TypeError"""
        with pytest.raises(TypeError, match="success must be bool"):
            LlmCommandResultDto(success=1, message="ok")  # type: ignore[arg-type]

    def test_message_not_str_raises_type_error(self):
        """message が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="message must be str"):
            LlmCommandResultDto(success=True, message=None)  # type: ignore[arg-type]

    def test_error_code_not_str_raises_type_error(self):
        """error_code が str でない場合（None 以外）TypeError"""
        with pytest.raises(TypeError, match="error_code must be str or None"):
            LlmCommandResultDto(
                success=False,
                message="err",
                error_code=123,  # type: ignore[arg-type]
            )

    def test_remediation_not_str_raises_type_error(self):
        """remediation が str でない場合（None 以外）TypeError"""
        with pytest.raises(TypeError, match="remediation must be str or None"):
            LlmCommandResultDto(
                success=False,
                message="err",
                remediation=[],  # type: ignore[arg-type]
            )

    def test_was_no_op_not_bool_raises_type_error(self):
        """was_no_op が bool でない場合 TypeError"""
        with pytest.raises(TypeError, match="was_no_op must be bool"):
            LlmCommandResultDto(
                success=True,
                message="ok",
                was_no_op="yes",  # type: ignore[arg-type]
            )

    def test_should_reschedule_for_next_tick_no_tool_call_returns_true(self):
        """NO_TOOL_CALL のとき should_reschedule_for_next_tick は True"""
        dto = LlmCommandResultDto(
            success=False,
            message="LLM がツールを返しませんでした。",
            error_code="NO_TOOL_CALL",
            remediation="...",
        )
        assert should_reschedule_for_next_tick(dto) is True

    def test_should_reschedule_for_next_tick_success_returns_false(self):
        """成功時は should_reschedule_for_next_tick は False"""
        dto = LlmCommandResultDto(success=True, message="完了")
        assert should_reschedule_for_next_tick(dto) is False

    def test_should_reschedule_for_next_tick_unknown_tool_returns_false(self):
        """UNKNOWN_TOOL のときは False（再スケジュールしない）"""
        dto = LlmCommandResultDto(
            success=False,
            message="未知のツール",
            error_code="UNKNOWN_TOOL",
        )
        assert should_reschedule_for_next_tick(dto) is False

    def test_is_reschedulable_error_code(self):
        """is_reschedulable_error_code の判定"""
        assert is_reschedulable_error_code("NO_TOOL_CALL") is True
        assert is_reschedulable_error_code("LLM_RATE_LIMIT") is True
        assert is_reschedulable_error_code("UNKNOWN_TOOL") is False
        assert is_reschedulable_error_code(None) is False


class TestToolDefinitionDto:
    """ToolDefinitionDto の正常・例外ケース"""

    def test_create_with_valid_fields(self):
        """name / description / parameters が正しい型なら正常"""
        dto = ToolDefinitionDto(
            name="world_no_op",
            description="何もしない。",
            parameters={"type": "object", "properties": {}, "required": []},
        )
        assert dto.name == "world_no_op"
        assert dto.description == "何もしない。"
        assert dto.parameters == {"type": "object", "properties": {}, "required": []}

    def test_name_not_str_raises_type_error(self):
        """name が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="name must be str"):
            ToolDefinitionDto(
                name=123,  # type: ignore[arg-type]
                description="d",
                parameters={},
            )


class TestToolRuntimeDtos:
    def test_tool_runtime_target_dto_valid(self):
        dto = ToolRuntimeTargetDto(
            label="P1",
            kind="player",
            display_name="Alice",
            player_id=1,
        )
        assert dto.label == "P1"
        assert dto.player_id == 1

    def test_tool_runtime_context_empty(self):
        ctx = ToolRuntimeContextDto.empty()
        assert ctx.targets == {}

    def test_llm_ui_context_dto_valid(self):
        ctx = ToolRuntimeContextDto.empty()
        dto = LlmUiContextDto(
            current_state_text="現在地: 広場",
            tool_runtime_context=ctx,
        )
        assert dto.current_state_text == "現在地: 広場"
        assert dto.tool_runtime_context is ctx

    def test_description_not_str_raises_type_error(self):
        """description が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="description must be str"):
            ToolDefinitionDto(
                name="n",
                description=None,  # type: ignore[arg-type]
                parameters={},
            )

    def test_parameters_not_dict_raises_type_error(self):
        """parameters が dict でない場合 TypeError"""
        with pytest.raises(TypeError, match="parameters must be dict"):
            ToolDefinitionDto(
                name="n",
                description="d",
                parameters="{}",  # type: ignore[arg-type]
            )


class TestEpisodeMemoryEntry:
    """EpisodeMemoryEntry の正常・例外ケース（記憶モジュール Phase 4）"""

    def test_create_with_valid_fields(self):
        """全フィールドが正しい型・値なら正常に生成される"""
        now = datetime.now()
        entry = EpisodeMemoryEntry(
            id="ep1",
            context_summary="洞窟にいた",
            action_taken="move_to_destination を実行",
            outcome_summary="到着した",
            entity_ids=("loc_1",),
            location_id="loc_1",
            timestamp=now,
            importance="medium",
            surprise=False,
            recall_count=0,
        )
        assert entry.id == "ep1"
        assert entry.context_summary == "洞窟にいた"
        assert entry.importance == "medium"
        assert entry.recall_count == 0

    def test_create_accepts_low_medium_high_importance(self):
        """importance に low / medium / high を指定できる"""
        now = datetime.now()
        for imp in ("low", "medium", "high"):
            entry = EpisodeMemoryEntry(
                id="e",
                context_summary="c",
                action_taken="a",
                outcome_summary="o",
                entity_ids=(),
                location_id=None,
                timestamp=now,
                importance=imp,
                surprise=False,
                recall_count=0,
            )
            assert entry.importance == imp

    def test_importance_invalid_raises_type_error(self):
        """importance が low/medium/high 以外の場合 TypeError"""
        with pytest.raises(TypeError, match="importance must be 'low', 'medium', or 'high'"):
            EpisodeMemoryEntry(
                id="e",
                context_summary="c",
                action_taken="a",
                outcome_summary="o",
                entity_ids=(),
                location_id=None,
                timestamp=datetime.now(),
                importance="invalid",  # type: ignore[arg-type]
                surprise=False,
                recall_count=0,
            )

    def test_recall_count_negative_raises_type_error(self):
        """recall_count が負の場合 TypeError"""
        with pytest.raises(TypeError, match="recall_count must be non-negative int"):
            EpisodeMemoryEntry(
                id="e",
                context_summary="c",
                action_taken="a",
                outcome_summary="o",
                entity_ids=(),
                location_id=None,
                timestamp=datetime.now(),
                importance="medium",
                surprise=False,
                recall_count=-1,
            )

    def test_id_not_str_raises_type_error(self):
        """id が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="id must be str"):
            EpisodeMemoryEntry(
                id=123,  # type: ignore[arg-type]
                context_summary="c",
                action_taken="a",
                outcome_summary="o",
                entity_ids=(),
                location_id=None,
                timestamp=datetime.now(),
                importance="medium",
                surprise=False,
                recall_count=0,
            )

    def test_entity_ids_not_tuple_raises_type_error(self):
        """entity_ids が tuple でない場合 TypeError"""
        with pytest.raises(TypeError, match="entity_ids must be tuple"):
            EpisodeMemoryEntry(
                id="e",
                context_summary="c",
                action_taken="a",
                outcome_summary="o",
                entity_ids=["loc_1"],  # type: ignore[arg-type]
                location_id=None,
                timestamp=datetime.now(),
                importance="medium",
                surprise=False,
                recall_count=0,
            )

    def test_entity_ids_contains_non_str_raises_type_error(self):
        """entity_ids の要素が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="entity_ids must contain only str"):
            EpisodeMemoryEntry(
                id="e",
                context_summary="c",
                action_taken="a",
                outcome_summary="o",
                entity_ids=(1,),  # type: ignore[arg-type]
                location_id=None,
                timestamp=datetime.now(),
                importance="medium",
                surprise=False,
                recall_count=0,
            )


class TestLongTermFactEntry:
    """LongTermFactEntry の正常・例外ケース"""

    def test_create_with_valid_fields(self):
        """全フィールドが正しい型なら正常に生成される"""
        now = datetime.now()
        entry = LongTermFactEntry(
            id="fact-1",
            content="洞窟の奥には強敵がいる",
            player_id=1,
            updated_at=now,
        )
        assert entry.id == "fact-1"
        assert entry.content == "洞窟の奥には強敵がいる"
        assert entry.player_id == 1
        assert entry.updated_at == now

    def test_id_not_str_raises_type_error(self):
        """id が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="id must be str"):
            LongTermFactEntry(
                id=1,  # type: ignore[arg-type]
                content="c",
                player_id=1,
                updated_at=datetime.now(),
            )

    def test_content_not_str_raises_type_error(self):
        """content が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="content must be str"):
            LongTermFactEntry(
                id="f",
                content=None,  # type: ignore[arg-type]
                player_id=1,
                updated_at=datetime.now(),
            )

    def test_player_id_not_int_raises_type_error(self):
        """player_id が int でない場合 TypeError"""
        with pytest.raises(TypeError, match="player_id must be int"):
            LongTermFactEntry(
                id="f",
                content="c",
                player_id="1",  # type: ignore[arg-type]
                updated_at=datetime.now(),
            )

    def test_updated_at_not_datetime_raises_type_error(self):
        """updated_at が datetime でない場合 TypeError"""
        with pytest.raises(TypeError, match="updated_at must be datetime"):
            LongTermFactEntry(
                id="f",
                content="c",
                player_id=1,
                updated_at="2025-01-01",  # type: ignore[arg-type]
            )


class TestMemoryLawEntry:
    """MemoryLawEntry の正常・例外ケース"""

    def test_create_with_valid_fields(self):
        """全フィールドが正しい型なら正常に生成される"""
        entry = MemoryLawEntry(
            id="law-1",
            subject="チェスト",
            relation="開けると",
            target="回復アイテム",
            strength=1.0,
            player_id=1,
        )
        assert entry.id == "law-1"
        assert entry.subject == "チェスト"
        assert entry.relation == "開けると"
        assert entry.target == "回復アイテム"
        assert entry.strength == 1.0
        assert entry.player_id == 1

    def test_strength_int_accepted(self):
        """strength に int を指定できる（float と同様）"""
        entry = MemoryLawEntry(
            id="l",
            subject="s",
            relation="r",
            target="t",
            strength=2,
            player_id=1,
        )
        assert entry.strength == 2

    def test_id_not_str_raises_type_error(self):
        """id が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="id must be str"):
            MemoryLawEntry(
                id=1,  # type: ignore[arg-type]
                subject="s",
                relation="r",
                target="t",
                strength=1.0,
                player_id=1,
            )

    def test_subject_not_str_raises_type_error(self):
        """subject が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="subject must be str"):
            MemoryLawEntry(
                id="l",
                subject=None,  # type: ignore[arg-type]
                relation="r",
                target="t",
                strength=1.0,
                player_id=1,
            )

    def test_strength_not_number_raises_type_error(self):
        """strength が int/float でない場合 TypeError"""
        with pytest.raises(TypeError, match="strength must be int or float"):
            MemoryLawEntry(
                id="l",
                subject="s",
                relation="r",
                target="t",
                strength="1.0",  # type: ignore[arg-type]
                player_id=1,
            )

    def test_player_id_not_int_raises_type_error(self):
        """player_id が int でない場合 TypeError"""
        with pytest.raises(TypeError, match="player_id must be int"):
            MemoryLawEntry(
                id="l",
                subject="s",
                relation="r",
                target="t",
                strength=1.0,
                player_id=None,  # type: ignore[arg-type]
            )
