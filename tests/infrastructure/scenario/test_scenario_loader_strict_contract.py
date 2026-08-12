"""ScenarioLoader がシナリオ作家の誤記を既定値へ縮退させず拒否することを保証する。"""

from __future__ import annotations

from copy import deepcopy
import inspect
import re

import pytest

from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    SUPPORTED_CONDITION_TYPES,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)
from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario


class TestScenarioEventContract:
    """scenario_events の列挙値・通知先・チェーン参照を読込時に検査する。"""

    def test_unknown_condition_type_is_rejected(self) -> None:
        """未知の condition_type は永久に未発火へ縮退せず、イベント位置つきで拒否する。"""
        raw = _minimal_scenario()
        raw["scenario_events"][0]["conditions"][0]["condition_type"] = (
            "TICK_AT_LEATS"
        )

        with pytest.raises(ScenarioLoadError, match="TICK_AT_LEATS"):
            ScenarioLoader().load_from_dict(raw)

    def test_unknown_recipient_is_rejected(self) -> None:
        """未知の recipients は全員通知へ縮退せず、読込時に拒否する。"""
        raw = _minimal_scenario()
        raw["scenario_events"][0]["observation"]["recipients"] = "player_at_spot"

        with pytest.raises(ScenarioLoadError, match="player_at_spot"):
            ScenarioLoader().load_from_dict(raw)

    def test_non_string_recipient_is_rejected_as_scenario_error(self) -> None:
        """recipients が配列でも Python の TypeError を漏らさず読込エラーにする。"""
        raw = _minimal_scenario()
        raw["scenario_events"][0]["observation"]["recipients"] = [
            "players_at_spot"
        ]

        with pytest.raises(ScenarioLoadError, match="recipients"):
            ScenarioLoader().load_from_dict(raw)

    def test_non_string_trigger_is_rejected_as_scenario_error(self) -> None:
        """trigger が配列でも Python の TypeError を漏らさず読込エラーにする。"""
        raw = _minimal_scenario()
        raw["scenario_events"][0]["trigger"] = ["ON_TICK"]

        with pytest.raises(ScenarioLoadError, match="trigger"):
            ScenarioLoader().load_from_dict(raw)

    def test_players_at_spot_requires_target_spot(self) -> None:
        """players_at_spot に target_spot が無ければ全員通知へ縮退せず拒否する。"""
        raw = _minimal_scenario()
        raw["scenario_events"][0]["observation"].pop("target_spot")

        with pytest.raises(ScenarioLoadError, match="target_spot"):
            ScenarioLoader().load_from_dict(raw)

    def test_duplicate_event_id_is_rejected(self) -> None:
        """同じ event id が複数あればチェーン解決先が曖昧になるため拒否する。"""
        raw = _minimal_scenario()
        raw["scenario_events"].append(deepcopy(raw["scenario_events"][0]))

        with pytest.raises(ScenarioLoadError, match="tick_event"):
            ScenarioLoader().load_from_dict(raw)

    def test_unknown_next_event_id_is_rejected(self) -> None:
        """next_event_id の参照先が無ければ実行時に予約が消えるため拒否する。"""
        raw = _minimal_scenario()
        raw["scenario_events"][0]["next_event_id"] = "missing_event"

        with pytest.raises(ScenarioLoadError, match="missing_event"):
            ScenarioLoader().load_from_dict(raw)

    def test_negative_chain_delay_is_rejected(self) -> None:
        """delay_ticks が負なら過去への予約になるため読込時に拒否する。"""
        raw = _minimal_scenario()
        raw["scenario_events"][0]["delay_ticks"] = -1

        with pytest.raises(ScenarioLoadError, match="delay_ticks"):
            ScenarioLoader().load_from_dict(raw)


class TestScenarioReferenceContract:
    """名前で参照したシナリオ要素が実在することを読込時に検査する。"""

    def test_unknown_accessible_object_id_is_rejected(self) -> None:
        """sub_location の存在しない object 参照は一覧から黙って捨てず拒否する。"""
        raw = _minimal_scenario()
        raw["spots"][0]["interior"]["sub_locations"] = [
            {
                "id": "desk_side",
                "name": "机の脇",
                "description": "箱に手が届く。",
                "accessible_object_ids": ["chest", "missing_object"],
            }
        ]

        with pytest.raises(ScenarioLoadError, match="missing_object"):
            ScenarioLoader().load_from_dict(raw)

    def test_object_from_another_interior_is_rejected(self) -> None:
        """別の地点に実在する object も sub_location の操作対象にはできない。"""
        raw = _minimal_scenario()
        raw["spots"][1]["interior"] = {
            "objects": [
                {
                    "id": "remote_box",
                    "name": "遠くの箱",
                    "description": "別室にある。",
                    "object_type": "OTHER",
                    "state": {},
                    "interactions": [],
                }
            ]
        }
        raw["spots"][0]["interior"]["sub_locations"] = [
            {
                "id": "desk_side",
                "name": "机の脇",
                "description": "この部屋だけが見える。",
                "accessible_object_ids": ["remote_box"],
            }
        ]

        with pytest.raises(ScenarioLoadError, match="remote_box"):
            ScenarioLoader().load_from_dict(raw)

    def test_nested_unknown_condition_is_rejected_with_path(self) -> None:
        """合成条件の子にある未知条件も、子の位置を含む読込エラーにする。"""
        raw = _minimal_scenario()
        raw["scenario_events"][0]["conditions"] = [
            {
                "condition_type": "AND",
                "children": [{"condition_type": "FLAG_SETT", "flag_name": "x"}],
            }
        ]

        with pytest.raises(ScenarioLoadError, match=r"children\[0\].*FLAG_SETT"):
            ScenarioLoader().load_from_dict(raw)

    def test_unknown_reactive_binding_condition_is_rejected(self) -> None:
        """reactive_bindings でも共通の条件種別検査が働き、未知条件を拒否する。"""
        raw = _minimal_scenario()
        raw["reactive_bindings"] = {
            "passages": [
                {
                    "target": "a_to_b",
                    "predicate": {"condition_type": "FLAG_SETT"},
                    "on_true_state": "OPEN",
                    "on_false_state": "LOCKED",
                }
            ]
        }

        with pytest.raises(ScenarioLoadError, match=r"predicate.*FLAG_SETT"):
            ScenarioLoader().load_from_dict(raw)

    def test_unknown_player_outcome_condition_is_rejected(self) -> None:
        """player_outcome_rules でも共通の条件種別検査が働き、未知条件を拒否する。"""
        raw = _minimal_scenario()
        raw["player_outcome_rules"] = [
            {
                "id": "ending",
                "trigger": {"condition_type": "TICK_AT_LEATS", "tick": 3},
                "once": True,
                "player_conditions": [],
                "outcome": "RESCUED",
            }
        ]

        with pytest.raises(ScenarioLoadError, match=r"trigger.*TICK_AT_LEATS"):
            ScenarioLoader().load_from_dict(raw)

    @pytest.mark.parametrize(
        "condition",
        [
            {"condition_type": "PROBABILITY"},
            {"condition_type": "PROBABILITY", "probability": "not-a-number"},
            {"condition_type": "NOT", "children": []},
        ],
        ids=["missing-probability", "invalid-probability", "empty-not"],
    )
    def test_invalid_known_condition_uses_scenario_load_error(
        self,
        condition: dict,
    ) -> None:
        """既知条件の値が不正でもドメイン例外等を漏らさず、位置つき読込エラーにする。"""
        raw = _minimal_scenario()
        raw["scenario_events"][0]["conditions"] = [condition]

        with pytest.raises(ScenarioLoadError, match=r"conditions\[0\]"):
            ScenarioLoader().load_from_dict(raw)

    def test_supported_condition_types_match_evaluator_branches(self) -> None:
        """読込可能な全 condition_type に評価分岐があり、静かな未発火の再発を防ぐ。"""
        source = inspect.getsource(ScenarioConditionEvaluator._evaluate)
        evaluated_types = frozenset(re.findall(r'ctype == "([A-Z_]+)"', source))

        assert evaluated_types == SUPPORTED_CONDITION_TYPES


class TestScenarioBooleanContract:
    """JSON 真偽値だけを受理し、文字列や数値の暗黙変換を拒否する。"""

    @pytest.mark.parametrize(
        ("mutate", "path"),
        [
            (
                lambda raw: raw["connections"][0].__setitem__(
                    "is_bidirectional", "false"
                ),
                "is_bidirectional",
            ),
            (
                lambda raw: raw["spots"][0].__setitem__("is_outdoor", "false"),
                "is_outdoor",
            ),
            (
                lambda raw: raw["spots"][0]["interior"]["objects"][0].__setitem__(
                    "is_visible", "false"
                ),
                "is_visible",
            ),
            (
                lambda raw: raw["scenario_events"][0].__setitem__("once", "false"),
                "once",
            ),
            (
                lambda raw: raw["scenario_events"][0]["observation"].__setitem__(
                    "schedules_turn", "false"
                ),
                "schedules_turn",
            ),
            (
                lambda raw: raw["connections"][0]["passage_conditions"][0].__setitem__(
                    "consume_item", "false"
                ),
                "consume_item",
            ),
        ],
        ids=[
            "connection-is-bidirectional",
            "spot-is-outdoor",
            "object-is-visible",
            "event-once",
            "event-schedules-turn",
            "passage-consume-item",
        ],
    )
    def test_non_boolean_value_is_rejected(self, mutate, path: str) -> None:
        """真偽値項目へ文字列を渡すと真扱いせず、項目名つきで拒否する。"""
        raw = _minimal_scenario()
        mutate(raw)

        with pytest.raises(ScenarioLoadError, match=path):
            ScenarioLoader().load_from_dict(raw)

    def test_numeric_boolean_value_is_rejected(self) -> None:
        """真偽値項目へ 0 や 1 を渡しても JSON 真偽値として扱わず拒否する。"""
        raw = _minimal_scenario()
        raw["scenario_events"][0]["once"] = 1

        with pytest.raises(ScenarioLoadError, match="once"):
            ScenarioLoader().load_from_dict(raw)
