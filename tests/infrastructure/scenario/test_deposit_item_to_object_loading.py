"""投入 effect と整数 state 条件を、曖昧さの無い宣言として読み込むことを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.infrastructure.scenario.parse_interaction_conditions import (
    parse_interaction_condition,
)
from ai_rpg_world.infrastructure.scenario.parse_interaction_effects import (
    parse_interaction_effect,
)
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper
from ai_rpg_world.domain.player.value_object.player_attribute_spec import (
    PlayerAttributeSpecs,
)

#: この試験は属性の宣言を扱わない。**空を渡すのが正しい。**
#: 宣言が無ければ、宣言に由来する検査は何も落とさない。
_NO_ATTRIBUTES = PlayerAttributeSpecs.empty()
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoadError


@pytest.fixture()
def mapper() -> ScenarioIdMapper:
    result = ScenarioIdMapper()
    result.register("item_spec", "driftwood")
    result.register("object", "signal_fire_pit")
    return result


class TestDepositItemToObjectLoading:
    """投入数や対象 state を暗黙に補わず、必要な宣言を読み込み時に固定する。"""

    def test_loads_all_quantity_and_resolves_string_ids(
        self, mapper: ScenarioIdMapper
    ) -> None:
        """item_spec・target_object を数値 ID に解決し、quantity=all を保持する。"""
        effect = parse_interaction_effect(
            {
                "effect_type": "DEPOSIT_ITEM_TO_OBJECT",
                "parameters": {
                    "item_spec": "driftwood",
                    "target_object": "signal_fire_pit",
                    "state_key": "driftwood_stacked",
                    "quantity": "all",
                },
            },
            mapper,
            player_attribute_specs=_NO_ATTRIBUTES,
        )

        assert effect.parameters == {
            "item_spec_id": mapper.get_int("item_spec", "driftwood"),
            "object_id": mapper.get_int("object", "signal_fire_pit"),
            "state_key": "driftwood_stacked",
            "quantity": "all",
        }

    @pytest.mark.parametrize("missing", ["item_spec", "state_key", "quantity"])
    def test_required_parameter_omission_fails_fast(
        self, mapper: ScenarioIdMapper, missing: str
    ) -> None:
        """item_spec・state_key・quantity の省略は既定値へ縮退せず読み込み時に拒否する。"""
        parameters = {
            "item_spec": "driftwood",
            "state_key": "driftwood_stacked",
            "quantity": "all",
        }
        parameters.pop(missing)

        with pytest.raises(ScenarioLoadError, match=missing):
            parse_interaction_effect(
                {
                    "effect_type": "DEPOSIT_ITEM_TO_OBJECT",
                    "parameters": parameters,
                },
                mapper,
                player_attribute_specs=_NO_ATTRIBUTES,
            )

    @pytest.mark.parametrize("quantity", [0, -1, "some"])
    def test_invalid_quantity_fails_fast(
        self, mapper: ScenarioIdMapper, quantity: object
    ) -> None:
        """quantity は正の整数か all だけを許し、曖昧な値を実行時へ持ち越さない。"""
        with pytest.raises(ScenarioLoadError, match="quantity"):
            parse_interaction_effect(
                {
                    "effect_type": "DEPOSIT_ITEM_TO_OBJECT",
                    "parameters": {
                        "item_spec": "driftwood",
                        "state_key": "driftwood_stacked",
                        "quantity": quantity,
                    },
                },
                mapper,
                player_attribute_specs=_NO_ATTRIBUTES,
            )

    def test_scenario_event_context_fails_fast(self, mapper: ScenarioIdMapper) -> None:
        """行為者のいない scenario_event では所持品を引けないため、読み込み時に拒否する。"""
        with pytest.raises(ScenarioLoadError, match="acting player"):
            parse_interaction_effect(
                {
                    "effect_type": "DEPOSIT_ITEM_TO_OBJECT",
                    "parameters": {
                        "item_spec": "driftwood",
                        "state_key": "driftwood_stacked",
                        "quantity": "all",
                    },
                },
                mapper,
                actor_context="scenario_event",
                player_attribute_specs=_NO_ATTRIBUTES,
            )


class TestObjectStateIntAtLeastLoading:
    """整数 state 条件は state_key と required_quantity を別々に保持する。"""

    def test_loads_state_key_and_required_quantity(
        self, mapper: ScenarioIdMapper
    ) -> None:
        """閾値には required_quantity を使い、reactive の ticks_offset を流用しない。"""
        condition = parse_interaction_condition(
            {
                "condition_type": "OBJECT_STATE_INT_AT_LEAST",
                "target_object": "signal_fire_pit",
                "state_key": "driftwood_stacked",
                "required_quantity": 3,
            },
            mapper,
                player_attribute_specs=_NO_ATTRIBUTES,
        )

        assert condition.state_key == "driftwood_stacked"
        assert condition.required_quantity == 3

    def test_missing_state_key_fails_fast(self, mapper: ScenarioIdMapper) -> None:
        """state_key が無い条件は永久不成立にせず、読み込み時に拒否する。"""
        with pytest.raises(ScenarioLoadError, match="state_key"):
            parse_interaction_condition(
                {
                    "condition_type": "OBJECT_STATE_INT_AT_LEAST",
                    "target_object": "signal_fire_pit",
                    "required_quantity": 3,
                },
                mapper,
                player_attribute_specs=_NO_ATTRIBUTES,
            )
