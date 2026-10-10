"""ツールの説明が、プロンプトに実在する節と、このツールが受け取る引数だけを指すことを保証する。"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    TRAVEL_TO_DEFINITION,
)
from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import (
    GOAL_UPDATE_FIELD_NAME,
    with_goal_update_schema,
)


class TestGoalUpdateDescription:
    """goal_update の説明が、同じツールに無い引数を指さないことを確かめる。"""

    def test_does_not_mention_an_argument_the_tool_does_not_take(self) -> None:
        """intention を持たない travel_to に goal_update を足しても、説明は intention を指さない。"""
        definition = with_goal_update_schema(TRAVEL_TO_DEFINITION)
        properties = definition.parameters["properties"]

        description = properties[GOAL_UPDATE_FIELD_NAME]["description"]

        assert "intention" not in properties
        assert "intention" not in description


class TestDestinationLabelDescription:
    """destination_label の説明が、実在する節名を指すことを確かめる。"""

    def test_points_at_the_current_location_section(self) -> None:
        """接続先が載る節を、実際の見出し【現在地と周囲】で指し、実在しない『現在の状況』を指さない。"""
        description = TRAVEL_TO_DEFINITION.parameters["properties"]["destination_label"][
            "description"
        ]

        assert "【現在地と周囲】" in description
        assert "現在の状況" not in description
