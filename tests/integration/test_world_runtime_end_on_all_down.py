"""全員が行動不能になったときの outcome モード終了判定を保証する。"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from tests.runtime_config_helpers import runtime_config


_SCENARIO_PATH = Path("data/scenarios/survival_island_v4_coop.json")


def _down_players(runtime, player_ids: list[PlayerId]) -> None:
    for player_id in player_ids:
        status = runtime._player_status_repo.find_by_id(player_id)
        assert status is not None
        status.apply_damage(9999)
        runtime._player_status_repo.save(status)


class TestWorldRuntimeEndOnAllDown:
    """END_ON_ALL_DOWN が outcome 未確定の全員 down を即終了へ畳む挙動を固定する。"""

    def test_flag_off_keeps_existing_death_grace_behavior(self) -> None:
        """既定 off では全員 down でも DEAD 猶予を待ち、即終了しない。"""
        runtime = create_world_runtime(_SCENARIO_PATH, config=runtime_config())
        _down_players(runtime, runtime.get_player_ids())

        result = runtime.check_game_end()

        assert result.is_ended is False
        assert "未確定プレイヤー" in result.reason

    def test_flag_on_ends_when_every_unresolved_player_is_down(self) -> None:
        """ON なら全員 down の時点で grace_ticks 経過を待たずに終了する。"""
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=runtime_config(end_on_all_down=True),
        )
        _down_players(runtime, runtime.get_player_ids())

        result = runtime.check_game_end()

        assert result.is_ended is True
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
        assert "行動可能プレイヤーがいない" in result.reason

    def test_flag_on_does_not_end_while_any_unresolved_player_can_act(self) -> None:
        """ON でも未確定かつ down していない player が残るなら終了しない。"""
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=runtime_config(end_on_all_down=True),
        )
        _down_players(runtime, runtime.get_player_ids()[:-1])

        result = runtime.check_game_end()

        assert result.is_ended is False
        assert "未確定プレイヤー" in result.reason
