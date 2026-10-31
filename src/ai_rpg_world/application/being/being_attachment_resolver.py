"""BeingAttachmentResolver — プレイヤーと、それを動かす Being を引き合う。

どの Being がどのプレイヤーを動かしているかは、ゲームの側の対応表 (``PlayerBeings``) が持つ (#1928、
design_decisions D1928)。Being の保存先を番号で探さない。1 人のプレイヤーを動かす Being は 1 つという決まりは、
対応表が自分で守る。
"""

from __future__ import annotations

from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.domain.being.repository.being_repository import BeingRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.aggregate.player_beings import PlayerBeings
from ai_rpg_world.domain.world.value_object.world_id import WorldId


class BeingAttachmentResolver:
    """``player_beings`` の世界のプレイヤーだけを引く。ほかの世界を尋ねられたら、動かす Being はいない。"""

    def __init__(self, being_repository: BeingRepository, player_beings: PlayerBeings) -> None:
        if not isinstance(being_repository, BeingRepository):
            raise TypeError(f"being_repository must be BeingRepository, got {type(being_repository).__name__}")
        if not isinstance(player_beings, PlayerBeings):
            raise TypeError(f"player_beings must be PlayerBeings, got {type(player_beings).__name__}")
        self._repo = being_repository
        self._player_beings = player_beings

    def resolve_being_id(self, world_id: WorldId, player_id: PlayerId) -> BeingId | None:
        """(world, player) を動かしている Being の ID。いなければ None。"""
        if not isinstance(world_id, WorldId):
            raise TypeError(f"world_id must be WorldId, got {type(world_id).__name__}")
        if not isinstance(player_id, PlayerId):
            raise TypeError(f"player_id must be PlayerId, got {type(player_id).__name__}")
        if world_id != self._player_beings.world_id:
            return None
        return self._player_beings.being_of(player_id)

    def resolve_attached_being(self, world_id: WorldId, player_id: PlayerId) -> Being | None:
        """(world, player) を動かしている Being。いないか、保存先に無ければ None。"""
        being_id = self.resolve_being_id(world_id, player_id)
        return self._repo.find_by_id(being_id) if being_id is not None else None

    def resolve_player_id(self, being_id: BeingId) -> PlayerId | None:
        """Being が動かしているプレイヤー。動かしていなければ None。"""
        if not isinstance(being_id, BeingId):
            raise TypeError(f"being_id must be BeingId, got {type(being_id).__name__}")
        return self._player_beings.player_of(being_id)


__all__ = ["BeingAttachmentResolver"]
