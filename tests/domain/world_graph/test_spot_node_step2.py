from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import SpotAtmosphere


class TestSpotNodeStep2:
    def test_with_interior_and_atmosphere(self):
        interior = SpotInterior.empty()
        atm = SpotAtmosphere(lighting=LightingEnum.DIM)
        n = SpotNode(
            spot_id=SpotId.create(1),
            name="Room",
            description="",
            category=SpotCategoryEnum.DUNGEON,
            parent_id=None,
            interior=interior,
            atmosphere=atm,
        )
        assert n.interior is not None
        assert n.atmosphere is not None
        assert n.is_outdoor is False

    def test_is_outdoor_defaults_false(self):
        n = SpotNode(
            spot_id=SpotId.create(10),
            name="Indoor",
            description="",
            category=SpotCategoryEnum.DUNGEON,
            parent_id=None,
        )
        assert n.is_outdoor is False

    def test_is_outdoor_explicit_true(self):
        n = SpotNode(
            spot_id=SpotId.create(11),
            name="Outdoors",
            description="",
            category=SpotCategoryEnum.FIELD,
            parent_id=None,
            is_outdoor=True,
        )
        assert n.is_outdoor is True
