"""共通シナリオ述語が不可能な定義を構築時に拒否する仕様。"""

import pytest

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ScenarioPredicateValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_predicate import (
    EntityAtSpotPredicate,
    EntityCountAtSpotAtLeastPredicate,
    FlagSetPredicate,
    ItemSpecOwnedPredicate,
    TickAtLeastPredicate,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


class TestFlagSetPredicate:
    """世界フラグ名の型と空白条件を保証する。"""

    @pytest.mark.parametrize("flag_name", [None, "", "   ", 1, True])
    def test_rejects_missing_empty_or_non_string_name(self, flag_name: object) -> None:
        """空・空白のみ・文字列以外のフラグ名は定義時に拒否する。"""
        with pytest.raises(ScenarioPredicateValidationException):
            FlagSetPredicate(flag_name)  # type: ignore[arg-type]

    def test_preserves_exact_name_without_normalization(self) -> None:
        """大文字小文字や前後空白を勝手に変えず、完全一致用の名前を保持する。"""
        predicate = FlagSetPredicate(" Flag_A ")

        assert predicate.flag_name == " Flag_A "


class TestTickAtLeastPredicate:
    """tick閾値の型を保証し、既存の負数整数は意味を変えず保持する。"""

    @pytest.mark.parametrize("threshold", [None, True, False, "10", 1.5])
    def test_rejects_non_integer_threshold(self, threshold: object) -> None:
        """boolを含む整数以外の閾値は、型付き述語の構築時に拒否する。"""
        with pytest.raises(ScenarioPredicateValidationException):
            TickAtLeastPredicate(threshold)  # type: ignore[arg-type]

    @pytest.mark.parametrize("threshold", [-1, 0, 10])
    def test_preserves_integer_threshold(self, threshold: int) -> None:
        """入力厳格化を別PRへ分けるため、既存が受理する負数を含む整数を保持する。"""
        assert TickAtLeastPredicate(threshold).threshold == threshold


class TestLocationPredicates:
    """場所述語が明示entityと在席数の異なる意味を型で保持する。"""

    @pytest.mark.parametrize(
        ("entity_id", "spot_id"),
        [(1, SpotId.create(1)), (EntityId.create(1), 1), (None, SpotId.create(1))],
    )
    def test_entity_at_spot_rejects_untyped_ids(
        self, entity_id: object, spot_id: object,
    ) -> None:
        """本人位置の述語はEntityIdとSpotId以外を構築時に拒否する。"""
        with pytest.raises(ScenarioPredicateValidationException):
            EntityAtSpotPredicate(entity_id, spot_id)  # type: ignore[arg-type]

    @pytest.mark.parametrize("required_count", [0, -1, True, 1.5, "2"])
    def test_entity_count_rejects_non_positive_or_non_integer_threshold(
        self, required_count: object,
    ) -> None:
        """在席数の閾値はboolを除く正整数だけを受理する。"""
        with pytest.raises(ScenarioPredicateValidationException):
            EntityCountAtSpotAtLeastPredicate(
                SpotId.create(1), required_count,  # type: ignore[arg-type]
            )

    def test_location_predicates_preserve_typed_values(self) -> None:
        """正しいIDと人数を正規化せず、そのまま保持する。"""
        entity_id = EntityId.create(1)
        spot_id = SpotId.create(2)

        assert EntityAtSpotPredicate(entity_id, spot_id).entity_id == entity_id
        assert EntityCountAtSpotAtLeastPredicate(spot_id, 2).required_count == 2


class TestItemSpecOwnedPredicate:
    """所持述語が数量や所有者を持たず、品目IDだけを型で表すことを保証する。"""

    @pytest.mark.parametrize("item_spec_id", [None, 1, "1", True])
    def test_rejects_untyped_item_spec_id(self, item_spec_id: object) -> None:
        """ItemSpecId以外を受け入れず、整数IDとの取り違えを構築時に拒否する。"""
        with pytest.raises(ScenarioPredicateValidationException):
            ItemSpecOwnedPredicate(item_spec_id)  # type: ignore[arg-type]

    def test_preserves_typed_item_spec_id(self) -> None:
        """正しいItemSpecIdを正規化せず、そのまま保持する。"""
        item_spec_id = ItemSpecId.create(7)

        assert ItemSpecOwnedPredicate(item_spec_id).item_spec_id == item_spec_id
