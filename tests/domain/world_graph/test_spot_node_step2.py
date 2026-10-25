import pytest

from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import SpotAtmosphere
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


class TestSpotNodeStep2:
    @pytest.mark.parametrize("with_object", [False, True])
    def test_with_interior_and_atmosphere(self, with_object: bool):
        """指定した内部構造とDIMの雰囲気を値ごと保持し、屋内を既定とする。"""
        obj = SpotObject(
            SpotObjectId.create(7),
            "机",
            "木製",
            SpotObjectTypeEnum.OTHER,
            {"opened": False},
            (),
        )
        interior = SpotInterior((), (obj,), (), ()) if with_object else SpotInterior.empty()
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
        assert n.interior == interior
        assert n.atmosphere == atm
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
