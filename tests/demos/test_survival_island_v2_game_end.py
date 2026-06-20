"""survival_island_v2 の check_game_end が outcome 連動経路を取ることを確認 (Phase E-3c)。

v2 シナリオは集団 WIN/LOSE を廃止し、per-player outcome の all_resolved で
ゲーム終了する。本テストは:

- 初期状態 (全員 UNRESOLVED) では is_ended=False
- 全員の outcome を確定させると is_ended=True + player_outcomes snapshot が返る
- result (集団 WIN/LOSE) は意図的に None

を確認する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum


SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "survival_island_v2.json"
)


@pytest.fixture(scope="module")
def runtime():
    from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
    return create_world_runtime(SCENARIO_PATH)


class TestOutcomeGameEnd:
    """v2 の game end は all_resolved 連動。"""

    def test_初期状態は_未確定で_終了しない(self, runtime) -> None:
        result = runtime.check_game_end()
        assert result.is_ended is False
        # outcome モードに入っていることを reason で確認 (集団判定とは別経路)
        assert "outcome" in result.reason or "未確定" in result.reason

    def test_全員確定で_is_ended_True_かつ_player_outcomes_が返る(self, runtime) -> None:
        registry = runtime._player_outcome_registry
        assert registry is not None
        # 4 人全員に outcome をセット
        for spawn in runtime.scenario.player_spawns:
            from ai_rpg_world.domain.player.value_object.player_id import PlayerId
            registry.set_outcome(PlayerId(spawn.player_id), PlayerOutcomeEnum.STRANDED)

        result = runtime.check_game_end()

        assert result.is_ended is True
        # 集団 WIN/LOSE は意図的に None
        assert result.result is None
        # per-player outcomes が返る
        assert result.player_outcomes is not None
        assert len(result.player_outcomes) == 4
        for outcome in result.player_outcomes.values():
            assert outcome is PlayerOutcomeEnum.STRANDED
