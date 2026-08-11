"""宣言された観測文を実効照明で選ぶ規則を保証する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from ai_rpg_world.application.world_graph.declared_observation_message import (
    declared_observation_message_for_lighting,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum


@dataclass(frozen=True)
class _FixedLightingResolver:
    """試験で指定した実効照明を返す。"""

    lighting: LightingEnum

    def resolve(self, spot_id: SpotId) -> LightingEnum:
        del spot_id
        return self.lighting


@pytest.mark.parametrize(
    ("lighting", "expected"),
    [
        (LightingEnum.BRIGHT, "明所の文"),
        (LightingEnum.DIM, "明所の文"),
        (LightingEnum.DARK, "暗所の文"),
        (LightingEnum.PITCH_BLACK, "暗所の文"),
        (None, "暗所の文"),
    ],
)
def test_identity_revealing_copy_is_used_only_when_objects_are_visible(
    lighting: Optional[LightingEnum], expected: str
) -> None:
    """BRIGHT・DIM だけが明所文を使い、暗さ不明を含む残りは暗所文へ倒す。"""
    resolver = _FixedLightingResolver(lighting) if lighting is not None else None

    actual = declared_observation_message_for_lighting(
        SpotId.create(1),
        resolver=resolver,
        bright="明所の文",
        dark="暗所の文",
    )

    assert actual == expected
