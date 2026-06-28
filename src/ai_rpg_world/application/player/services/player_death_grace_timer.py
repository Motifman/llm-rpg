"""ダウン後 DEAD 確定までの猶予 tick を管理する service (Issue #621)。

旧仕様 (PR #607 以前): PlayerDownedOutcomeHandler が即時 DEAD 確定。
新仕様 (Issue #621): ダウン後 30 tick の猶予を設ける。猶予中に
first_aid / tend_to_player で revive されれば DEAD 確定を回避できる。

責務分離:
- PlayerOutcomeRegistry: 確定済み outcome (UNRESOLVED/RESCUED/DEAD/STRANDED)
- PlayerDeathGraceTimer (本 service): 猶予中の pending state
- PlayerDeathGraceTickStage: tick 毎に本 timer をスキャン → overdue → 確定

設計判断:
- PlayerStatusAggregate に `_downed_at_tick` を持たせると domain を汚し、
  既存の `apply_damage` シグネチャに current_tick を追加する破壊的変更が
  caller 全てに波及する。application 層に独立した service として置く
  ことで domain 不変、handler 経路だけで完結する
- 同じ player が「ダウン → revive → 再ダウン」した場合、register が
  上書きされて新しい起点で 30 tick 猶予がリセットされる
"""

from __future__ import annotations

from typing import Dict, List

from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class PlayerDeathGraceTimer:
    """ダウン後 DEAD 確定までの猶予を player ごとに保持する。

    state: { player_id (int): downed_at_tick (int) }
    """

    def __init__(self) -> None:
        self._downed_at: Dict[int, int] = {}

    def register(self, player_id: PlayerId, downed_at_tick: int) -> None:
        """ダウンを記録する。既に pending なら downed_at_tick を上書き
        (= 再ダウンで猶予がリセット)。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(downed_at_tick, int) or downed_at_tick < 0:
            raise ValueError(
                f"downed_at_tick must be non-negative int, got {downed_at_tick!r}"
            )
        self._downed_at[int(player_id)] = downed_at_tick

    def cancel(self, player_id: PlayerId) -> None:
        """pending を削除する。revive 時に呼ぶ。
        pending でない player への呼び出しは no-op (冪等)。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        self._downed_at.pop(int(player_id), None)

    def is_pending(self, player_id: PlayerId) -> bool:
        """pending 中 (= ダウンしたが DEAD 確定前) か。"""
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        return int(player_id) in self._downed_at

    def get_downed_at_tick(self, player_id: PlayerId) -> "int | None":
        """``player_id`` が pending なら downed_at_tick を返し、無ければ None。

        Phase 5: revive 時の post hoc observation 構築で ``current_tick -
        downed_at_tick`` を求めるのに使う。cancel される前に handler が読む。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        return self._downed_at.get(int(player_id))

    def overdue_players(
        self, current_tick: int, grace_ticks: int
    ) -> List[PlayerId]:
        """猶予 tick を過ぎた pending player の list を返す。

        判定: current_tick - downed_at_tick >= grace_ticks
        (= ちょうど grace_ticks 経過した時点で overdue 入り、inclusive)
        """
        if not isinstance(grace_ticks, int) or grace_ticks < 0:
            raise ValueError(
                f"grace_ticks must be non-negative int, got {grace_ticks!r}"
            )
        return [
            PlayerId(pid)
            for pid, downed_at in self._downed_at.items()
            if current_tick - downed_at >= grace_ticks
        ]
