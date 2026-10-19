import pytest

from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.entity.sub_location import SubLocation
from ai_rpg_world.domain.world_graph.enum.discovery_condition_type import DiscoveryConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import UnknownSpotObjectException
from ai_rpg_world.domain.world_graph.value_object.discoverable_item import DiscoverableItem
from ai_rpg_world.domain.world_graph.value_object.discovery_condition import DiscoveryCondition
from ai_rpg_world.domain.world_graph.value_object.ground_item import GroundItem
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId


def _ground(instance_id: int, spec_id: int) -> GroundItem:
    return GroundItem(
        item_instance_id=ItemInstanceId.create(instance_id),
        item_spec_id=ItemSpecId.create(spec_id),
    )


class TestSpotInterior:
    @pytest.mark.parametrize("with_other_contents", [False, True])
    def test_replace_object(self, with_other_contents: bool):
        """指定物体だけを差し替え、別の物体・他の集合と元の内部構造を保つ。"""
        o = SpotObject(
            object_id=SpotObjectId.create(1),
            name="A",
            description="",
            object_type=SpotObjectTypeEnum.OTHER,
            state={},
            interactions=(),
        )
        other = SpotObject(
            object_id=SpotObjectId.create(2), name="B", description="別の物体",
            object_type=SpotObjectTypeEnum.OTHER, state={"untouched": True}, interactions=(),
        )
        sub = SubLocation(SubLocationId.create(1), "隅", "部屋の隅", (), False)
        ground = _ground(5, 100)
        discoverable = DiscoverableItem(
            ItemSpecId.create(200),
            DiscoveryCondition(DiscoveryConditionTypeEnum.ALWAYS),
        )
        interior = (
            SpotInterior((sub,), (other, o), (ground,), (discoverable,))
            if with_other_contents else SpotInterior((), (o,), (), ())
        )
        o2 = o.with_state({"x": 1})
        ni = interior.replace_object(o2)
        assert ni.get_object(SpotObjectId.create(1)).state["x"] == 1
        assert interior.get_object(SpotObjectId.create(1)).state == {}
        if with_other_contents:
            assert ni.objects == (other, o2)
            assert ni.sub_locations == (sub,)
            assert ni.ground_items == (ground,)
            assert ni.discoverable_items == (discoverable,)
            assert interior.objects == (other, o)
        else:
            assert ni.objects == (o2,)

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


class TestSpotInteriorGroundItems:
    """SpotInterior.with_ground_item / without_ground_item / find_ground_item の挙動。"""

    def test_with_ground_item_adds_new_item(self):
        """with_ground_item が指定 GroundItem を ground_items に追加して新インスタンスを返す。"""
        interior = SpotInterior((), (), (), ())
        g = _ground(1, 100)
        ni = interior.with_ground_item(g)
        assert len(ni.ground_items) == 1
        assert ni.ground_items[0] == g
        # 元の interior は不変 (immutability の確認)
        assert interior.ground_items == ()

    def test_ground_item_same_instance(self):
        """同一 ItemInstanceId が既に存在する場合は重複追加しない (idempotent)。"""
        g = _ground(1, 100)
        interior = SpotInterior((), (), (g,), ())
        ni = interior.with_ground_item(g)
        assert len(ni.ground_items) == 1
        assert ni.ground_items == (g,)

        other = _ground(2, 200)
        populated = SpotInterior((), (), (g, other), ())
        duplicate_id = _ground(1, 999)
        retried = populated.with_ground_item(duplicate_id)
        assert retried.ground_items == (g, other)
        assert populated.ground_items == (g, other)

    def test_excludes_ground_item_instance(self):
        """既存メソッド without_ground_item の回帰テスト。"""
        g1 = _ground(1, 100)
        g2 = _ground(2, 200)
        interior = SpotInterior((), (), (g1, g2), ())
        ni = interior.without_ground_item(g1.item_instance_id)
        assert len(ni.ground_items) == 1
        assert ni.ground_items[0] == g2

    def test_returns_find_ground_item_instance(self):
        """find_ground_item が ItemInstanceId で GroundItem を取り出せる。"""
        g = _ground(1, 100)
        interior = SpotInterior((), (), (g,), ())
        assert interior.find_ground_item(g.item_instance_id) == g
        other = _ground(2, 200)
        populated = SpotInterior((), (), (other, g), ())
        assert populated.find_ground_item(g.item_instance_id) == g

    def test_find_ground_item_none(self):
        """find_ground_item は地面にない instance に対しては None を返す。"""
        interior = SpotInterior((), (), (), ())
        assert interior.find_ground_item(ItemInstanceId.create(99)) is None
        populated = SpotInterior((), (), (_ground(1, 100),), ())
        assert populated.find_ground_item(ItemInstanceId.create(99)) is None
