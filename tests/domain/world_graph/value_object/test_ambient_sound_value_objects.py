"""AmbientSound 系値オブジェクトのテスト。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.value_object.ambient_sound_atlas import (
    AmbientSoundAtlas,
    AmbientSoundConfig,
    AmbientSoundThrottleConfig,
)
from ai_rpg_world.domain.world_graph.value_object.ambient_sound_def import (
    AmbientSoundDef,
)
from ai_rpg_world.domain.world_graph.value_object.ambient_sound_filter import (
    AmbientSoundFilter,
)


def _def(*, id_: str, tags: tuple = ()) -> AmbientSoundDef:
    return AmbientSoundDef(
        id=id_,
        tags=frozenset(tags),
        prose="どこかで音がする",
        probability_per_tick=0.05,
        sound_strength=0.3,
        filters=AmbientSoundFilter(),
    )


class TestAmbientSoundFilter:
    def test_default_matches_anything(self):
        f = AmbientSoundFilter()
        assert f.matches_phase("night") is True
        assert f.matches_phase(None) is True
        assert f.matches_weather("RAIN") is True
        assert f.matches_weather(None) is True
        assert f.matches_outdoor(True) is True
        assert f.matches_outdoor(False) is True

    def test_phases_filter(self):
        f = AmbientSoundFilter(phases=frozenset({"night"}))
        assert f.matches_phase("night") is True
        assert f.matches_phase("day") is False
        assert f.matches_phase(None) is False

    def test_weather_filter(self):
        f = AmbientSoundFilter(weather_types=frozenset({"RAIN"}))
        assert f.matches_weather("RAIN") is True
        assert f.matches_weather("CLEAR") is False
        assert f.matches_weather(None) is False

    def test_indoor_only_blocks_outdoor(self):
        f = AmbientSoundFilter(indoor_only=True)
        assert f.matches_outdoor(False) is True
        assert f.matches_outdoor(True) is False

    def test_outdoor_only_blocks_indoor(self):
        f = AmbientSoundFilter(outdoor_only=True)
        assert f.matches_outdoor(True) is True
        assert f.matches_outdoor(False) is False

    def test_both_only_flags_rejected(self):
        with pytest.raises(ValueError):
            AmbientSoundFilter(indoor_only=True, outdoor_only=True)


class TestAmbientSoundDef:
    def test_valid_def(self):
        d = _def(id_="x", tags=("a",))
        assert d.id == "x"

    @pytest.mark.parametrize("p", [-0.01, 1.01])
    def test_probability_out_of_range(self, p):
        with pytest.raises(ValueError, match="probability"):
            AmbientSoundDef(
                id="x", tags=frozenset(), prose="p",
                probability_per_tick=p, sound_strength=0.5,
                filters=AmbientSoundFilter(),
            )

    @pytest.mark.parametrize("s", [-0.01, 1.01])
    def test_strength_out_of_range(self, s):
        with pytest.raises(ValueError, match="sound_strength"):
            AmbientSoundDef(
                id="x", tags=frozenset(), prose="p",
                probability_per_tick=0.5, sound_strength=s,
                filters=AmbientSoundFilter(),
            )

    def test_empty_id_rejected(self):
        with pytest.raises(ValueError, match="id"):
            AmbientSoundDef(
                id="", tags=frozenset(), prose="p",
                probability_per_tick=0.5, sound_strength=0.5,
                filters=AmbientSoundFilter(),
            )

    def test_empty_prose_rejected(self):
        with pytest.raises(ValueError, match="prose"):
            AmbientSoundDef(
                id="x", tags=frozenset(), prose="",
                probability_per_tick=0.5, sound_strength=0.5,
                filters=AmbientSoundFilter(),
            )


class TestAmbientSoundAtlas:
    def test_empty_atlas(self):
        atlas = AmbientSoundAtlas(defs=())
        assert atlas.is_empty()
        assert atlas.candidates_for_tags(frozenset({"x"})) == ()

    def test_duplicate_ids_rejected(self):
        with pytest.raises(ValueError, match="Duplicate"):
            AmbientSoundAtlas(defs=(_def(id_="a"), _def(id_="a")))

    def test_find_by_id(self):
        atlas = AmbientSoundAtlas(defs=(_def(id_="drip"), _def(id_="wind")))
        assert atlas.find_by_id("drip") is not None
        assert atlas.find_by_id("none") is None

    def test_candidates_for_tags_intersects(self):
        atlas = AmbientSoundAtlas(defs=(
            _def(id_="a", tags=("wet",)),
            _def(id_="b", tags=("windy",)),
            _def(id_="c", tags=("wet", "abandoned")),
        ))
        result = atlas.candidates_for_tags(frozenset({"wet"}))
        assert {d.id for d in result} == {"a", "c"}

    def test_candidates_with_empty_spot_tags(self):
        atlas = AmbientSoundAtlas(defs=(_def(id_="a", tags=("wet",)),))
        assert atlas.candidates_for_tags(frozenset()) == ()


class TestAmbientSoundThrottleConfig:
    def test_negative_gap_rejected(self):
        with pytest.raises(ValueError):
            AmbientSoundThrottleConfig(min_gap_ticks_per_player=-1)

    def test_negative_dedup_rejected(self):
        with pytest.raises(ValueError):
            AmbientSoundThrottleConfig(dedup_window_size=-1)


class TestAmbientSoundConfig:
    def test_invalid_interval_rejected(self):
        with pytest.raises(ValueError):
            AmbientSoundConfig(
                enabled=True,
                update_interval_ticks=0,
                throttle=AmbientSoundThrottleConfig(),
                atlas=AmbientSoundAtlas(defs=()),
            )

    def test_valid_config(self):
        cfg = AmbientSoundConfig(
            enabled=True,
            update_interval_ticks=3,
            throttle=AmbientSoundThrottleConfig(),
            atlas=AmbientSoundAtlas(defs=()),
        )
        assert cfg.update_interval_ticks == 3
