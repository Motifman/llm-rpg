"""SpotPerceptionService のユニットテスト。

「現実世界だったらどう見えるか？」を基準に知覚判定を検証する。
"""

from __future__ import annotations

from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.service.spot_perception_service import SpotPerceptionService
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import SpotAtmosphere


def _atmosphere(lighting: LightingEnum) -> SpotAtmosphere:
    return SpotAtmosphere(lighting=lighting)


class TestEffectiveLighting:
    """照明 + 光源から実効照明を計算するテスト"""

    def test_bright_unchanged(self) -> None:
        """明るい部屋は光源有無にかかわらずBRIGHT"""
        svc = SpotPerceptionService()
        assert svc.compute_effective_lighting(_atmosphere(LightingEnum.BRIGHT), False) == LightingEnum.BRIGHT
        assert svc.compute_effective_lighting(_atmosphere(LightingEnum.BRIGHT), True) == LightingEnum.BRIGHT

    def test_dim_unchanged(self) -> None:
        """薄暗い部屋は光源有無にかかわらずDIM"""
        svc = SpotPerceptionService()
        assert svc.compute_effective_lighting(_atmosphere(LightingEnum.DIM), False) == LightingEnum.DIM

    def test_dark_without_light_stays_dark(self) -> None:
        """暗闇で光源なしはDARKのまま"""
        svc = SpotPerceptionService()
        assert svc.compute_effective_lighting(_atmosphere(LightingEnum.DARK), False) == LightingEnum.DARK

    def test_dark_with_light_becomes_dim(self) -> None:
        """暗闇で誰かが光源を持てばDIMに引き上がる"""
        svc = SpotPerceptionService()
        assert svc.compute_effective_lighting(_atmosphere(LightingEnum.DARK), True) == LightingEnum.DIM

    def test_pitch_black_with_light_becomes_dim(self) -> None:
        """完全な暗闇でも光源があればDIM"""
        svc = SpotPerceptionService()
        assert svc.compute_effective_lighting(_atmosphere(LightingEnum.PITCH_BLACK), True) == LightingEnum.DIM

    def test_pitch_black_without_light_stays(self) -> None:
        """完全な暗闇で光源なしはPITCH_BLACK"""
        svc = SpotPerceptionService()
        assert svc.compute_effective_lighting(_atmosphere(LightingEnum.PITCH_BLACK), False) == LightingEnum.PITCH_BLACK

    def test_no_atmosphere_defaults_bright(self) -> None:
        """雰囲気未設定はBRIGHT"""
        svc = SpotPerceptionService()
        assert svc.compute_effective_lighting(None, False) == LightingEnum.BRIGHT


class TestCanSeeObjects:
    """オブジェクト視認可否のテスト"""

    def test_bright_can_see(self) -> None:
        svc = SpotPerceptionService()
        assert svc.can_see_objects(LightingEnum.BRIGHT) is True

    def test_dim_can_see(self) -> None:
        svc = SpotPerceptionService()
        assert svc.can_see_objects(LightingEnum.DIM) is True

    def test_dark_cannot_see(self) -> None:
        svc = SpotPerceptionService()
        assert svc.can_see_objects(LightingEnum.DARK) is False

    def test_pitch_black_cannot_see(self) -> None:
        svc = SpotPerceptionService()
        assert svc.can_see_objects(LightingEnum.PITCH_BLACK) is False


class TestLightingPerceptionText:
    """照明知覚テキストのテスト"""

    def test_bright_no_note(self) -> None:
        """明るい部屋では補足テキストなし"""
        svc = SpotPerceptionService()
        assert svc.describe_lighting_perception(
            LightingEnum.BRIGHT, LightingEnum.BRIGHT, False, None
        ) is None

    def test_dark_with_own_light(self) -> None:
        """自分が光源を持つ場合の知覚テキスト"""
        svc = SpotPerceptionService()
        note = svc.describe_lighting_perception(
            LightingEnum.DARK, LightingEnum.DIM, True, None
        )
        assert note is not None
        assert "手元" in note

    def test_dark_with_companion_light(self) -> None:
        """同行者が光源を持つ場合の知覚テキスト"""
        svc = SpotPerceptionService()
        note = svc.describe_lighting_perception(
            LightingEnum.DARK, LightingEnum.DIM, False, "太郎"
        )
        assert note is not None
        assert "太郎" in note

    def test_pitch_black_no_light(self) -> None:
        """完全な暗闇で光源なしの知覚テキスト"""
        svc = SpotPerceptionService()
        note = svc.describe_lighting_perception(
            LightingEnum.PITCH_BLACK, LightingEnum.PITCH_BLACK, False, None
        )
        assert note is not None
        assert "暗闇" in note

    def test_dark_no_light(self) -> None:
        """暗闇で光源なしの知覚テキスト"""
        svc = SpotPerceptionService()
        note = svc.describe_lighting_perception(
            LightingEnum.DARK, LightingEnum.DARK, False, None
        )
        assert note is not None
        assert "見えない" in note
