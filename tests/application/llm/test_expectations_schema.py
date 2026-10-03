"""環境の tool に足す予期の引数 ``expectations`` の形を保証する (#1441)。"""

from __future__ import annotations

from ai_rpg_world.application.being.expectation.likelihood_labels import (
    LIKELIHOOD_LABELS,
)
from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.tool_category import ToolCategory
from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import (
    EXPECTATIONS_FIELD_NAME,
    strip_reason_first_action_subjective_schema,
    with_expectations_schema,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)


def _world_tool() -> ToolDefinitionDto:
    return ToolDefinitionDto(
        name="speak",
        description="話す",
        parameters={
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
        },
        category=ToolCategory.WORLD_ACTION,
    )


class TestWithExpectationsSchema:
    """with_expectations_schema が、what / when / likelihood を持つ予期の配列を必須の引数として足すことを保証する。"""

    def test_adds_required_array_of_expectations(self) -> None:
        """足した引数は配列で required に入り、元の引数と required はそのまま残る。"""
        decorated = with_expectations_schema(_world_tool())

        parameters = decorated.parameters
        assert parameters["properties"][EXPECTATIONS_FIELD_NAME]["type"] == "array"
        assert parameters["required"] == ["content", EXPECTATIONS_FIELD_NAME]
        assert "content" in parameters["properties"]

    def test_each_item_requires_what_and_likelihood_but_not_when(self) -> None:
        """1 件ごとに what と likelihood は必須で、when は分からなければ書かなくてよい。"""
        items = with_expectations_schema(_world_tool()).parameters["properties"][
            EXPECTATIONS_FIELD_NAME
        ]["items"]

        assert set(items["properties"]) == {"what", "when", "likelihood"}
        assert items["required"] == ["what", "likelihood"]

    def test_likelihood_offers_the_four_labels_of_the_domain(self) -> None:
        """likelihood の選択肢は、ドメインの確からしさ 4 段に対応する日本語の値だけになる。"""
        items = with_expectations_schema(_world_tool()).parameters["properties"][
            EXPECTATIONS_FIELD_NAME
        ]["items"]

        assert items["properties"]["likelihood"]["enum"] == [
            LIKELIHOOD_LABELS[likelihood] for likelihood in Likelihood
        ]

    def test_does_not_add_expected_result(self) -> None:
        """予期の引数を足しても expected_result は足さない。"""
        decorated = with_expectations_schema(_world_tool())

        assert "expected_result" not in decorated.parameters["properties"]

    def test_does_not_mutate_input_definition(self) -> None:
        """元の定義の parameters を書き換えない。"""
        original = _world_tool()

        with_expectations_schema(original)

        assert EXPECTATIONS_FIELD_NAME not in original.parameters["properties"]
        assert original.parameters["required"] == ["content"]


class TestReasonFirstKeepsExpectations:
    """2 段階ターンの行動段階でも、予期の引数が残ることを保証する。"""

    def test_strip_keeps_expectations_on_the_action_tool(self) -> None:
        """行動段階で inner_thought を外しても、予期は行動を選んだあとに書くので残る。"""
        decorated = with_expectations_schema(_world_tool())

        stripped = strip_reason_first_action_subjective_schema(decorated)

        assert EXPECTATIONS_FIELD_NAME in stripped.parameters["properties"]
        assert EXPECTATIONS_FIELD_NAME in stripped.parameters["required"]
