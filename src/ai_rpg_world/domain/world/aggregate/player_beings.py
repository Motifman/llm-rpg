"""ある世界で、どの Being がどのプレイヤーを動かしているかの対応表 (#1928、design_decisions D1928)。

誰がどのプレイヤーを動かしているかは、ゲームが知っていればよい。Being はゲームのプレイヤーの番号を知らなくてよいので、
対応表はゲームの側に置く。#1339 で環境を集約にし直すときに、「今自分の中に誰が入っているか」として環境の集約に移す。
"""

from __future__ import annotations

from collections.abc import Iterable

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.exception.player_beings_exception import (
    PlayerAlreadyDrivenException,
    PlayerBeingsValidationException,
)
from ai_rpg_world.domain.world.value_object.world_id import WorldId


class PlayerBeings(AggregateRoot):
    """1 人のプレイヤーを動かす Being は 1 つ。1 つの Being が動かすプレイヤーは 1 人。"""

    def __init__(self, world_id: WorldId, pairs: Iterable[tuple[PlayerId, BeingId]] = ()) -> None:
        super().__init__()
        if not isinstance(world_id, WorldId):
            raise PlayerBeingsValidationException(f"world_id must be WorldId, got {type(world_id).__name__}")
        self._world_id = world_id
        self._being_by_player: dict[PlayerId, BeingId] = {}
        self._player_by_being: dict[BeingId, PlayerId] = {}
        self.replace_with(pairs)

    @property
    def world_id(self) -> WorldId:
        return self._world_id

    def being_of(self, player_id: PlayerId) -> BeingId | None:
        return self._being_by_player.get(player_id)

    def player_of(self, being_id: BeingId) -> PlayerId | None:
        return self._player_by_being.get(being_id)

    def pairs(self) -> tuple[tuple[PlayerId, BeingId], ...]:
        """プレイヤーの番号の順。"""
        return tuple(sorted(self._being_by_player.items(), key=lambda pair: pair[0].value))

    def drive(self, player_id: PlayerId, being_id: BeingId) -> None:
        """``being_id`` に ``player_id`` を動かさせる。

        別の Being がもう動かしているプレイヤーなら、``PlayerAlreadyDrivenException`` で断る。``being_id`` がほかの
        プレイヤーを動かしていれば、そこを離れてから動かす (Being は同時に 1 つの環境にしか入れない)。
        """
        if not isinstance(player_id, PlayerId):
            raise PlayerBeingsValidationException(f"player_id must be PlayerId, got {type(player_id).__name__}")
        if not isinstance(being_id, BeingId):
            raise PlayerBeingsValidationException(f"being_id must be BeingId, got {type(being_id).__name__}")
        current = self._being_by_player.get(player_id)
        if current == being_id:
            return
        if current is not None:
            raise PlayerAlreadyDrivenException(
                f"player {player_id.value} is already driven by {current.value}; {being_id.value} cannot drive it"
            )
        previous_player = self._player_by_being.pop(being_id, None)
        if previous_player is not None:
            del self._being_by_player[previous_player]
        self._being_by_player[player_id] = being_id
        self._player_by_being[being_id] = player_id

    def replace_with(self, pairs: Iterable[tuple[PlayerId, BeingId]]) -> None:
        """対応表をまるごと入れ替える (snapshot から戻すとき)。同じプレイヤーか同じ Being が 2 回出てくれば断り、今の表を変えない。"""
        being_by_player: dict[PlayerId, BeingId] = {}
        player_by_being: dict[BeingId, PlayerId] = {}
        for player_id, being_id in pairs:
            if not isinstance(player_id, PlayerId) or not isinstance(being_id, BeingId):
                raise PlayerBeingsValidationException(
                    f"pair must be (PlayerId, BeingId), got {(player_id, being_id)!r}"
                )
            if player_id in being_by_player:
                raise PlayerBeingsValidationException(f"player {player_id.value} is driven by two Beings")
            if being_id in player_by_being:
                raise PlayerBeingsValidationException(f"{being_id.value} drives two players")
            being_by_player[player_id] = being_id
            player_by_being[being_id] = player_id
        self._being_by_player = being_by_player
        self._player_by_being = player_by_being


__all__ = ["PlayerBeings"]
