from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.spot import (
    NoAmbientSound,
    NoSmell,
    SpotAtmosphere,
    Temperature,
    Unchanged,
)
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.value_object import DescriptionText


def _cellar() -> SpotAtmosphere:
    return SpotAtmosphere(
        lighting=Lighting.DARK,
        outdoor=False,
        temperature=Temperature.COLD,
        ambient_sound=DescriptionText("水の滴る音"),
        smell=DescriptionText("かびの匂い"),
    )


class TestSpotAtmosphereWithChanges:
    """SpotAtmosphere.with_changes が、Unchanged を渡した欄を元のまま残し、ほかの欄だけ変えた新しい雰囲気を返すことを保証する。"""

    def test_all_unchanged_returns_an_equal_atmosphere(self) -> None:
        """4 つの欄すべてに Unchanged を渡すと、元と等しい雰囲気が返る。"""
        original = _cellar()

        changed = original.with_changes(
            lighting=Unchanged(), temperature=Unchanged(), ambient_sound=Unchanged(), smell=Unchanged()
        )

        assert changed == original

    def test_only_given_fields_change_and_unchanged_fields_keep_their_values(self) -> None:
        """明るさと温度だけ値を渡すと、その 2 つだけ変わり、音と匂いと屋外かどうかは元のまま残る。"""
        original = _cellar()

        changed = original.with_changes(
            lighting=Lighting.BRIGHT, temperature=Temperature.WARM, ambient_sound=Unchanged(), smell=Unchanged()
        )

        assert changed == SpotAtmosphere(
            lighting=Lighting.BRIGHT,
            outdoor=False,
            temperature=Temperature.WARM,
            ambient_sound=DescriptionText("水の滴る音"),
            smell=DescriptionText("かびの匂い"),
        )

    def test_sound_and_smell_can_be_changed_to_none(self) -> None:
        """音に NoAmbientSound、匂いに NoSmell を渡すと、音も匂いも無い雰囲気になる。"""
        original = _cellar()

        changed = original.with_changes(
            lighting=Unchanged(), temperature=Unchanged(), ambient_sound=NoAmbientSound(), smell=NoSmell()
        )

        assert changed.ambient_sound == NoAmbientSound()
        assert changed.smell == NoSmell()

    def test_with_changes_leaves_the_original_atmosphere_as_it_was(self) -> None:
        """with_changes を呼んでも、呼ばれた側の雰囲気は変わらない。"""
        original = _cellar()

        original.with_changes(
            lighting=Lighting.BRIGHT,
            temperature=Temperature.HOT,
            ambient_sound=DescriptionText("風の音"),
            smell=NoSmell(),
        )

        assert original == _cellar()
