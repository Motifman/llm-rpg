import pytest
from unittest.mock import MagicMock

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.enum.discovery_condition_type import DiscoveryConditionTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ScenarioPredicateEvaluationException,
)
from ai_rpg_world.domain.world_graph.service.spot_exploration_service import SpotExplorationService
from ai_rpg_world.domain.world_graph.value_object.discoverable_item import DiscoverableItem
from ai_rpg_world.domain.world_graph.value_object.discovery_condition import DiscoveryCondition
from ai_rpg_world.domain.world_graph.value_object.predicate_result import PredicateResult


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

    def test_flag_set_delegates_to_typed_common_evaluator(self):
        """発見済み管理を保ち、未発見物の世界フラグ判定だけを共通核へ委譲する。"""
        common = MagicMock()
        common.evaluate.return_value = PredicateResult.satisfied()
        spec = ItemSpecId.create(6)
        discoverable = DiscoverableItem(
            item_spec_id=spec,
            discovery_condition=DiscoveryCondition(
                condition_type=DiscoveryConditionTypeEnum.FLAG_SET,
                flag_name="lights_on",
            ),
        )

        result = SpotExplorationService(
            predicate_evaluator=common
        ).explore(
            SpotInterior((), (), (), (discoverable,)),
            frozenset(),
            1,
            frozenset(),
        )

        assert result.item_spec_ids_newly_discovered == (spec,)
        predicate, context = common.evaluate.call_args.args
        assert predicate.flag_name == "lights_on"
        assert context.world_flags == frozenset()

    def test_has_item_delegates_resolved_ownership_to_common_evaluator(self):
        """探索者の所持集合を渡し、未発見物の品目判定だけを共通核へ委譲する。"""
        common = MagicMock()
        common.evaluate.return_value = PredicateResult.satisfied()
        required = ItemSpecId.create(8)
        reward = ItemSpecId.create(9)
        discoverable = DiscoverableItem(
            item_spec_id=reward,
            discovery_condition=DiscoveryCondition(
                condition_type=DiscoveryConditionTypeEnum.HAS_ITEM,
                required_item_spec_id=required,
            ),
        )

        result = SpotExplorationService(common).explore(
            SpotInterior((), (), (), (discoverable,)),
            frozenset({required}),
            1,
            frozenset(),
        )

        assert result.item_spec_ids_newly_discovered == (reward,)
        predicate, context = common.evaluate.call_args.args
        assert predicate.item_spec_id == required
        assert context.owned_item_spec_ids == frozenset({required})

    @pytest.mark.parametrize("reason", ["missing", "unsupported"])
    def test_has_item_evaluation_failure_stops_exploration(self, reason):
        """所持共通核の入力不足・未対応を、未発見という通常状態へ縮退させない。"""
        common = MagicMock()
        failed = MagicMock()
        common.evaluate.return_value = (
            PredicateResult.context_missing(
                failed_predicate=failed,
                failed_path=(),
                required_context={"owned_item_spec_ids"},
            )
            if reason == "missing"
            else PredicateResult.unsupported(failed_predicate=failed, failed_path=())
        )
        discoverable = DiscoverableItem(
            item_spec_id=ItemSpecId.create(9),
            discovery_condition=DiscoveryCondition(
                condition_type=DiscoveryConditionTypeEnum.HAS_ITEM,
                required_item_spec_id=ItemSpecId.create(8),
            ),
        )

        with pytest.raises(ScenarioPredicateEvaluationException):
            SpotExplorationService(common).explore(
                SpotInterior((), (), (), (discoverable,)),
                frozenset(),
                1,
                frozenset(),
            )

    @pytest.mark.parametrize("reason", ["missing", "unsupported"])
    def test_flag_set_evaluation_failure_stops_exploration(self, reason):
        """共通評価核の入力不足・未対応は、未発見のまま静かに残さない。"""
        common = MagicMock()
        failed = MagicMock()
        common.evaluate.return_value = (
            PredicateResult.context_missing(
                failed_predicate=failed,
                failed_path=(),
                required_context={"world_flags"},
            )
            if reason == "missing"
            else PredicateResult.unsupported(
                failed_predicate=failed,
                failed_path=(),
            )
        )
        discoverable = DiscoverableItem(
            item_spec_id=ItemSpecId.create(7),
            discovery_condition=DiscoveryCondition(
                condition_type=DiscoveryConditionTypeEnum.FLAG_SET,
                flag_name="lights_on",
            ),
        )

        with pytest.raises(ScenarioPredicateEvaluationException):
            SpotExplorationService(predicate_evaluator=common).explore(
                SpotInterior((), (), (), (discoverable,)),
                frozenset(),
                1,
                frozenset(),
            )
