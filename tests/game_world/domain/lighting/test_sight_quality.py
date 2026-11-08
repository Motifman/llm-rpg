from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.lighting import SeesClearly, SeesNothing, SeesShapes, SightQuality


class _TextsNamingTheCase:
    def when_clear(self) -> str:
        return "clear"

    def when_shapes(self) -> str:
        return "shapes"

    def when_nothing(self) -> str:
        return "nothing"


class TestSightQualityRead:
    """SightQuality.read が、見え方ごとに、渡された文の側の対応するメソッドだけを呼ぶことを保証する。"""

    @pytest.mark.parametrize(
        ("sight", "expected"),
        [(SeesClearly(), "clear"), (SeesShapes(), "shapes"), (SeesNothing(), "nothing")],
    )
    def test_each_sight_asks_the_texts_for_its_own_case(self, sight: SightQuality, expected: str) -> None:
        """SeesClearly は when_clear、SeesShapes は when_shapes、SeesNothing は when_nothing の戻り値を返す。"""
        assert sight.read(_TextsNamingTheCase()) == expected
