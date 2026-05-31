from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum


@dataclass(frozen=True)
class GameEndResult:
    """ゲーム終了判定の結果。

    Phase E-3c: 集団勝敗 (result) と並列に、Per-player 終局 outcome を保持できる
    ようにした。outcome ベースのシナリオでは `result` は None で、
    `player_outcomes` に各プレイヤーの最終 outcome (RESCUED/DEAD/STRANDED) を
    詰める。既存の集団判定経路では `player_outcomes` は None のまま。
    """

    is_ended: bool
    result: Optional[GameResultEnum]
    reason: str
    # Phase E-3c: 個別 outcome の snapshot ({player_id_int: outcome})。
    # None なら本結果は per-player モードではない (集団判定 / 続行中)。
    player_outcomes: Optional[Mapping[int, PlayerOutcomeEnum]] = field(default=None)
