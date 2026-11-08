from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.sound import HearingQuality, HearsClearly, HearsFaintly, HearsMuffled, HearsNothing


class _TextsNamingTheCase:
    def when_clear(self) -> str:
        return "clear"

    def when_muffled(self) -> str:
        return "muffled"

    def when_faint(self) -> str:
        return "faint"

    def when_nothing(self) -> str:
        return "nothing"


class TestHearingQualityRead:
    """HearingQuality.read が、聞こえ方ごとに、渡された文の側の対応するメソッドだけを呼ぶことを保証する。"""

    @pytest.mark.parametrize(
        ("quality", "expected"),
        [(HearsClearly(), "clear"), (HearsMuffled(), "muffled"), (HearsFaintly(), "faint"), (HearsNothing(), "nothing")],
    )
    def test_each_quality_asks_the_texts_for_its_own_case(self, quality: HearingQuality, expected: str) -> None:
        """HearsClearly は when_clear、HearsMuffled は when_muffled、HearsFaintly は when_faint、HearsNothing は when_nothing の戻り値を返す。"""
        assert quality.read(_TextsNamingTheCase()) == expected
