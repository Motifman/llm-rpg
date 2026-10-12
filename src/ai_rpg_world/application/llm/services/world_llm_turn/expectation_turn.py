"""ゲームの 1 ターンで、届いた出来事を予期の清算の材料に写す (#1440)。"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

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

# 清算の時系列は外れた予期の信念の材料にそのまま載る (#1509)。行動と観測の文に入る
# 識別子を外す。小文字で始まる語は tool の名前やシナリオの操作名 (interact、gather、
# search_wreck_hold) で、文が崩れないよう「操作」に置き換える。操作名はシナリオごとに
# 増え、tool の一覧では拾いきれないので、語の形で拾う。数字と a〜f だけでできた 6 文字
# 以上の語はメモの ID (774c5e、a8cbc3) で、消す。数と単位 (1.5kg、10m) と、小文字で
# 始まらない語 (SOS、CLEAR) は残す。発言は本人たちの言葉なので触らない。
_TOOL_NAME_REPLACEMENT = "操作"
_WORD_PATTERN = re.compile(r"[ \t]?(?<![A-Za-z0-9_.])[A-Za-z0-9_]+(?![A-Za-z0-9_])[ \t]?")
_HEX_ID = re.compile(r"(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])[0-9a-f]{6,}")


def _replace_identifier(match: re.Match[str]) -> str:
    word = match.group(0).strip(" \t")
    if _HEX_ID.fullmatch(word):
        return ""
    if word[0].islower() and len(word) > 1:
        return _TOOL_NAME_REPLACEMENT
    return match.group(0)


def without_tool_names(text: str) -> str:
    """行動と観測の文に入った tool の名前を「操作」に置き換え、ID を消す。前後の半角空白も詰める。"""
    return _WORD_PATTERN.sub(_replace_identifier, text)


def turn_material(
    entries: Iterable[UnifiedRecentEventEntry], *, self_name: str
) -> TurnMaterial:
    """観測と自分の行動の結果を、届いた順に行動と発言へ分ける。

    自分の行動は本人の名前を付けて書く。行動の要約は一人称の表示文で、主語が
    無いと Jev が他の人の行動と取り違える。行動と観測の文からは tool の名前と
    ID を外す。発言は本人たちの言葉なので、そのまま写す。
    """
    actions: list[str] = []
    speeches: list[str] = []
    for entry in entries:
        label = f"[{entry.game_time_label}] " if entry.game_time_label else ""
        payload = entry.payload
        if isinstance(payload, ActionResultEntry):
            if payload.tool_name == TOOL_NAME_SPEECH:
                speeches.append(
                    f"{label}{self_name}: {payload.action_summary} → {payload.result_summary}"
                )
            else:
                actions.append(
                    f"{label}{self_name}: {without_tool_names(payload.action_summary)}"
                    f" → {without_tool_names(payload.result_summary)}"
                )
            continue
        if payload.output.structured.get("type") in _SPEECH_OBSERVATION_TYPES:
            speeches.append(f"{label}{payload.output.prose}")
        else:
            actions.append(f"{label}{without_tool_names(payload.output.prose)}")
    return TurnMaterial(actions=tuple(actions), speeches=tuple(speeches))


def _record(
    runtime: Any, kind: str, player_id: PlayerId, payload: dict[str, Any]
) -> None:
    recorder = getattr(runtime, "trace_recorder", None)
    if recorder is None:
        return
    try:
        tick = runtime.current_tick()
    except Exception:
        tick = None
    try:
        recorder.record(kind, tick=tick, player_id=player_id.value, **payload)
    except Exception:
        logger.exception("trace_recorder.record(%s) failed", kind)


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


__all__ = [
    "settle_expectations_after_turn",
    "turn_material",
    "without_tool_names",
]
