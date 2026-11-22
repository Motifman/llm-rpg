from __future__ import annotations

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.tool_category import ToolCategory
from ai_rpg_world.application.llm.services.tool_catalog.memo_argument import with_memo_schema


class TestMemoSchema:
    """with_memo_schema が、環境の tool に省略できる引数 memo を足すことを保証する。"""

    def _definition(self) -> ToolDefinitionDto:
        return ToolDefinitionDto(
            name="wait",
            description="待つ",
            parameters={
                "type": "object",
                "properties": {"inner_thought": {"type": "string"}},
                "required": ["inner_thought"],
            },
            category=ToolCategory.WORLD_ACTION,
        )

    def test_memo_is_added_but_not_required(self) -> None:
        """memo を properties に足し、required には足さない。元の引数はそのまま残る。"""
        definition = with_memo_schema(self._definition(), episode_source_offered=False)

        assert set(definition.parameters["properties"]) == {"inner_thought", "memo"}
        assert definition.parameters["required"] == ["inner_thought"]

    def test_episode_source_is_not_offered_unless_asked(self) -> None:
        """エピソードを出どころに出さない設定では、選択肢にも説明にも episode と ep_ が出ない。"""
        memo = with_memo_schema(self._definition(), episode_source_offered=False).parameters["properties"]["memo"]

        assert memo["items"]["properties"]["source"]["enum"] == ["self", "heard"]
        assert "episode" not in memo["description"]
        assert "ep_" not in memo["description"]

    def test_episode_source_is_offered_when_asked(self) -> None:
        """エピソードを出どころに出す設定では、選択肢と説明に episode が出る。"""
        memo = with_memo_schema(self._definition(), episode_source_offered=True).parameters["properties"]["memo"]

        assert memo["items"]["properties"]["source"]["enum"] == ["self", "heard", "episode"]
        assert "ep_" in memo["description"]

    def test_episode_source_is_limited_to_handles_in_the_index(self) -> None:
        """エピソードを出どころに出す設定では、【思い出せる出来事】にある呼び名だけを書き、無ければ episode を選ばないと説明する。

        確認の run (`var/runs/mine_v1_008_check`) で、エピソードがまだ無い回に episode を選び、
        呼び名の代わりに ep_? と書いて外された。
        """
        memo = with_memo_schema(self._definition(), episode_source_offered=True).parameters["properties"]["memo"]

        assert "【思い出せる出来事】にある呼び名だけ書ける" in memo["description"]
        assert "無ければ episode は選ばない" in memo["description"]
