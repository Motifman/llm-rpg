"""手番の中で立ったフラグによる個人結果が、その tick のうちに、そのときの位置で決まることを保証する (#1618)。

`var/runs/mine_v1_007_memo` では、T36 の手番でゲンが昇降機を動かし、移動中だった
サヨが T37 の移動の段で乗り場に着いてから判定され、脱出になった。籠が上がった
時点で乗り場にいなかった人は、あとから着いても取り残される。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEvent, TraceEventKind
from ai_rpg_world.application.world_graph.world_flag_state import (
    WorldFlagMutationContext,
    WorldFlagMutationSource,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from tests.runtime_config_helpers import runtime_config

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"
_MINE = _SCENARIOS / "mine_village_v1.json"


def _ids(runtime) -> dict[str, PlayerId]:
    return {runtime.get_player_name(pid): pid for pid in runtime.get_player_ids()}


def _place(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity_id = EntityId.create(int(player_id))
    graph.unplace_entity(entity_id)
    graph.place_entity(entity_id, SpotId.create(runtime.id_mapper.get_int("spot", spot)))
    runtime._spot_graph_repo.save(graph)


def _spot_of(runtime, player_id: PlayerId) -> str:
    graph = runtime._spot_graph_repo.find_graph()
    spot_id = graph.get_entity_spot(EntityId.create(int(player_id)))
    return runtime.id_mapper.get_str("spot", int(spot_id.value))


def _outcomes(runtime) -> dict[str, PlayerOutcomeEnum]:
    registry = runtime._player_outcome_registry
    return {name: registry.get_outcome(pid) for name, pid in _ids(runtime).items()}


class _DepartLiftInTurn:
    """最初の手番で、ゲンの操作として `lift_departed` を立てる llm_turn_trigger の代わり。"""

    def __init__(self, runtime, actor: PlayerId) -> None:
        self._runtime = runtime
        self._actor = actor
        self.departed_at: int | None = None

    def schedule_turn(self, player_id: PlayerId) -> None:
        pass

    def run_scheduled_turns(self) -> None:
        if self.departed_at is not None:
            return
        self._runtime._world_flag_state.add(
            "lift_departed",
            context=WorldFlagMutationContext(
                source=WorldFlagMutationSource.SPOT_INTERACTION,
                actor_player_id=self._actor,
            ),
        )
        self.departed_at = self._runtime._time_provider.get_current_tick().value


def _mine_with_sayo_walking_to_the_landing():
    """ゲン・ミオ・サヨが籠に乗り込み、サヨだけが乗り場を離れて、着くまで 2 tick かかる古い支柱の通路から乗り場へ歩き出した世界。"""
    runtime = create_world_runtime(_MINE, config=runtime_config())
    ids = _ids(runtime)
    for name in ("ゲン", "ミオ", "サヨ"):
        _place(runtime, ids[name], "lift_landing")
        runtime.do_interact(ids[name], "lift", "board_lift")
    _place(runtime, ids["サヨ"], "timber_passage")
    runtime.do_move(ids["サヨ"], "lift_landing")
    trigger = _DepartLiftInTurn(runtime, ids["ゲン"])
    runtime.set_simulation_llm_turn_trigger(trigger)
    return runtime, ids, trigger


class TestLiftDepartureInTurnIsJudgedInTheSameTick:
    """廃坑の山村で、手番の中で昇降機が出た tick のうちに、全員の結果が決まることを保証する。"""

    def test_outcomes_are_resolved_in_the_tick_the_lift_departed(self) -> None:
        """手番の中で `lift_departed` が立った tick を終えた時点で、4 人全員の結果が決まり、ゲームが終わる。"""
        runtime, _, trigger = _mine_with_sayo_walking_to_the_landing()

        tick = runtime.advance_tick()

        assert trigger.departed_at == tick
        assert PlayerOutcomeEnum.UNRESOLVED not in _outcomes(runtime).values()
        assert runtime.check_game_end().is_ended is True

    def test_rider_walking_to_the_landing_is_left_behind(self) -> None:
        """籠が上がった tick に乗り場へ移動中だったサヨは、籠の中の場所を持っていても、次の tick に着いても取り残される。"""
        runtime, ids, _ = _mine_with_sayo_walking_to_the_landing()

        runtime.advance_tick()
        position_at_departure = _spot_of(runtime, ids["サヨ"])
        runtime.advance_tick()

        assert position_at_departure != "lift_landing"
        assert _spot_of(runtime, ids["サヨ"]) == "lift_landing"
        assert _outcomes(runtime)["サヨ"] is PlayerOutcomeEnum.STRANDED

    def test_riders_at_the_landing_escape(self) -> None:
        """籠が上がった tick に乗り場にいて籠の中の場所を持つゲンとミオは脱出し、乗り込んでいないハルは取り残される。"""
        runtime, _, _ = _mine_with_sayo_walking_to_the_landing()

        runtime.advance_tick()

        outcomes = _outcomes(runtime)
        assert outcomes["ゲン"] is PlayerOutcomeEnum.RESCUED
        assert outcomes["ミオ"] is PlayerOutcomeEnum.RESCUED
        assert outcomes["ハル"] is PlayerOutcomeEnum.STRANDED

    def test_each_outcome_is_announced_once(self) -> None:
        """1 tick に 2 回判定しても、籠が上がった tick とその次の tick を通して、結果の知らせは 1 人につき 1 回だけ出る。"""
        runtime, ids, _ = _mine_with_sayo_walking_to_the_landing()
        announced: list[int] = []
        runtime._player_outcome_registry.register_callback(
            lambda player_id, old, new: announced.append(int(player_id))
        )

        runtime.advance_tick()
        runtime.advance_tick()

        assert sorted(announced) == sorted(int(pid) for pid in ids.values())


class _CollectingRecorder(NullTraceRecorder):
    """NullTraceRecorder の採番を使いながら記録した event を保持する。"""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[TraceEvent] = []

    def record(
        self,
        kind: str,
        *,
        tick: int | None = None,
        player_id: int | None = None,
        **payload: Any,
    ) -> TraceEvent:
        event = super().record(kind, tick=tick, player_id=player_id, **payload)
        self.events.append(event)
        return event


class TestOutcomeJudgementTraceTellsWhenItWasJudged:
    """個人結果の規則の評価の trace が、世界の段の判定か手番のあとの判定かを区別できることを保証する。"""

    def test_departure_tick_trace_shows_the_rule_fired_after_turns(self) -> None:
        """昇降機が手番で出た tick に、世界の段の判定では発火せず、手番のあとの判定で発火したことが evaluation_point で分かる。"""
        runtime, _, _ = _mine_with_sayo_walking_to_the_landing()
        recorder = _CollectingRecorder()
        runtime.set_trace_recorder(recorder)

        runtime.advance_tick()

        triggers = [
            (event.payload["evaluation_point"], event.payload["is_satisfied"])
            for event in recorder.events
            if event.kind == TraceEventKind.SCENARIO_PREDICATE_EVALUATED
            and event.payload["purpose"] == "player_outcome_trigger"
            and event.payload["owner_id"] == "escape_by_lift"
        ]
        assert triggers == [("world_stage", False), ("after_turns", True)]


class _RecordOutcomeAtTurn:
    """手番が回った時点の、1 人の個人結果を記録する llm_turn_trigger の代わり。"""

    def __init__(self, runtime, player_id: PlayerId) -> None:
        self._runtime = runtime
        self._player_id = player_id
        self.seen: dict[int, PlayerOutcomeEnum] = {}

    def schedule_turn(self, player_id: PlayerId) -> None:
        pass

    def run_scheduled_turns(self) -> None:
        tick = self._runtime._time_provider.get_current_tick().value
        self.seen[tick] = self._runtime._player_outcome_registry.get_outcome(self._player_id)


@pytest.mark.parametrize(
    ("scenario", "rescue_tick"),
    [
        ("survival_island_v2.json", 192),
        ("survival_island_v3_coop.json", 144),
        ("survival_island_v4_coop.json", 144),
    ],
)
class TestIslandRescueOnArrivalTick:
    """島のシナリオで、移動で山頂に着いた tick に、手番より前に救助されることを保証する。"""

    def test_player_arriving_at_the_summit_on_the_rescue_tick_is_rescued_before_turns(
        self, scenario: str, rescue_tick: int
    ) -> None:
        """狼煙が上がっていて、救助の tick に移動で山頂に着いた人は、その tick の手番が回る前に RESCUED になる。"""
        runtime = create_world_runtime(_SCENARIOS / scenario, config=runtime_config())
        player_id = runtime.get_player_ids()[0]
        _place(runtime, player_id, "mountain_path")
        runtime._world_flag_state.add(
            "signal_fire_lit",
            context=WorldFlagMutationContext(
                source=WorldFlagMutationSource.SCENARIO_EVENT,
                actor_player_id=None,
            ),
        )
        trigger = _RecordOutcomeAtTurn(runtime, player_id)
        runtime.set_simulation_llm_turn_trigger(trigger)
        runtime._time_provider.set_current_tick(rescue_tick - 2)
        runtime.do_move(player_id, "summit")

        runtime.advance_tick()
        position_before = _spot_of(runtime, player_id)
        runtime.advance_tick()

        assert position_before != "summit"
        assert _spot_of(runtime, player_id) == "summit"
        assert trigger.seen[rescue_tick] is PlayerOutcomeEnum.RESCUED
