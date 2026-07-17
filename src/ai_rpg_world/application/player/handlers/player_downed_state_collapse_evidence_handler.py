"""PlayerDownedEvent を受けて StateCollapseEvidenceTranscriber に転記する (PR-D)。

責務:
- ``PlayerDownedEvent.aggregate_id`` (PlayerId) から being_id を解決する
  (Being 文脈の解決自体は呼び出し側から渡される resolver に委ねる。domain
  event ハンドラは being 解決の実装詳細を持たない)
- 解決できたら ``transcriber.record_down_evidence(being_id)`` を呼ぶだけ
  (dedup 判定は transcriber 側の責務、本ハンドラは判定を持たない)
- evidence 記録は本編ゲームプレイに影響しない best-effort な副作用なので、
  being 未解決 / transcriber 側の例外はここで握って pipeline を止めない
  (``PipelineEventPublisher._dispatch`` の side handler 例外握りとは独立に、
  本ハンドラ自身でも握っておく — テストで直接 handle() を呼ぶ経路でも
  同じ安全性を保証するため)
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_logger = logging.getLogger(__name__)


class PlayerDownedStateCollapseEvidenceHandler(EventHandler[PlayerDownedEvent]):
    """PlayerDownedEvent → StateCollapseEvidenceTranscriber.record_down_evidence。"""

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

    def handle(self, event: PlayerDownedEvent) -> None:
        try:
            being_id = self._being_id_resolver(event.aggregate_id)
            if being_id is None:
                return
            self._transcriber.record_down_evidence(being_id)  # type: ignore[attr-defined]
        except Exception:
            _logger.exception(
                "PlayerDownedStateCollapseEvidenceHandler failed for player_id=%s",
                event.aggregate_id,
            )


__all__ = ["PlayerDownedStateCollapseEvidenceHandler"]
