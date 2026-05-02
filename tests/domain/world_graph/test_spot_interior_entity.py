import pytest

from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import UnknownSpotObjectException
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


class TestSpotInterior:
    def test_replace_object(self):
        o = SpotObject(
            object_id=SpotObjectId.create(1),
            name="A",
            description="",
            object_type=SpotObjectTypeEnum.OTHER,
            state={},
            interactions=(),
        )
        interior = SpotInterior((), (o,), (), ())
        o2 = o.with_state({"x": 1})
        ni = interior.replace_object(o2)
        assert ni.get_object(SpotObjectId.create(1)).state["x"] == 1

    def test_replace_unknown_raises(self):
        o = SpotObject(
            object_id=SpotObjectId.create(1),
            name="A",
            description="",
            object_type=SpotObjectTypeEnum.OTHER,
            state={},
            interactions=(),
        )
        interior = SpotInterior((), (o,), (), ())
        other = SpotObject(
            object_id=SpotObjectId.create(99),
            name="B",
            description="",
            object_type=SpotObjectTypeEnum.OTHER,
            state={},
            interactions=(),
        )
        with pytest.raises(UnknownSpotObjectException):
            interior.replace_object(other)
