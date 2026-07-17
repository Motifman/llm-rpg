"""PlayerRevivedEvent を受けて StateCollapseEvidenceTranscriber の dedup 状態を
リセットする (PR-D)。

``PlayerDownedStateCollapseEvidenceHandler`` が down 遷移時に積んだ dedup
状態 (「down 中は再度 evidence を積まない」) を、復帰時にクリアする対。
これがないと、一度 down した being は復帰後に再度 down しても evidence が
二度と積まれない (dedup 状態が永久に残る) 静かな劣化になる。

evidence 記録は best-effort な副作用なので、being 未解決 / transcriber 側の
例外はここで握って pipeline を止めない。
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.player.event.status_events import PlayerRevivedEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_logger = logging.getLogger(__name__)


class PlayerRevivedStateCollapseEvidenceHandler(EventHandler[PlayerRevivedEvent]):
    """PlayerRevivedEvent → StateCollapseEvidenceTranscriber.clear_down_state。"""

    def __init__(
        self,
        *,
        transcriber: object,
        being_id_resolver: Callable[[PlayerId], Optional[BeingId]],
    ) -> None:
        if not callable(being_id_resolver):
            raise TypeError("being_id_resolver must be callable")
        self._transcriber = transcriber
        self._being_id_resolver = being_id_resolver

    def handle(self, event: PlayerRevivedEvent) -> None:
        try:
            being_id = self._being_id_resolver(event.aggregate_id)
            if being_id is None:
                return
            self._transcriber.clear_down_state(being_id)  # type: ignore[attr-defined]
        except Exception:
            _logger.exception(
                "PlayerRevivedStateCollapseEvidenceHandler failed for player_id=%s",
                event.aggregate_id,
            )


__all__ = ["PlayerRevivedStateCollapseEvidenceHandler"]
