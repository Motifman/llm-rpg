"""scenario event が世界フェーズと場所ごとの人数を条件にできる契約。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)


_TARGET_SPOT = SpotId.create(10)
_OTHER_SPOT = SpotId.create(20)
_DRILL = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "scenarios"
    / "station_drill.json"
)


def _graph() -> SpotGraphAggregate:
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    for spot_id, name in ((_TARGET_SPOT, "対象地"), (_OTHER_SPOT, "別の場所")):
        graph.add_spot(
            SpotNode(
                spot_id=spot_id,
                name=name,
                description=name,
                category=SpotCategoryEnum.OTHER,
                parent_id=None,
            )
        )
    graph.place_entity(EntityId.create(1), _TARGET_SPOT)
    graph.place_entity(EntityId.create(2), _TARGET_SPOT)
    graph.place_entity(EntityId.create(3), _OTHER_SPOT)
    graph.place_entity(EntityId.create(99), _TARGET_SPOT)
    return graph


def _graph_with_one_entity_at_target() -> SpotGraphAggregate:
    graph = _graph()
    graph.teleport_entity(EntityId.create(2), _OTHER_SPOT)
    graph.teleport_entity(EntityId.create(99), _OTHER_SPOT)
    return graph


def _graph_with_two_entities_at_target() -> SpotGraphAggregate:
    graph = _graph()
    graph.teleport_entity(EntityId.create(99), _OTHER_SPOT)
    return graph


def _evaluator(
    *,
    phase: GamePhase | None = GamePhase.FREE_ROAM,
) -> ScenarioConditionEvaluator:
    return ScenarioConditionEvaluator(
        world_flag_state=MutableWorldFlagState(),
        spot_interior_repository=MagicMock(),
        player_status_repository=MagicMock(),
        player_inventory_repository=MagicMock(),
        item_repository=MagicMock(),
        game_phase_provider=(lambda: phase) if phase is not None else None,
    )


class TestGamePhaseIs:
    """`GAME_PHASE_IS` は現在の世界フェーズとの一致だけを見る。"""

    def test_matching_phase_is_true(self) -> None:
        """現在が会議中なら `MEETING` 条件は成立する。"""
        condition = ScenarioEventCondition(
            condition_type="GAME_PHASE_IS",
            game_phase="MEETING",
        )

        assert _evaluator(phase=GamePhase.MEETING).evaluate(
            condition,
            WorldTick(0),
            _graph(),
        ) is True

    def test_different_phase_is_false(self) -> None:
        """自由時間では `MEETING` 条件は成立しない。"""
        condition = ScenarioEventCondition(
            condition_type="GAME_PHASE_IS",
            game_phase="MEETING",
        )

        assert _evaluator(phase=GamePhase.FREE_ROAM).evaluate(
            condition,
            WorldTick(0),
            _graph(),
        ) is False

    def test_missing_provider_is_not_a_silent_false(self) -> None:
        """フェーズの配線が無ければ、未成立へ黙って縮退せず失敗する。"""
        condition = ScenarioEventCondition(
            condition_type="GAME_PHASE_IS",
            game_phase="MEETING",
        )

        with pytest.raises(RuntimeError, match="game_phase_provider"):
            _evaluator(phase=None).evaluate(condition, WorldTick(0), _graph())


class TestPlayersAtSpot:
    """`PLAYERS_AT_SPOT` は graph が持つ在席数を閾値と比べる。"""

    def test_required_count_or_more_is_true(self) -> None:
        """対象地に3 entityいれば必要人数3人の条件は成立する。"""
        condition = ScenarioEventCondition(
            condition_type="PLAYERS_AT_SPOT",
            spot_id=_TARGET_SPOT.value,
            required_player_count=3,
        )

        assert _evaluator().evaluate(condition, WorldTick(0), _graph()) is True

    def test_fewer_than_required_count_is_false(self) -> None:
        """対象地に3 entityしかいなければ必要人数4人の条件は成立しない。"""
        condition = ScenarioEventCondition(
            condition_type="PLAYERS_AT_SPOT",
            spot_id=_TARGET_SPOT.value,
            required_player_count=4,
        )

        assert _evaluator().evaluate(condition, WorldTick(0), _graph()) is False

    def test_omitted_required_count_defaults_to_two(self) -> None:
        """必要人数を省略すると1人では不成立となり、既定の2人を要求する。"""
        condition = ScenarioEventCondition(
            condition_type="PLAYERS_AT_SPOT",
            spot_id=_TARGET_SPOT.value,
        )

        assert _evaluator().evaluate(
            condition,
            WorldTick(0),
            _graph_with_one_entity_at_target(),
        ) is False

    def test_omitted_required_count_accepts_two_entities(self) -> None:
        """必要人数を省略すると2人で成立し、3人以上を要求しない。"""
        condition = ScenarioEventCondition(
            condition_type="PLAYERS_AT_SPOT",
            spot_id=_TARGET_SPOT.value,
        )

        assert _evaluator().evaluate(
            condition,
            WorldTick(0),
            _graph_with_two_entities_at_target(),
        ) is True

    def test_player_scoped_entry_keeps_world_entity_count(self) -> None:
        """対象者入口でもPLAYERS_AT_SPOTは本人に狭めず、対象地の全entityを数える。"""
        condition = ScenarioEventCondition(
            condition_type="PLAYERS_AT_SPOT",
            spot_id=_TARGET_SPOT.value,
            required_player_count=3,
        )

        assert _evaluator().evaluate_for_player(
            condition,
            WorldTick(0),
            _graph(),
            target_player_id=PlayerId(3),
        ) is True


def _load_condition(tmp_path: Path, condition: dict) -> ScenarioEventCondition:
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    raw.setdefault("scenario_events", []).append(
        {
            "id": "world_context_probe",
            "trigger": "ON_TICK",
            "once": True,
            "conditions": [condition],
            "effects": [
                {
                    "effect_type": "SET_FLAG",
                    "parameters": {"flag_name": "probe_fired"},
                }
            ],
        }
    )
    path = tmp_path / "world_context_probe.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    loaded = ScenarioLoader().load_from_file(path)
    return loaded.scenario_events[-1].conditions[0]


class TestWorldContextConditionLoading:
    """世界文脈条件の文字列IDと必須値を読み込み時に検証する。"""

    def test_game_phase_is_loads_a_known_phase(self, tmp_path) -> None:
        """既知のフェーズ名は評価用の値へそのまま運ぶ。"""
        condition = _load_condition(
            tmp_path,
            {"condition_type": "GAME_PHASE_IS", "game_phase": "MEETING"},
        )

        assert condition.game_phase == "MEETING"

    @pytest.mark.parametrize("game_phase", [None, "DISCUSSION"])
    def test_game_phase_is_rejects_missing_or_unknown_phase(
        self,
        tmp_path,
        game_phase,
    ) -> None:
        """フェーズの欠落や未知名は、永久に偽の条件として受理しない。"""
        raw = {"condition_type": "GAME_PHASE_IS"}
        if game_phase is not None:
            raw["game_phase"] = game_phase

        with pytest.raises(ScenarioLoadError, match="game_phase"):
            _load_condition(tmp_path, raw)

    def test_players_at_spot_resolves_the_spot_and_count(self, tmp_path) -> None:
        """場所名と必要人数を、評価器が使う数値へ解決する。"""
        condition = _load_condition(
            tmp_path,
            {
                "condition_type": "PLAYERS_AT_SPOT",
                "target_spot": "hall",
                "required_player_count": 2,
            },
        )

        assert condition.spot_id is not None
        assert condition.required_player_count == 2

    @pytest.mark.parametrize("payload", [
        {"required_player_count": 2},
        {"target_spot": "hall", "required_player_count": 0},
        {"target_spot": "hall", "required_player_count": True},
    ])
    def test_player_count_rejects_missing_or_invalid_values(
        self,
        tmp_path,
        payload,
    ) -> None:
        """場所の欠落と明示した非正数を、常に偽の条件として通さない。"""
        with pytest.raises(ScenarioLoadError):
            _load_condition(
                tmp_path,
                {"condition_type": "PLAYERS_AT_SPOT", **payload},
            )

    def test_players_at_spot_leaves_omitted_count_for_the_shared_rule(
        self,
        tmp_path,
    ) -> None:
        """省略値をloaderで補わず、両経路共通の人数規則へ委ねる。"""
        condition = _load_condition(
            tmp_path,
            {"condition_type": "PLAYERS_AT_SPOT", "target_spot": "hall"},
        )

        assert condition.required_player_count is None
