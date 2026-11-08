from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.design_flaw import DesignLocation
from ai_rpg_world.game_world.infrastructure.scenario.scenario_layout import YamlPath


class TestLocation:
    """YamlPath.location が、シナリオの YAML の道筋を宣言の種類・名前・欄に写すことを保証する。"""

    def test_object_inside_spot_is_located_by_the_object_name(self) -> None:
        """場所の中に書いた物の操作の前提は、物の名前と、物の中の道筋で表す。"""
        path = YamlPath.root() / "spots" / "lift_landing" / "objects" / "lift_panel" / "interactions"
        path = path / "start_lift" / "precondition"

        assert path.location() == DesignLocation("object", "lift_panel", "interactions.start_lift.precondition")

    @pytest.mark.parametrize(
        ("steps", "expected"),
        [
            (("spots", "mine"), DesignLocation("spot", "mine", "")),
            (("spots", "mine", "sections", "cage", "access"), DesignLocation("section", "cage", "access")),
            (("spots", "mine", "discoverables", "nail"), DesignLocation("discoverable", "nail", "")),
            (("passages", "shaft", "ends", 1), DesignLocation("passage", "shaft", "ends[1]")),
            (("groupings", "team", "groups", "north"), DesignLocation("group", "north", "")),
            (("happenings", "quake", "effect"), DesignLocation("happening", "quake", "effect")),
            (("characters", "haru", "being"), DesignLocation("character", "haru", "being")),
        ],
    )
    def test_named_declarations_are_located_by_their_key(
        self, steps: tuple[str | int, ...], expected: DesignLocation
    ) -> None:
        """名前で指す宣言は、地図の鍵を名前にし、その下の道筋を欄にする。"""
        path = YamlPath.root()
        for step in steps:
            path = path / step

        assert path.location() == expected

    def test_world_wide_section_is_located_on_the_world(self) -> None:
        """世界に 1 つの欄 (rules など) は、world の欄として道筋をそのまま書く。"""
        path = YamlPath.root() / "rules" / "fatigue" / "limit"

        assert path.location() == DesignLocation("world", "world", "rules.fatigue.limit")

    def test_section_list_itself_is_located_on_the_world(self) -> None:
        """名前より手前 (spots そのもの) は、world の欄として表す。"""
        assert (YamlPath.root() / "spots").location() == DesignLocation("world", "world", "spots")
