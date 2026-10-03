"""ゲームの 1 ターンに届いた出来事を、予期の清算の材料に写す (#1440)。"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING

from ai_rpg_world.application.being.expectation.settlement import TurnMaterial
from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    UnifiedRecentEventEntry,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPEECH
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services.world_llm_turn.wiring import (
        WorldLlmWiring,
    )

logger = logging.getLogger(__name__)

_SPEECH_OBSERVATION_TYPES = frozenset({"player_spoke"})


def turn_material(
    entries: Iterable[UnifiedRecentEventEntry], *, self_name: str
) -> TurnMaterial:
    """観測と自分の行動の結果を、届いた順に行動と発言へ分ける。

    自分の行動は本人の名前を付けて書く。行動の要約は一人称の表示文で、主語が
    無いと Jev が他の人の行動と取り違える。
    """
    actions: list[str] = []
    speeches: list[str] = []
    for entry in entries:
        label = f"[{entry.game_time_label}] " if entry.game_time_label else ""
        payload = entry.payload
        if isinstance(payload, ActionResultEntry):
            text = f"{label}{self_name}: {payload.action_summary} → {payload.result_summary}"
            target = speeches if payload.tool_name == TOOL_NAME_SPEECH else actions
            target.append(text)
            continue
        text = f"{label}{payload.output.prose}"
        if payload.output.structured.get("type") in _SPEECH_OBSERVATION_TYPES:
            speeches.append(text)
        else:
            actions.append(text)
    return TurnMaterial(actions=tuple(actions), speeches=tuple(speeches))


def settle_expectations_after_turn(wiring: WorldLlmWiring, player_id: PlayerId) -> None:
    """ターンの終わり、ターンを閉じる前に呼ぶ。閉じると、このターンの出来事が引けなくなる。

    清算の失敗でゲームのターンを止めない。清算の service の中で起きた失敗は
    service が trace に残すので、ここでは service に渡す前の失敗だけを残す。
    """
    settlement = wiring.expectation_settlement
    if settlement is None:
        return
    runtime = wiring.runtime
    handed_over = False
    being_id: str | None = None
    tick: int | None = None
    try:
        tick = runtime.current_tick()
        acting = runtime._acting_being_for(player_id)
        if acting is None:
            _trace_skipped(runtime, player_id, tick, None, "no_acting_being", None)
            return
        being_id = acting.being_id.value
        self_name = runtime.get_player_name(player_id)
        material = turn_material(
            runtime._recent_event_store.open_turn_entries(player_id),
            self_name=self_name,
        )
        handed_over = True
        settlement.settle_turn(
            acting.being_id,
            self_name=self_name,
            material=material,
            tick=tick,
            player_id=player_id.value,
        )
    except Exception as exc:
        logger.exception("expectation settlement failed for player=%s", player_id.value)
        if not handed_over:
            _trace_skipped(
                runtime,
                player_id,
                tick,
                being_id,
                "settlement_failed",
                f"{type(exc).__name__}: {exc}",
            )


def _trace_skipped(
    runtime: object,
    player_id: PlayerId,
    tick: int | None,
    being_id: str | None,
    reason: str,
    detail: str | None,
) -> None:
    recorder = getattr(runtime, "trace_recorder", None)
    if recorder is None:
        return
    recorder.record(
        TraceEventKind.EXPECTATION_SETTLEMENT,
        tick=tick,
        player_id=player_id.value,
        being_id=being_id,
        judged=False,
        skipped_reason=reason,
        unavailable_reason=detail,
    )


__all__ = ["settle_expectations_after_turn", "turn_material"]
