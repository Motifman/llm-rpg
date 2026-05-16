"""SoundIntensityEnum の単体テスト (Phase 5)。

検証対象:
- level プロパティが 0-3 で順序付け
- attenuate(hops) で 1 段階ずつ減衰
- SILENT はそれ以上減衰しない
- LOUD → MODERATE → FAINT → SILENT の連鎖
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.enum.sound_intensity_enum import (
    SoundIntensityEnum,
)


class TestLevelOrdering:
    """level は 0 (静寂) - 3 (大音響) の整数で順序付け可能。"""

    def test_level_は_期待値(self) -> None:
        assert SoundIntensityEnum.SILENT.level == 0
        assert SoundIntensityEnum.FAINT.level == 1
        assert SoundIntensityEnum.MODERATE.level == 2
        assert SoundIntensityEnum.LOUD.level == 3

    def test_level_比較で_順序_を_扱える(self) -> None:
        # 直接比較ではなく level 整数経由で順序判定
        assert SoundIntensityEnum.LOUD.level > SoundIntensityEnum.SILENT.level
        assert SoundIntensityEnum.MODERATE.level > SoundIntensityEnum.FAINT.level


class TestAttenuate:
    """1 hop ごとに 1 段階減衰、SILENT 以下にはならない。"""

    def test_LOUD_1hop_は_MODERATE(self) -> None:
        assert (
            SoundIntensityEnum.LOUD.attenuate(1)
            == SoundIntensityEnum.MODERATE
        )

    def test_LOUD_2hop_は_FAINT(self) -> None:
        assert SoundIntensityEnum.LOUD.attenuate(2) == SoundIntensityEnum.FAINT

    def test_LOUD_3hop_は_SILENT(self) -> None:
        assert SoundIntensityEnum.LOUD.attenuate(3) == SoundIntensityEnum.SILENT

    def test_LOUD_4hop_でも_SILENT_を_維持(self) -> None:
        """SILENT 以下にはならない (clamp)。"""
        assert SoundIntensityEnum.LOUD.attenuate(4) == SoundIntensityEnum.SILENT

    def test_SILENT_は_何_hop_減衰しても_SILENT(self) -> None:
        assert (
            SoundIntensityEnum.SILENT.attenuate(5)
            == SoundIntensityEnum.SILENT
        )

    def test_hops_0_以下は_減衰なし(self) -> None:
        assert SoundIntensityEnum.MODERATE.attenuate(0) == SoundIntensityEnum.MODERATE
        assert SoundIntensityEnum.MODERATE.attenuate(-1) == SoundIntensityEnum.MODERATE

    def test_default_hops_は_1(self) -> None:
        assert (
            SoundIntensityEnum.LOUD.attenuate()
            == SoundIntensityEnum.MODERATE
        )
