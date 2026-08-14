"""reason-first trace 記録ヘルパ。"""

from __future__ import annotations

import logging
from typing import Any

from ai_rpg_world.domain.player.value_object.player_id import PlayerId

logger = logging.getLogger(__name__)

def record_reason_first_trace(
    wiring, kind: str, player_id: PlayerId, **payload: Any
) -> None:
    trace_recorder = getattr(wiring.runtime, "trace_recorder", None)
    if trace_recorder is None:
        return
    try:
        tick = int(wiring.runtime.current_tick())
    except Exception:
        tick = None
    try:
        trace_recorder.record(
            kind,
            tick=tick,
            player_id=int(player_id.value),
            **payload,
        )
    except Exception:
        logger.exception("trace_recorder.record(%s) failed", kind)
