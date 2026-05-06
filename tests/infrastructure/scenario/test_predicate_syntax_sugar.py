"""ScenarioLoader の predicate 糖衣記法 (`all_of` / `any_of` / `not_`) のテスト。

合成条件のネストを浅く書ける糖衣を提供する Phase 2 polish。
内部 AST (ScenarioEventCondition) は変更しないため、糖衣は load 時に
`condition_type: AND/OR/NOT + children` 形へ正規化される。

入力 JSON が読み込み後に等価な AST になることを保証する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)


def _scenario_with_event_condition(condition_raw: dict) -> dict:
    """指定 condition を 1 つ持つシナリオの最小骨格。"""
    return {
        "scenario_format_version": "1.0",
        "metadata": {
            "id": "x", "title": "x", "description": "x",
            "theme": "x", "difficulty": "easy", "estimated_ticks": 1,
            "author": "x", "tags": [],
        },
        "item_specs": [],
        "environment": {
            "weather": {
                "enabled": False,
                "initial": {"weather_type": "CLEAR", "intensity": 0.0},
                "update_interval_ticks": 100,
                "announce_changes": False,
            },
        },
        "spots": [{
            "id": "s", "name": "S", "description": "d", "category": "OTHER",
            "atmosphere": {"lighting": "DIM", "temperature": "NORMAL"},
            "interior": {"objects": []},
        }],
        "connections": [],
        "players": [{"id": "p", "name": "P", "spawn_spot": "s", "initial_items": []}],
        "game_end_conditions": {"win": [], "lose": []},
        "scenario_events": [{
            "id": "ev",
            "trigger": "ON_TICK",
            "once": True,
            "conditions": [condition_raw],
            "effects": [],
        }],
    }


def _loaded_root_condition(condition_raw: dict):
    result = ScenarioLoader().load_from_dict(
        _scenario_with_event_condition(condition_raw)
    )
    assert len(result.scenario_events) == 1
    conds = result.scenario_events[0].conditions
    assert len(conds) == 1
    return conds[0]


class TestAllOfShorthand:
    """`all_of` 糖衣記法は内部で AND ノードに正規化される。"""

    def test_all_of_becomes_and_with_children(self) -> None:
        """`{all_of: [c1, c2]}` は condition_type=AND の 2-child ノードになる。"""
        cond = _loaded_root_condition({
            "all_of": [
                {"condition_type": "TICK_AT_LEAST", "tick": 5},
                {"condition_type": "FLAG_SET", "flag_name": "ready"},
            ],
        })
        assert cond.condition_type == "AND"
        assert len(cond.children) == 2
        assert cond.children[0].condition_type == "TICK_AT_LEAST"
        assert cond.children[1].condition_type == "FLAG_SET"

    def test_all_of_can_nest(self) -> None:
        """`all_of` 内に更なる `all_of` / `any_of` を入れて再帰展開できる。"""
        cond = _loaded_root_condition({
            "all_of": [
                {"condition_type": "TICK_AT_LEAST", "tick": 5},
                {"any_of": [
                    {"condition_type": "FLAG_SET", "flag_name": "a"},
                    {"condition_type": "FLAG_SET", "flag_name": "b"},
                ]},
            ],
        })
        assert cond.condition_type == "AND"
        # 2 番目の child は OR に展開されている
        nested = cond.children[1]
        assert nested.condition_type == "OR"
        assert len(nested.children) == 2

    def test_all_of_empty_list_yields_and_with_no_children(self) -> None:
        """空 `all_of` は children=() の AND になる（評価器側で True を返す約束）。"""
        cond = _loaded_root_condition({"all_of": []})
        assert cond.condition_type == "AND"
        assert cond.children == ()


class TestAnyOfShorthand:
    """`any_of` 糖衣記法は内部で OR ノードに正規化される。"""

    def test_any_of_becomes_or(self) -> None:
        """`{any_of: [c1, c2]}` は condition_type=OR の 2-child ノードになる。"""
        cond = _loaded_root_condition({
            "any_of": [
                {"condition_type": "FLAG_SET", "flag_name": "a"},
                {"condition_type": "FLAG_SET", "flag_name": "b"},
            ],
        })
        assert cond.condition_type == "OR"
        assert len(cond.children) == 2


class TestNotShorthand:
    """`not_` 糖衣記法は内部で NOT ノードに正規化される。"""

    def test_not_takes_single_condition(self) -> None:
        """`{not_: c}` は condition_type=NOT の 1-child ノードになる。"""
        cond = _loaded_root_condition({
            "not_": {"condition_type": "FLAG_SET", "flag_name": "x"},
        })
        assert cond.condition_type == "NOT"
        assert len(cond.children) == 1
        assert cond.children[0].condition_type == "FLAG_SET"

    def test_not_rejects_list_payload(self) -> None:
        """`not_` に list を渡すのは作家ミスとして拒否（NOT は単項）。"""
        with pytest.raises(ScenarioLoadError, match="not_"):
            ScenarioLoader().load_from_dict(_scenario_with_event_condition({
                "not_": [{"condition_type": "FLAG_SET", "flag_name": "x"}],
            }))


class TestShorthandValidation:
    """糖衣記法の組合せに関するバリデーション。"""

    def test_multiple_shortcuts_rejected(self) -> None:
        """同じノードに `all_of` と `any_of` を併記するのは拒否。"""
        with pytest.raises(ScenarioLoadError, match="multiple composite shortcuts"):
            ScenarioLoader().load_from_dict(_scenario_with_event_condition({
                "all_of": [{"condition_type": "FLAG_SET", "flag_name": "a"}],
                "any_of": [{"condition_type": "FLAG_SET", "flag_name": "b"}],
            }))

    def test_shortcut_mixed_with_condition_type_rejected(self) -> None:
        """`condition_type` と糖衣記法の併記は拒否（曖昧さを排除）。"""
        with pytest.raises(ScenarioLoadError, match="cannot mix"):
            ScenarioLoader().load_from_dict(_scenario_with_event_condition({
                "condition_type": "AND",
                "all_of": [{"condition_type": "FLAG_SET", "flag_name": "a"}],
            }))

    def test_all_of_non_list_rejected(self) -> None:
        """`all_of` の値は list でないと拒否する。"""
        with pytest.raises(ScenarioLoadError, match="all_of must be a list"):
            ScenarioLoader().load_from_dict(_scenario_with_event_condition({
                "all_of": {"condition_type": "FLAG_SET", "flag_name": "a"},  # dict は不可
            }))


class TestEquivalenceWithVerboseForm:
    """糖衣 ↔ 旧記法が AST レベルで同値であることを保証する。"""

    def test_all_of_equivalent_to_explicit_and(self) -> None:
        """`all_of` 版と explicit AND 版で children 構造が一致する。"""
        explicit = _loaded_root_condition({
            "condition_type": "AND",
            "children": [
                {"condition_type": "TICK_AT_LEAST", "tick": 5},
                {"condition_type": "FLAG_SET", "flag_name": "ready"},
            ],
        })
        sugary = _loaded_root_condition({
            "all_of": [
                {"condition_type": "TICK_AT_LEAST", "tick": 5},
                {"condition_type": "FLAG_SET", "flag_name": "ready"},
            ],
        })
        assert explicit.condition_type == sugary.condition_type
        assert len(explicit.children) == len(sugary.children)
        for a, b in zip(explicit.children, sugary.children):
            assert a.condition_type == b.condition_type
            assert a.tick == b.tick
            assert a.flag_name == b.flag_name
