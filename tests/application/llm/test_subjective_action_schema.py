"""world-action tool の主観入力 schema (主観フィールド 5→4) の不変条件。"""

import pytest

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.tool_category import ToolCategory
from ai_rpg_world.application.llm.llm_argument_fingerprint import (
    NARRATIVE_ARG_FIELDS,
)
from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import (
    SUBJECTIVE_ACTION_FIELD_PROPERTIES,
    SUBJECTIVE_ACTION_FIELDS,
    SUBJECTIVE_ACTION_TEXT_FIELDS,
    with_expected_result_schema,
    with_subjective_action_schema,
)

# attention は行き先ゼロ (SubjectiveEpisode・trace・observer・recall いずれも読まない)
# のため PR0 で削除した。inner_thought=声 / intention=目的 / expected_result=予測 /
# emotion_hint=感情 の 4 facet を残す。
EXPECTED_SUBJECTIVE_FIELDS = (
    "inner_thought",
    "intention",
    "expected_result",
    "emotion_hint",
)


class TestSubjectiveActionFieldSet:
    """主観フィールド集合が 4 facet (attention 削除後) であること。"""

    def test_subjective_action_fields_are_the_four_facets(self) -> None:
        """SUBJECTIVE_ACTION_FIELDS は声/目的/予測/感情の 4 つ。"""
        assert SUBJECTIVE_ACTION_FIELDS == EXPECTED_SUBJECTIVE_FIELDS

    def test_attention_is_not_a_subjective_field(self) -> None:
        """attention は主観フィールドから除外されている。"""
        assert "attention" not in SUBJECTIVE_ACTION_FIELDS
        assert "attention" not in SUBJECTIVE_ACTION_TEXT_FIELDS
        assert "attention" not in SUBJECTIVE_ACTION_FIELD_PROPERTIES

    def test_text_fields_exclude_emotion_hint_enum(self) -> None:
        """text validation 対象は enum の emotion_hint を含まない 3 つ。"""
        assert SUBJECTIVE_ACTION_TEXT_FIELDS == (
            "inner_thought",
            "intention",
            "expected_result",
        )

    def test_attention_not_stripped_as_narrative_anymore(self) -> None:
        """fingerprint の narrative strip 対象からも attention は外れている。"""
        assert "attention" not in NARRATIVE_ARG_FIELDS


class TestWithSubjectiveActionSchema:
    """with_subjective_action_schema が required へ 4 facet を強制すること。"""

    def _world_tool(self) -> ToolDefinitionDto:
        return ToolDefinitionDto(
            name="spot_graph_interact",
            description="何かに作用する",
            parameters={"type": "object", "properties": {}, "required": []},
            category=ToolCategory.WORLD_ACTION,
        )

    def test_required_includes_four_facets(self) -> None:
        """world-action tool の required に 4 facet が入る。"""
        decorated = with_subjective_action_schema(self._world_tool())
        required = set(decorated.parameters["required"])
        for field_name in EXPECTED_SUBJECTIVE_FIELDS:
            assert field_name in required

    def test_required_does_not_include_attention(self) -> None:
        """required にも properties にも attention は現れない。"""
        decorated = with_subjective_action_schema(self._world_tool())
        assert "attention" not in decorated.parameters["required"]
        assert "attention" not in decorated.parameters["properties"]


class TestWithExpectedResultSchema:
    """with_expected_result_schema (#526 v0): expected_result だけを選択露出する。"""

    def _world_tool(self) -> ToolDefinitionDto:
        return ToolDefinitionDto(
            name="spot_graph_interact",
            description="何かに作用する",
            parameters={
                "type": "object",
                "properties": {"object_label": {"type": "string"}},
                "required": ["object_label"],
            },
            category=ToolCategory.WORLD_ACTION,
        )

    def test_optional_adds_property_but_not_required(self) -> None:
        """required=False なら expected_result が properties に出るが required には入らない。"""
        decorated = with_expected_result_schema(self._world_tool(), required=False)
        assert "expected_result" in decorated.parameters["properties"]
        assert "expected_result" not in decorated.parameters["required"]
        # 既存 property / required は保持
        assert "object_label" in decorated.parameters["properties"]
        assert "object_label" in decorated.parameters["required"]

    def test_required_adds_property_and_required(self) -> None:
        """required=True なら expected_result が properties と required の両方に入る。"""
        decorated = with_expected_result_schema(self._world_tool(), required=True)
        assert "expected_result" in decorated.parameters["properties"]
        assert "expected_result" in decorated.parameters["required"]

    def test_only_expected_result_added_not_intention_or_emotion(self) -> None:
        """v0 は expected_result 一本。intention / emotion_hint は露出しない。"""
        decorated = with_expected_result_schema(self._world_tool(), required=True)
        assert "intention" not in decorated.parameters["properties"]
        assert "emotion_hint" not in decorated.parameters["properties"]

    def test_expected_result_property_matches_canonical_definition(self) -> None:
        """露出する property は SUBJECTIVE_ACTION_FIELD_PROPERTIES の定義と一致する。"""
        decorated = with_expected_result_schema(self._world_tool(), required=False)
        assert (
            decorated.parameters["properties"]["expected_result"]
            == SUBJECTIVE_ACTION_FIELD_PROPERTIES["expected_result"]
        )

    def test_does_not_mutate_input_definition(self) -> None:
        """入力 definition を破壊しない (immutable パターン)。"""
        original = self._world_tool()
        with_expected_result_schema(original, required=True)
        assert "expected_result" not in original.parameters["properties"]
        assert "expected_result" not in original.parameters["required"]
