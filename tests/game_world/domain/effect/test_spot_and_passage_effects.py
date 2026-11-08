from __future__ import annotations

from ai_rpg_world.game_world.domain.action.trigger import HappeningFired
from ai_rpg_world.game_world.domain.declaration.spot import NoSmell, Temperature, Unchanged
from ai_rpg_world.game_world.domain.effect.spot_and_passage_effects import (
    ChangeAtmosphereEffect,
    ChangePassageStateEffect,
    RemovePassageEffect,
    RevealPassageEffect,
)
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.value_object import DescriptionText
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from tests.game_world.domain.effect._builders import WORLD
from tests.game_world.domain.whereabouts._builders import OPEN, door, path, spot
from tests.game_world.support.declarations_for_tests import HappeningForTests
from tests.game_world.support.world_in_memory import WorldInMemory

_PLAZA = spot("plaza")
_CELLAR = spot("cellar", Lighting.DARK)
_GATE = door("gate", "plaza", "cellar")
_TUNNEL = path("tunnel", "plaza", "cellar", hidden_until_revealed=True)
_STAIRS = path("stairs", "plaza", "cellar")
_QUAKE = HappeningFired(HappeningForTests(HappeningId("quake")))


def _world() -> WorldInMemory:
    return WorldInMemory(world=WORLD, spots=(_PLAZA, _CELLAR), passages=(_GATE, _TUNNEL, _STAIRS))


class TestPassageEffects:
    """通路の効果が、PassageStates に状態を変える・現す・無くすよう頼むことを保証する。"""

    def test_change_passage_state_opens_door(self) -> None:
        """閉じた門を open にすると、門は通れる。"""
        world = _world()

        ChangePassageStateEffect(_GATE, OPEN).apply(world.facts(), world.aggregates(), _QUAKE)

        assert world.passages.is_traversable(_GATE)

    def test_reveal_passage_makes_hidden_passage_traversable(self) -> None:
        """隠れたトンネルを現すと、トンネルは通れる。"""
        world = _world()

        RevealPassageEffect(_TUNNEL).apply(world.facts(), world.aggregates(), _QUAKE)

        assert world.passages.is_traversable(_TUNNEL)

    def test_remove_passage_makes_passage_closed(self) -> None:
        """階段を無くすと、階段は通れない道に入る。"""
        world = _world()

        RemovePassageEffect(_STAIRS).apply(world.facts(), world.aggregates(), _QUAKE)

        assert _STAIRS.passage_id in world.passages.closed_passages()


class TestChangeAtmosphereEffect:
    """ChangeAtmosphereEffect が、今の雰囲気のうち Unchanged でない欄だけを変えることを保証する。"""

    def test_changes_given_fields_and_keeps_unchanged_ones(self) -> None:
        """暗い地下室を明るくし、においを足すと、明るさとにおいだけが変わり、温度と物音は前のまま。"""
        world = _world()
        before = world.atmospheres.atmosphere_of(_CELLAR)

        ChangeAtmosphereEffect(
            _CELLAR, Lighting.BRIGHT, Unchanged(), Unchanged(), DescriptionText("焦げたにおい")
        ).apply(world.facts(), world.aggregates(), _QUAKE)

        after = world.atmospheres.atmosphere_of(_CELLAR)
        assert after.lighting is Lighting.BRIGHT
        assert after.smell == DescriptionText("焦げたにおい")
        assert after.temperature == before.temperature
        assert after.ambient_sound == before.ambient_sound

    def test_builds_on_atmosphere_changed_before(self) -> None:
        """先ににおいを足したあと温度だけを寒くすると、においは残ったまま温度が変わる。"""
        world = _world()
        ChangeAtmosphereEffect(_CELLAR, Unchanged(), Unchanged(), Unchanged(), DescriptionText("焦げたにおい")).apply(
            world.facts(), world.aggregates(), _QUAKE
        )

        ChangeAtmosphereEffect(_CELLAR, Unchanged(), Temperature.COLD, Unchanged(), Unchanged()).apply(
            world.facts(), world.aggregates(), _QUAKE
        )

        after = world.atmospheres.atmosphere_of(_CELLAR)
        assert after.smell == DescriptionText("焦げたにおい")
        assert after.temperature is Temperature.COLD

    def test_can_clear_smell(self) -> None:
        """においを NoSmell にすると、においが消える。"""
        world = _world()
        ChangeAtmosphereEffect(_CELLAR, Unchanged(), Unchanged(), Unchanged(), DescriptionText("焦げたにおい")).apply(
            world.facts(), world.aggregates(), _QUAKE
        )

        ChangeAtmosphereEffect(_CELLAR, Unchanged(), Unchanged(), Unchanged(), NoSmell()).apply(
            world.facts(), world.aggregates(), _QUAKE
        )

        assert world.atmospheres.atmosphere_of(_CELLAR).smell == NoSmell()
