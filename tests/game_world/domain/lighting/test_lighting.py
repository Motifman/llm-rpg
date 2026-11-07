from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.lighting import (
    Lighting,
    SeesClearly,
    SeesNothing,
    SeesShapes,
    SightQuality,
)


class TestLightingSight:
    """Lighting.sight が、明るさの 4 段を perception.md の表どおりの見え方 3 つへ写すことを保証する。"""

    @pytest.mark.parametrize(
        ("lighting", "expected"),
        [
            (Lighting.BRIGHT, SeesClearly()),
            (Lighting.DUSKY, SeesClearly()),
            (Lighting.DARK, SeesShapes()),
            (Lighting.PITCH_DARK, SeesNothing()),
        ],
    )
    def test_each_lighting_maps_to_the_sight_in_the_table(self, lighting: Lighting, expected: SightQuality) -> None:
        """明るい・薄暗いは SeesClearly、暗いは SeesShapes、真っ暗は SeesNothing を返す。"""
        assert lighting.sight() == expected


class TestSightQuality:
    """見え方の値が、WorldRules の notice_by_bystander のような表のキーとして使えることを保証する。"""

    def test_same_sight_qualities_are_equal_and_share_a_hash(self) -> None:
        """別々に作った SeesShapes どうしは等しく、同じハッシュを持つので、表のキーとして引ける。"""
        table = {SeesClearly(): "clear", SeesShapes(): "shapes", SeesNothing(): "nothing"}

        assert table[SeesShapes()] == "shapes"

    def test_different_sight_qualities_are_not_equal(self) -> None:
        """SeesClearly、SeesShapes、SeesNothing は互いに等しくない。"""
        assert len({SeesClearly(), SeesShapes(), SeesNothing()}) == 3
