"""生死に関する四つの問いが、同じ query を通して現行挙動を保つことを保証する。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    PlayerInteractedWithPlayerEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring


_ROOT = Path(__file__).resolve().parents[2]
_STATION_DRILL = _ROOT / "data" / "scenarios" / "station_drill.json"
_RELAY_PUZZLE = _ROOT / "data" / "scenarios" / "relay_puzzle_demo.json"
_MORI = PlayerId(1)
_SENA = PlayerId(2)


def _set_life_state(runtime, state: str) -> None:
    if state in {"downed", "dead"}:
        status = runtime._player_status_repo.find_by_id(_SENA)
        status.apply_damage(status.hp.value)
        runtime._player_status_repo.save(status)
    if state == "dead":
        runtime._player_outcome_registry.set_outcome(
            _SENA, PlayerOutcomeEnum.DEAD
        )
    if state == "ejected":
        assert runtime.eject_player(_SENA) is True
    if state == "rescued":
        runtime._player_outcome_registry.set_outcome(
            _SENA, PlayerOutcomeEnum.RESCUED
        )
    if state == "stranded":
        runtime._player_outcome_registry.set_outcome(
            _SENA, PlayerOutcomeEnum.STRANDED
        )


def _is_placed(runtime, player_id: PlayerId) -> bool:
    graph = runtime._spot_graph_repo.find_graph()
    try:
        graph.get_entity_spot(EntityId.create(int(player_id)))
    except Exception:
        return False
    return True


def _can_take_llm_turn(runtime, player_id: PlayerId) -> bool:
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=StubLlmClient(None),
    )
    return wiring.llm_turn_trigger._can_player_act(int(player_id))


def _passes_observation_gate(runtime, player_id: PlayerId) -> bool:
    event_about_someone_else = MagicMock(
        aggregate_id=MagicMock(value=int(_MORI)),
        aggregate_type="PlayerStatusAggregate",
    )
    resolver = runtime._obs_pipeline._resolver
    return resolver._without_the_fallen(
        event_about_someone_else, [player_id]
    ) == [player_id]


@pytest.mark.parametrize(
    (
        "state",
        "expected_outcome",
        "expected_is_down",
        "expected_turn",
        "expected_observation",
        "expected_placed",
        "expected_vote",
        "expected_body",
        "expected_report_error_code",
    ),
    (
        (
            "active",
            PlayerOutcomeEnum.UNRESOLVED,
            False,
            True,
            True,
            True,
            True,
            False,
            "TARGET_NOT_INCAPACITATED",
        ),
        (
            "downed",
            PlayerOutcomeEnum.UNRESOLVED,
            True,
            False,
            False,
            True,
            False,
            True,
            None,
        ),
        (
            "dead",
            PlayerOutcomeEnum.DEAD,
            True,
            False,
            False,
            True,
            False,
            True,
            None,
        ),
        (
            "ejected",
            PlayerOutcomeEnum.EJECTED,
            False,
            False,
            True,
            False,
            False,
            False,
            "TARGET_NOT_FOUND",
        ),
        (
            "rescued",
            PlayerOutcomeEnum.RESCUED,
            False,
            False,
            True,
            True,
            True,
            False,
            "TARGET_NOT_INCAPACITATED",
        ),
        (
            "stranded",
            PlayerOutcomeEnum.STRANDED,
            False,
            False,
            True,
            True,
            True,
            False,
            "TARGET_NOT_INCAPACITATED",
        ),
    ),
)
def test_station_drill_preserves_the_four_life_state_answers(
    state: str,
    expected_outcome: PlayerOutcomeEnum,
    expected_is_down: bool,
    expected_turn: bool,
    expected_observation: bool,
    expected_placed: bool,
    expected_vote: bool,
    expected_body: bool,
    expected_report_error_code: str | None,
) -> None:
    """六つの outcome 状態で、手番・観測・投票・身体の答えを変えない。"""
    runtime = create_world_runtime(_STATION_DRILL)
    _set_life_state(runtime, state)

    status = runtime._player_status_repo.find_by_id(_SENA)
    assert runtime._player_outcome_registry.get_outcome(_SENA) is expected_outcome
    assert status.is_down is expected_is_down
    assert runtime._player_life_query.can_take_turn(_SENA) is expected_turn
    assert (
        runtime._player_life_query.can_receive_world_observation(_SENA)
        is expected_observation
    )
    assert runtime._player_life_query.can_vote(_SENA) is expected_vote
    assert (
        runtime._player_life_query.has_reportable_body(_SENA) is expected_body
    )
    assert _can_take_llm_turn(runtime, _SENA) is expected_turn
    assert _passes_observation_gate(runtime, _SENA) is expected_observation
    assert _is_placed(runtime, _SENA) is expected_placed
    assert (_SENA in runtime.eligible_voters()) is expected_vote

    report = runtime.report_body(_MORI, _SENA)
    assert report.success is expected_body
    assert report.error_code == expected_report_error_code


class TestEveryGateUsesTheSharedQuery:
    """query 自体だけでなく、公開入口から共有 query へ到達することを保証する。"""

    def test_llm_turn_gate_uses_can_take_turn(self) -> None:
        """活動中でも query が不可と答えれば LLM 手番を回さない。"""
        runtime = create_world_runtime(_STATION_DRILL)
        runtime._player_life_query.can_take_turn = MagicMock(return_value=False)

        assert _can_take_llm_turn(runtime, _SENA) is False
        runtime._player_life_query.can_take_turn.assert_called_once_with(_SENA)

    def test_observation_exit_uses_can_receive_world_observation(self) -> None:
        """活動中でも query が不可と答えれば他者の観測から除外する。"""
        runtime = create_world_runtime(_STATION_DRILL)
        runtime._player_life_query.can_receive_world_observation = MagicMock(
            return_value=False
        )

        assert _passes_observation_gate(runtime, _SENA) is False
        runtime._player_life_query.can_receive_world_observation.assert_called_once_with(
            _SENA
        )

    def test_body_report_uses_has_reportable_body(self) -> None:
        """立っている相手でも query が身体ありと答えれば通報入口を通る。"""
        runtime = create_world_runtime(_STATION_DRILL)
        runtime._player_life_query.has_reportable_body = MagicMock(return_value=True)

        assert runtime.report_body(_MORI, _SENA).success is True
        assert runtime._player_life_query.has_reportable_body.call_args_list[0].args == (
            _SENA,
        )

    def test_voter_selection_uses_can_vote(self) -> None:
        """活動中でも query が不可と答えれば投票母数から外す。"""
        runtime = create_world_runtime(_STATION_DRILL)
        original = runtime._player_life_query.can_vote
        runtime._player_life_query.can_vote = MagicMock(
            side_effect=lambda player_id: (
                False if player_id == _SENA else original(player_id)
            )
        )

        assert _SENA not in runtime.eligible_voters()
        runtime._player_life_query.can_vote.assert_any_call(_SENA)

    def test_player_interaction_records_the_querys_body_answer(
        self, tmp_path: Path
    ) -> None:
        """対人行為も status を再導出せず、query の身体判定を event に載せる。"""
        raw = json.loads(_RELAY_PUZZLE.read_text(encoding="utf-8"))
        raw["player_interactions"] = [
            {
                "action_name": "inspect_player",
                "display_label": "様子を見る",
                "preconditions": [{"condition_type": "ALWAYS"}],
                "effects": [
                    {
                        "effect_type": "APPLY_DAMAGE",
                        "target": "TARGET_PLAYER",
                        "parameters": {"damage": 1},
                    }
                ],
            }
        ]
        scenario = tmp_path / "life_query_player_interaction.json"
        scenario.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        runtime = create_world_runtime(scenario)
        graph = runtime._spot_graph_repo.find_graph()
        actor_spot = graph.get_entity_spot(EntityId.create(int(_MORI)))
        graph.unplace_entity(EntityId.create(int(_SENA)))
        graph.place_entity(EntityId.create(int(_SENA)), actor_spot)
        runtime._spot_graph_repo.save(graph)
        runtime._player_life_query.has_reportable_body = MagicMock(return_value=True)
        seen = []
        original = runtime._speech_event_publisher.publish_all

        def spy(events):
            seen.extend(events)
            return original(events)

        runtime._speech_event_publisher.publish_all = spy

        runtime.do_interact_with_player(_MORI, _SENA, "inspect_player")

        interaction = next(
            event
            for event in seen
            if isinstance(event, PlayerInteractedWithPlayerEvent)
        )
        assert interaction.target_was_down is True
        runtime._player_life_query.has_reportable_body.assert_called_once_with(_SENA)
