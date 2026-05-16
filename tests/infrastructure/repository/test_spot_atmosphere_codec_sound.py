"""SpotAtmosphere の sound_intensity round-trip テスト (Phase 5)。

検証対象:
- to_dict / from_dict で sound_intensity が保存・復元される
- 旧スキーマ (sound_intensity 無し) は SILENT としてロードされる (後方互換)
"""

from __future__ import annotations

from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.sound_intensity_enum import (
    SoundIntensityEnum,
)
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.infrastructure.repository.sqlite_world_graph_state_codec import (
    _spot_atmosphere_from_dict,
    _spot_atmosphere_to_dict,
)


class TestSoundIntensityRoundTrip:
    """sound_intensity が dict 経由で round-trip する。"""

    def test_MODERATE_の_round_trip(self) -> None:
        atmosphere = SpotAtmosphere(
            lighting=LightingEnum.BRIGHT,
            sound_ambient="川のせせらぎ",
            temperature=TemperatureEnum.NORMAL,
            sound_intensity=SoundIntensityEnum.MODERATE,
        )
        d = _spot_atmosphere_to_dict(atmosphere)
        assert d["sound_intensity"] == "MODERATE"

        restored = _spot_atmosphere_from_dict(d)
        assert restored.sound_intensity == SoundIntensityEnum.MODERATE
        assert restored.sound_ambient == "川のせせらぎ"

    def test_default_SILENT_が_round_trip(self) -> None:
        atmosphere = SpotAtmosphere(lighting=LightingEnum.BRIGHT)
        d = _spot_atmosphere_to_dict(atmosphere)
        assert d["sound_intensity"] == "SILENT"

        restored = _spot_atmosphere_from_dict(d)
        assert restored.sound_intensity == SoundIntensityEnum.SILENT


class TestLegacyCompat:
    """旧スキーマ (sound_intensity フィールド無し) でも SILENT 復元。"""

    def test_旧_dict_は_SILENT_で_復元される(self) -> None:
        legacy_dict = {
            "lighting": "BRIGHT",
            "sound_ambient": "古い音の説明",
            "temperature": "NORMAL",
            "smell": None,
            # sound_intensity が無い
        }
        restored = _spot_atmosphere_from_dict(legacy_dict)
        assert restored.sound_intensity == SoundIntensityEnum.SILENT
        assert restored.sound_ambient == "古い音の説明"
