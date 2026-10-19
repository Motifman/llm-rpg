"""world-action tool の主観入力 schema (主観フィールド 5→4→3→1) の不変条件。予測 expected_result と目的・感情 (intention / emotion_hint) は #1631 で消した。"""
import pytest

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.tool_category import ToolCategory
from ai_rpg_world.application.llm.llm_argument_fingerprint import NARRATIVE_ARG_FIELDS
from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import (
    SUBJECTIVE_ACTION_FIELD_PROPERTIES,
    SUBJECTIVE_ACTION_FIELDS,
    SUBJECTIVE_ACTION_TEXT_FIELDS,
    assess_situation_definition,
    strip_reason_first_action_subjective_schema,
    with_subjective_action_schema,
)

EXPECTED_SUBJECTIVE_FIELDS = ('inner_thought',)

class TestSubjectiveActionFieldSet:
    """主観フィールド集合が独白 inner_thought だけであること。"""

    def test_subjective_action_fields_are_only_inner_thought(self) -> None:
        """SUBJECTIVE_ACTION_FIELDS は独白 inner_thought だけで、予測・目的・感情は含まない。"""
        assert SUBJECTIVE_ACTION_FIELDS == EXPECTED_SUBJECTIVE_FIELDS

    def test_attention_is_not_a_subjective_field(self) -> None:
        """attention は主観フィールドから除外されている。"""
        assert 'attention' not in SUBJECTIVE_ACTION_FIELDS
        assert 'attention' not in SUBJECTIVE_ACTION_TEXT_FIELDS
        assert 'attention' not in SUBJECTIVE_ACTION_FIELD_PROPERTIES

    def test_text_fields_are_only_inner_thought(self) -> None:
        """text validation 対象も inner_thought だけになる。"""
        assert SUBJECTIVE_ACTION_TEXT_FIELDS == ('inner_thought',)

    def test_attention_not_stripped_as_narrative_anymore(self) -> None:
        """fingerprint の narrative strip 対象からも attention は外れている。"""
        assert 'attention' not in NARRATIVE_ARG_FIELDS

class TestWithSubjectiveActionSchema:
    """with_subjective_action_schema が required へ inner_thought を強制すること。"""

    def _world_tool(self) -> ToolDefinitionDto:
        return ToolDefinitionDto(name='interact', description='何かに作用する', parameters={'type': 'object', 'properties': {}, 'required': []}, category=ToolCategory.WORLD_ACTION)

    def test_required_includes_inner_thought_only(self) -> None:
        """world-action tool の required に inner_thought が入り、expected_result / intention / emotion_hint は properties にも出ない。"""
        decorated = with_subjective_action_schema(self._world_tool())
        required = set(decorated.parameters['required'])
        for field_name in EXPECTED_SUBJECTIVE_FIELDS:
            assert field_name in required
        for removed in ('expected_result', 'intention', 'emotion_hint'):
            assert removed not in decorated.parameters['properties']

    def test_required_does_not_include_attention(self) -> None:
        """required にも properties にも attention は現れない。"""
        decorated = with_subjective_action_schema(self._world_tool())
        assert 'attention' not in decorated.parameters['required']
        assert 'attention' not in decorated.parameters['properties']

class TestStripReasonFirstActionSubjectiveSchema:
    """reason-first の行動段階では LLM に主観フィールドを書かせない。"""

    def _action_tool(self) -> ToolDefinitionDto:
        return ToolDefinitionDto(name='interact', description='何かに作用する', parameters={'type': 'object', 'properties': {'object_label': {'type': 'string'}, 'inner_thought': {'type': 'string'}, 'expected_result': {'type': 'string'}}, 'required': ['object_label', 'inner_thought']}, category=ToolCategory.WORLD_ACTION)

    def test_removes_only_inner_thought(self) -> None:
        """reason-first action schema は step1 が所有する inner_thought だけを落とす。"""
        stripped = strip_reason_first_action_subjective_schema(self._action_tool())
        props = stripped.parameters['properties']
        required = stripped.parameters['required']
        assert 'inner_thought' not in props
        assert 'inner_thought' not in required
        assert 'object_label' in props
        assert 'object_label' in required
        assert 'expected_result' in props

    def test_does_not_mutate_input_definition(self) -> None:
        """入力定義は破壊せず、legacy toolset の schema を汚さない。"""
        original = self._action_tool()
        strip_reason_first_action_subjective_schema(original)
        assert 'inner_thought' in original.parameters['properties']
        assert 'inner_thought' in original.parameters['required']

class TestAssessSituationDefinition:
    """assess_situation が reason-first の主観入力として inner_thought だけを受け取る。"""

    def test_exposes_only_inner_thought(self) -> None:
        """assess_situation は inner_thought だけを必須で受け取り、予測 expected_result は出さない。"""
        definition = assess_situation_definition()
        assert definition.name == 'assess_situation'
        assert definition.category is ToolCategory.META_COGNITIVE
        assert definition.parameters['required'] == ['inner_thought']
        assert set(definition.parameters['properties']) == {'inner_thought'}
        assert '実行しない' in definition.description
