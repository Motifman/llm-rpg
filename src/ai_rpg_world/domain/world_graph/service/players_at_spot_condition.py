"""`PLAYERS_AT_SPOT` の人数比較を全利用経路で共有する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


DEFAULT_REQUIRED_PLAYER_COUNT = 2


@dataclass(frozen=True)
class PlayersAtSpotConditionResult:
    """解決した必要人数と、在席数が条件を満たすかを対で返す。"""

    required_player_count: int
    is_satisfied: bool


def evaluate_players_at_spot(
    *,
    presence_count: int,
    required_player_count: Optional[int],
) -> PlayersAtSpotConditionResult:
    """必要人数の既定値を解決し、在席数がその人数以上かを判定する。"""
    required = (
        required_player_count
        if required_player_count is not None
        else DEFAULT_REQUIRED_PLAYER_COUNT
    )
    return PlayersAtSpotConditionResult(
        required_player_count=required,
        is_satisfied=presence_count >= required,
    )
