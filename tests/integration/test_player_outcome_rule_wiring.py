"""シナリオ宣言から公開 tick 入口まで個人結果規則が配線されることを保証する。"""

import json
from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from tests.runtime_config_helpers import runtime_config


_SOURCE = Path("data/scenarios/survival_island_v4_coop.json")


def _declared_scenario(tmp_path: Path) -> Path:
    raw = json.loads(_SOURCE.read_text(encoding="utf-8"))
    raw["player_outcome_rules"] = [
        {
            "id": "rescue_ship_144",
            "trigger": {"condition_type": "TICK_AT_LEAST", "tick": 144},
            "once": True,
            "player_conditions": [
                {"condition_type": "FLAG_SET", "flag_name": "signal_fire_lit"},
                {"condition_type": "PLAYER_AT_SPOT", "target_spot": "summit"},
            ],
            "outcome": "RESCUED",
        }
    ]
    raw["game_end_conditions"]["end"] = [
        {"type": "ALL_PLAYER_OUTCOMES_RESOLVED"}
    ]
    raw["needs"] = {"starvation_damage_per_tick": 2}
    path = tmp_path / "declared_outcome.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


class TestPlayerOutcomeRuleWiring:
    """ローダーの規則を同じ条件評価器・進捗ストアで実行する。"""

    def test_declared_rule_resolves_player_through_runtime_tick(
        self, tmp_path: Path
    ) -> None:
        """宣言した救助規則は create_world_runtime と advance_tick を通して発火する。"""
        runtime = create_world_runtime(
            _declared_scenario(tmp_path),
            config=runtime_config(),
        )
        player_id = runtime.get_player_ids()[0]
        graph = runtime._spot_graph_repo.find_graph()
        entity_id = EntityId.create(int(player_id))
        graph.unplace_entity(entity_id)
        graph.place_entity(
            entity_id,
            SpotId.create(runtime.id_mapper.get_int("spot", "summit")),
        )
        runtime._spot_graph_repo.save(graph)
        runtime._world_flag_state.add("signal_fire_lit")
        runtime._time_provider.set_current_tick(143)

        runtime.advance_tick()

        assert (
            runtime._player_outcome_registry.get_outcome(player_id)
            is PlayerOutcomeEnum.RESCUED
        )
        assert runtime._scenario_event_progress.is_fired(
            "player_outcome_rule:rescue_ship_144"
        )

    def test_neutral_end_returns_mixed_player_outcomes(self, tmp_path: Path) -> None:
        """全員確定時は混在した個人結果を保ち、集団 WIN/LOSE なしで終了する。"""
        runtime = create_world_runtime(
            _declared_scenario(tmp_path),
            config=runtime_config(),
        )
        expected: dict[int, PlayerOutcomeEnum] = {}
        for index, player_id in enumerate(runtime.get_player_ids()):
            outcome = (
                PlayerOutcomeEnum.RESCUED
                if index % 2 == 0
                else PlayerOutcomeEnum.STRANDED
            )
            runtime._player_outcome_registry.set_outcome(player_id, outcome)
            expected[int(player_id)] = outcome

        result = runtime.check_game_end()

        assert result.is_ended is True
        assert result.result is None
        assert result.player_outcomes == expected

    def test_needs_config_reaches_decay_stage(self, tmp_path: Path) -> None:
        """needs の飢餓ダメージ値は結果規則を経由せず needs 段階へ届く。"""
        runtime = create_world_runtime(
            _declared_scenario(tmp_path),
            config=runtime_config(),
        )

        assert (
            runtime._simulation_service._needs_decay_stage
            ._starvation_damage_per_tick
            == 2
        )
