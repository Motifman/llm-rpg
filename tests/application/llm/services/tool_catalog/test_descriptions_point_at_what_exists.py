"""ツールの説明が、プロンプトに実在する節と、このツールが受け取る引数だけを指すことを保証する。"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    TRAVEL_TO_DEFINITION,
)


class TestDestinationLabelDescription:
    """destination_label の説明が、実在する節名を指すことを確かめる。"""

    def test_points_at_the_current_location_section(self) -> None:
        """接続先が載る節を、実際の見出し【現在地と周囲】で指し、実在しない『現在の状況』を指さない。"""
        description = TRAVEL_TO_DEFINITION.parameters["properties"]["destination_label"][
            "description"
        ]

        assert "【現在地と周囲】" in description
        assert "現在の状況" not in description
