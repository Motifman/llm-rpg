"""GameEndResult.player_outcomes フィールドの後方互換性 (Phase E-3c)。

v1 経路 (集団判定) で GameEndResult を構築するとき player_outcomes は None
のまま、v2 経路 (outcome モード) では non-None で各プレイヤーの最終 outcome
を含むことを確認する。
"""

from __future__ import annotations

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum
from ai_rpg_world.domain.world_graph.value_object.game_end_result import GameEndResult


class TestBackwardCompat:
    """既存呼び出し (3 引数) は player_outcomes=None で動く。"""

    def test_既存_3_引数_constructor_で_player_outcomes_は_None(self) -> None:
        result = GameEndResult(is_ended=True, result=GameResultEnum.WIN, reason="勝利")
        assert result.player_outcomes is None
        assert result.result is GameResultEnum.WIN

    def test_per_player_モードの_GameEndResult(self) -> None:
        snapshot = {1: PlayerOutcomeEnum.RESCUED, 2: PlayerOutcomeEnum.DEAD}
        result = GameEndResult(
            is_ended=True, result=None, reason="全員 outcome 確定",
            player_outcomes=snapshot,
        )
        assert result.is_ended is True
        assert result.result is None  # 集団勝敗は意図的に None
        assert result.player_outcomes is not None
        assert result.player_outcomes[1] is PlayerOutcomeEnum.RESCUED
        assert result.player_outcomes[2] is PlayerOutcomeEnum.DEAD
