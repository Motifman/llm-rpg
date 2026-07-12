"""HeardClaim (P9 伝聞) の不変条件を保証する。

speaker (話者) と claim (主張) の両方が非空であること、前後空白が除かれること。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.memory.episodic.exception.episodic_exception import (
    HeardClaimValidationException,
)
from ai_rpg_world.domain.memory.episodic.value_object.heard_claim import HeardClaim


class TestHeardClaim:
    def test_valid_claim_constructs_and_strips(self) -> None:
        c = HeardClaim(speaker="  リオ ", claim=" 岩礁海岸は山に通じていない ")
        assert c.speaker == "リオ"
        assert c.claim == "岩礁海岸は山に通じていない"

    def test_empty_speaker_raises(self) -> None:
        with pytest.raises(HeardClaimValidationException):
            HeardClaim(speaker="   ", claim="何かの主張")

    def test_empty_claim_raises(self) -> None:
        with pytest.raises(HeardClaimValidationException):
            HeardClaim(speaker="リオ", claim="")

    def test_non_str_raises(self) -> None:
        with pytest.raises(HeardClaimValidationException):
            HeardClaim(speaker=None, claim="x")  # type: ignore[arg-type]
