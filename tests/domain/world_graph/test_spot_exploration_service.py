import pytest

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.enum.discovery_condition_type import DiscoveryConditionTypeEnum
from ai_rpg_world.domain.world_graph.service.spot_exploration_service import SpotExplorationService
from ai_rpg_world.domain.world_graph.value_object.discoverable_item import DiscoverableItem
from ai_rpg_world.domain.world_graph.value_object.discovery_condition import DiscoveryCondition


class TestSpotExplorationService:
    def test_always_discovers(self):
        spec = ItemSpecId.create(1)
        d = DiscoverableItem(
            item_spec_id=spec,
            discovery_condition=DiscoveryCondition(condition_type=DiscoveryConditionTypeEnum.ALWAYS),
            description="コイン",
        )
        interior = SpotInterior((), (), (), (d,))
        svc = SpotExplorationService()
        r = svc.explore(interior, frozenset(), 1, frozenset())
        assert r.item_spec_ids_newly_discovered == (spec,)
        assert "コイン" in r.discovery_descriptions[0]
        assert r.new_interior.discoverable_items[0].is_discovered

    def test_search_count_requires_two(self):
        """SEARCH_COUNT 未達の discoverable が残る間は、探索余地ありとして返す。"""
        spec = ItemSpecId.create(2)
        d = DiscoverableItem(
            item_spec_id=spec,
            discovery_condition=DiscoveryCondition(
                condition_type=DiscoveryConditionTypeEnum.SEARCH_COUNT,
                required_search_count=2,
            ),
        )
        interior = SpotInterior((), (), (), (d,))
        svc = SpotExplorationService()
        r1 = svc.explore(interior, frozenset(), 1, frozenset())
        assert r1.item_spec_ids_newly_discovered == ()
        assert r1.has_remaining_discoverable_items is True
        r2 = svc.explore(r1.new_interior, frozenset(), 2, frozenset())
        assert r2.item_spec_ids_newly_discovered == (spec,)
        assert r2.has_remaining_discoverable_items is False

    def test_has_item(self):
        """HAS_ITEM 未達の discoverable が残る間も、将来の探索余地ありとして返す。"""
        spec = ItemSpecId.create(3)
        d = DiscoverableItem(
            item_spec_id=spec,
            discovery_condition=DiscoveryCondition(
                condition_type=DiscoveryConditionTypeEnum.HAS_ITEM,
                required_item_spec_id=ItemSpecId.create(10),
            ),
        )
        interior = SpotInterior((), (), (), (d,))
        svc = SpotExplorationService()
        r0 = svc.explore(interior, frozenset(), 1, frozenset())
        assert r0.item_spec_ids_newly_discovered == ()
        assert r0.has_remaining_discoverable_items is True
        r1 = svc.explore(interior, frozenset({ItemSpecId.create(10)}), 1, frozenset())
        assert r1.item_spec_ids_newly_discovered == (spec,)
        assert r1.has_remaining_discoverable_items is False

    def test_empty_or_all_discovered_interiors_have_no_remaining_discoverable_items(self):
        """discoverable が無い、または全て発見済みなら探索余地なしとして返す。"""
        svc = SpotExplorationService()
        empty = svc.explore(SpotInterior((), (), (), ()), frozenset(), 1, frozenset())
        assert empty.has_remaining_discoverable_items is False

        discovered = DiscoverableItem(
            item_spec_id=ItemSpecId.create(5),
            discovery_condition=DiscoveryCondition(condition_type=DiscoveryConditionTypeEnum.ALWAYS),
            is_discovered=True,
        )
        done = svc.explore(SpotInterior((), (), (), (discovered,)), frozenset(), 1, frozenset())
        assert done.has_remaining_discoverable_items is False

    def test_flag_set(self):
        spec = ItemSpecId.create(4)
        d = DiscoverableItem(
            item_spec_id=spec,
            discovery_condition=DiscoveryCondition(
                condition_type=DiscoveryConditionTypeEnum.FLAG_SET,
                flag_name="lights_on",
            ),
        )
        interior = SpotInterior((), (), (), (d,))
        svc = SpotExplorationService()
        r0 = svc.explore(interior, frozenset(), 1, frozenset())
        assert r0.item_spec_ids_newly_discovered == ()
        r1 = svc.explore(interior, frozenset(), 1, frozenset({"lights_on"}))
        assert r1.item_spec_ids_newly_discovered == (spec,)
