"""world-action tool の主観入力 schema (主観フィールド 5→4→3) の不変条件。予測 expected_result は #1631 で消した。"""
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

EXPECTED_SUBJECTIVE_FIELDS = ('inner_thought', 'intention', 'emotion_hint')

class TestSubjectiveActionFieldSet:
    """主観フィールド集合が 3 facet (attention と expected_result の削除後) であること。"""

    def test_subjective_action_fields_are_the_three_facets(self) -> None:
        """SUBJECTIVE_ACTION_FIELDS は声/目的/感情の 3 つで、予測 expected_result は含まない。"""
        assert SUBJECTIVE_ACTION_FIELDS == EXPECTED_SUBJECTIVE_FIELDS

    def test_attention_is_not_a_subjective_field(self) -> None:
        """attention は主観フィールドから除外されている。"""
        assert 'attention' not in SUBJECTIVE_ACTION_FIELDS
        assert 'attention' not in SUBJECTIVE_ACTION_TEXT_FIELDS
        assert 'attention' not in SUBJECTIVE_ACTION_FIELD_PROPERTIES

    def test_text_fields_exclude_emotion_hint_enum(self) -> None:
        """text validation 対象は enum の emotion_hint を含まない 2 つ。"""
        assert SUBJECTIVE_ACTION_TEXT_FIELDS == ('inner_thought', 'intention')

    def test_attention_not_stripped_as_narrative_anymore(self) -> None:
        """fingerprint の narrative strip 対象からも attention は外れている。"""
        assert 'attention' not in NARRATIVE_ARG_FIELDS

class TestWithSubjectiveActionSchema:
    """with_subjective_action_schema が required へ 3 facet を強制すること。"""

    def _world_tool(self) -> ToolDefinitionDto:
        return ToolDefinitionDto(name='interact', description='何かに作用する', parameters={'type': 'object', 'properties': {}, 'required': []}, category=ToolCategory.WORLD_ACTION)

    def test_required_includes_three_facets(self) -> None:
        """world-action tool の required に 3 facet が入り、expected_result は properties にも出ない。"""
        decorated = with_subjective_action_schema(self._world_tool())
        required = set(decorated.parameters['required'])
        for field_name in EXPECTED_SUBJECTIVE_FIELDS:
            assert field_name in required
        assert 'expected_result' not in decorated.parameters['properties']

    def test_required_does_not_include_attention(self) -> None:
        """required にも properties にも attention は現れない。"""
        decorated = with_subjective_action_schema(self._world_tool())
        assert 'attention' not in decorated.parameters['required']
        assert 'attention' not in decorated.parameters['properties']

class TestStripReasonFirstActionSubjectiveSchema:
    """reason-first の行動段階では LLM に主観フィールドを書かせない。"""

    def _action_tool(self) -> ToolDefinitionDto:
        return ToolDefinitionDto(name='interact', description='何かに作用する', parameters={'type': 'object', 'properties': {'object_label': {'type': 'string'}, 'inner_thought': {'type': 'string'}, 'goal_update': {'type': ['string', 'null']}, 'goal_outcome': {'type': ['string', 'null'], 'enum': ['achieved', 'abandoned', None]}}, 'required': ['object_label', 'inner_thought']}, category=ToolCategory.WORLD_ACTION)

    def test_removes_only_inner_thought(self) -> None:
        """reason-first action schema は step1 が所有する inner_thought だけを落とす。"""
        stripped = strip_reason_first_action_subjective_schema(self._action_tool())
        props = stripped.parameters['properties']
        required = stripped.parameters['required']
        assert 'inner_thought' not in props
        assert 'inner_thought' not in required
        assert 'object_label' in props
        assert 'object_label' in required
        assert 'goal_update' in props
        assert 'goal_outcome' in props

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

class TestWithGoalUpdateSchema:
    """P6: with_goal_update_schema が goal_update を optional で足すこと。"""

    def _world_tool(self) -> ToolDefinitionDto:
        return ToolDefinitionDto(name='interact', description='何かに作用する', parameters={'type': 'object', 'properties': {}, 'required': []}, category=ToolCategory.WORLD_ACTION)

    def _todo_tool(self) -> ToolDefinitionDto:
        return ToolDefinitionDto(name='todo_add', description='メモ追加', parameters={'type': 'object', 'properties': {}, 'required': []}, category=ToolCategory.WORLD_ACTION)

    def test_goal_update_added_to_properties_not_required(self) -> None:
        from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import with_goal_update_schema
        decorated = with_goal_update_schema(self._world_tool())
        assert 'goal_update' in decorated.parameters['properties']
        assert 'goal_update' not in decorated.parameters['required']

    def test_description_contrasts_with_the_next_move_without_naming_an_argument(self) -> None:
        """高度の防衛は説明文。次の 1 手の意図との対比を載せるが、goal_update を足す tool が受け取らない intention 引数は指さない。"""
        from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import with_goal_update_schema
        decorated = with_goal_update_schema(self._world_tool())
        desc = decorated.parameters['properties']['goal_update']['description']
        assert '次の 1 手の意図' in desc
        assert 'intention' not in desc
        assert '数日スケール' in desc
        assert '続けるなら書かない' in desc

    def test_not_added_to_non_subjective_tool(self) -> None:
        """todo 系 (非 subjective action) には足さない。"""
        from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import with_goal_update_schema
        decorated = with_goal_update_schema(self._todo_tool())
        assert 'goal_update' not in decorated.parameters.get('properties', {})

class TestWithGoalOutcomeSchema:
    """P8: with_goal_outcome_schema が goal_outcome を nullable enum で足すこと。"""

    def _world_tool(self) -> ToolDefinitionDto:
        return ToolDefinitionDto(name='interact', description='何かに作用する', parameters={'type': 'object', 'properties': {}, 'required': []}, category=ToolCategory.WORLD_ACTION)

    def _todo_tool(self) -> ToolDefinitionDto:
        return ToolDefinitionDto(name='todo_add', description='メモ追加', parameters={'type': 'object', 'properties': {}, 'required': []}, category=ToolCategory.WORLD_ACTION)

    def test_goal_outcome_added_as_nullable_enum_not_required(self) -> None:
        from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import with_goal_outcome_schema
        decorated = with_goal_outcome_schema(self._world_tool())
        prop = decorated.parameters['properties']['goal_outcome']
        assert prop['enum'] == ['achieved', 'abandoned', None]
        assert 'null' in prop['type']
        assert 'goal_outcome' not in decorated.parameters['required']

    def test_description_distinguishes_close_from_rephrase(self) -> None:
        """説明文が「閉じる (清算)」と「言い直し (書かない)」を区別する。"""
        from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import with_goal_outcome_schema
        desc = with_goal_outcome_schema(self._world_tool()).parameters['properties']['goal_outcome']['description']
        assert 'achieved' in desc and 'abandoned' in desc
        assert '言い直し' in desc

    def test_not_added_to_non_subjective_tool(self) -> None:
        from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import with_goal_outcome_schema
        decorated = with_goal_outcome_schema(self._todo_tool())
        assert 'goal_outcome' not in decorated.parameters.get('properties', {})
