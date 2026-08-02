"""全員が行動不能になったときの外的停止をシナリオ規則と独立して保証する。"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from tests.runtime_config_helpers import runtime_config


_SCENARIO_PATH = Path("data/scenarios/survival_island_v4_coop.json")
_PERSISTENT_SCENARIO_PATH = Path("data/scenarios/persistent_world_demo.json")


def _down_players(runtime, player_ids: list[PlayerId]) -> None:
    for player_id in player_ids:
        status = runtime._player_status_repo.find_by_id(player_id)
        assert status is not None
        status.apply_damage(9999)
        runtime._player_status_repo.save(status)


class TestWorldRuntimeEndOnAllDown:
    """END_ON_ALL_DOWN が共通の外的停止として働く挙動を固定する。"""

    def test_flag_off_keeps_existing_death_grace_behavior(self) -> None:
        """既定 off では全員 down でも DEAD 猶予を待ち、即終了しない。"""
        runtime = create_world_runtime(_SCENARIO_PATH, config=runtime_config())
        _down_players(runtime, runtime.get_player_ids())

        result = runtime.check_game_end()

        assert result.is_ended is False
        assert result.reason == "ゲーム続行中"

    def test_flag_on_ends_when_every_unresolved_player_is_down(self) -> None:
        """ON なら全員 down の時点で grace_ticks 経過を待たずに終了する。"""
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=runtime_config(end_on_all_down=True),
        )
        _down_players(runtime, runtime.get_player_ids())

        result = runtime.check_game_end()

        assert result.is_ended is True
        assert result.reason.startswith("外的停止 END_ON_ALL_DOWN:")
        assert "行動可能プレイヤーがいない" in result.reason
        assert result.player_outcomes is not None
        assert all(
            outcome is PlayerOutcomeEnum.UNRESOLVED
            for outcome in result.player_outcomes.values()
        )

    def test_flag_on_treats_resolved_players_as_unable_to_act(self) -> None:
        """ON では outcome 確定済み player と down player だけなら終了する。"""
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=runtime_config(end_on_all_down=True),
        )
        player_ids = runtime.get_player_ids()
        runtime._player_outcome_registry.set_outcome(
            player_ids[0],
            PlayerOutcomeEnum.RESCUED,
        )
        _down_players(runtime, player_ids[1:])

        result = runtime.check_game_end()

        assert result.is_ended is True
        assert result.reason.startswith("外的停止 END_ON_ALL_DOWN:")

    def test_flag_on_does_not_end_while_any_unresolved_player_can_act(self) -> None:
        """ON でも未確定かつ down していない player が残るなら終了しない。"""
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=runtime_config(end_on_all_down=True),
        )
        _down_players(runtime, runtime.get_player_ids()[:-1])

        result = runtime.check_game_end()

        assert result.is_ended is False
        assert result.reason == "ゲーム続行中"

    def test_flag_on_also_stops_world_without_outcome_rules(self) -> None:
        """終了規則のない永続世界でも、明示した外的停止は同じ入口で働く。"""
        runtime = create_world_runtime(
            _PERSISTENT_SCENARIO_PATH,
            config=runtime_config(end_on_all_down=True),
        )
        assert runtime.scenario.player_outcome_rules == ()
        assert runtime.scenario.end_conditions == ()
        _down_players(runtime, runtime.get_player_ids())

        result = runtime.check_game_end()

        assert result.is_ended is True
        assert result.reason.startswith("外的停止 END_ON_ALL_DOWN:")

    def test_flag_on_does_not_stop_empty_player_set(self, monkeypatch) -> None:
        """対象者0人を空集合の論理で「全員行動不能」とみなして終了しない。"""
        runtime = create_world_runtime(
            _PERSISTENT_SCENARIO_PATH,
            config=runtime_config(end_on_all_down=True),
        )
        monkeypatch.setattr(runtime, "get_player_ids", lambda: [])

        result = runtime.check_game_end()

        assert result.is_ended is False
        assert result.reason == "ゲーム続行中"
