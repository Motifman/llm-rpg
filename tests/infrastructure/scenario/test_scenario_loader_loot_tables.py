"""loot_tables block のパース検証 (PR #1 動的 loot)。

scenario JSON に loot_tables を宣言すると ScenarioLootTableDefinition の
タプルとして読み込まれ、effect parameter の "loot_table" 文字列 ID も
正しく numeric loot_table_id に正規化される。
"""

from __future__ import annotations

import copy

import pytest

from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)


def _scenario_with_loot_tables(loot_tables: list) -> dict:
    from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario
    scenario = copy.deepcopy(_minimal_scenario())
    scenario["loot_tables"] = loot_tables
    return scenario


class TestLootTableParsing:
    """loot_tables block の基本パース挙動。"""

    def test_未指定なら_loot_tables_は_空(self) -> None:
        from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario
        r = ScenarioLoader().load_from_dict(_minimal_scenario())
        assert r.loot_tables == ()

    def test_単一_table_の_パース(self) -> None:
        r = ScenarioLoader().load_from_dict(_scenario_with_loot_tables([
            {
                "id": "test_loot",
                "name": "テスト loot",
                "entries": [
                    {"item_spec": "key", "weight": 50, "min_quantity": 1, "max_quantity": 2},
                ],
            },
        ]))
        assert len(r.loot_tables) == 1
        lt = r.loot_tables[0]
        assert lt.string_id == "test_loot"
        assert lt.name == "テスト loot"
        assert len(lt.entries) == 1
        assert lt.entries[0].weight == 50
        assert lt.entries[0].min_quantity == 1
        assert lt.entries[0].max_quantity == 2

    def test_複数_table_の_パース(self) -> None:
        r = ScenarioLoader().load_from_dict(_scenario_with_loot_tables([
            {"id": "t1", "entries": [{"item_spec": "key", "weight": 1}]},
            {"id": "t2", "entries": [{"item_spec": "key", "weight": 1}]},
        ]))
        assert len(r.loot_tables) == 2
        ids = {lt.string_id for lt in r.loot_tables}
        assert ids == {"t1", "t2"}

    def test_min_max_quantity_の_default_は_1(self) -> None:
        r = ScenarioLoader().load_from_dict(_scenario_with_loot_tables([
            {"id": "t1", "entries": [{"item_spec": "key", "weight": 1}]},
        ]))
        entry = r.loot_tables[0].entries[0]
        assert entry.min_quantity == 1
        assert entry.max_quantity == 1


class TestValidation:
    """loot_tables の不正値を boundary で弾く。"""

    def test_id_欠落で_ScenarioLoadError(self) -> None:
        with pytest.raises(ScenarioLoadError, match="loot_tables.*id is required"):
            ScenarioLoader().load_from_dict(_scenario_with_loot_tables([
                {"entries": [{"item_spec": "key", "weight": 1}]},
            ]))

    def test_entries_空で_ScenarioLoadError(self) -> None:
        with pytest.raises(ScenarioLoadError, match="entries must be non-empty"):
            ScenarioLoader().load_from_dict(_scenario_with_loot_tables([
                {"id": "t1", "entries": []},
            ]))

    def test_item_spec_欠落で_ScenarioLoadError(self) -> None:
        with pytest.raises(ScenarioLoadError, match="item_spec required"):
            ScenarioLoader().load_from_dict(_scenario_with_loot_tables([
                {"id": "t1", "entries": [{"weight": 1}]},
            ]))
