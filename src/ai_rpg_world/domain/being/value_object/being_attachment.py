"""BeingAttachment — Being が現在「どの世界の・どの player に乗っているか」。

PR #462 §2.1 (R1) の Being 集約構成要素:

    attachments: 現在どの世界のどの player に「乗って」いるか (0..1)

= 「世界への参加は attachment (関係) であって identity ではない」を表現する VO。
detach しても経験は Being に残り、別世界・別 run・外部対話 (R4) に持ち越せる。

本 PR (Phase 2 PR2) では VO の導入と Being 集約への接続のみ。既存 world / player
集約との配線 (= 実際にどう attach を切替えるか) は後続 PR で扱う。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingAttachmentValidationException,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId


@dataclass(frozen=True)
class BeingAttachment:
    """Being が乗っている (world, player) のペアを表す値オブジェクト。

    - ``world_id``: 参加している世界の ID
    - ``player_id``: その世界での attachment 先 player

    Being 集約は同時に高々 1 つの attachment しか持たない (0..1)。
    複数世界への同時参加は YAGNI として未対応 (PR #462 §4 議論ポイント)。
    """

    world_id: WorldId
    player_id: PlayerId

    def __post_init__(self) -> None:
        if not isinstance(self.world_id, WorldId):
            raise BeingAttachmentValidationException(
                f"world_id must be WorldId, got {type(self.world_id).__name__}"
            )
        if not isinstance(self.player_id, PlayerId):
            raise BeingAttachmentValidationException(
                f"player_id must be PlayerId, got {type(self.player_id).__name__}"
            )


__all__ = ["BeingAttachment"]
