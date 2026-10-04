"""ゲームの 1 ターンで、書かれた予期を積み (#1441)、届いた出来事を予期の清算の材料に写す (#1440)。"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from ai_rpg_world.application.being.expectation.forming import (
    ExpectationFormingInterrupted,
)
from ai_rpg_world.application.being.expectation.settlement import TurnMaterial
from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    UnifiedRecentEventEntry,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.action_summary_format import (
    format_action_summary_for_display,
)
from ai_rpg_world.application.llm.services.expectation_arguments import (
    read_written_expectations,
)
from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import (
    EXPECTATIONS_FIELD_NAME,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPEECH
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.memory.expectation.aggregate.expectation import (
    Expectation,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services.world_llm_turn.wiring import (
        WorldLlmWiring,
    )

logger = logging.getLogger(__name__)

_SPEECH_OBSERVATION_TYPES = frozenset({"player_spoke"})

# 清算の時系列は外れた予期の信念の材料にそのまま載る (#1509)。この世界の出来事は日本語で
# 書かれ、小文字の英字で始まる語は tool の名前、シナリオの操作名 (gather、
# search_wreck_hold)、メモの ID (a8cbc3) のような識別子になる。操作名はシナリオごとに
# 増え、tool の一覧では拾いきれないので、語の形で拾う。大文字で始まる語 (SOS) は残す。
_IDENTIFIER_REPLACEMENT = "操作"
_IDENTIFIER_PATTERN = re.compile(
    r"[ \t]?(?<![A-Za-z0-9_])[a-z][a-z0-9_]+(?![A-Za-z0-9_])[ \t]?"
)


def without_tool_names(text: str) -> str:
    """文に入った tool の名前などの識別子を「操作」に置き換える。前後の半角空白も詰める。"""
    return _IDENTIFIER_PATTERN.sub(_IDENTIFIER_REPLACEMENT, text)


def turn_material(
    entries: Iterable[UnifiedRecentEventEntry], *, self_name: str
) -> TurnMaterial:
    """観測と自分の行動の結果を、届いた順に行動と発言へ分ける。

    自分の行動は本人の名前を付けて書く。行動の要約は一人称の表示文で、主語が
    無いと Jev が他の人の行動と取り違える。tool の名前は文から外す。
    """
    actions: list[str] = []
    speeches: list[str] = []
    for entry in entries:
        label = f"[{entry.game_time_label}] " if entry.game_time_label else ""
        payload = entry.payload
        if isinstance(payload, ActionResultEntry):
            text = (
                f"{label}{self_name}: {without_tool_names(payload.action_summary)}"
                f" → {without_tool_names(payload.result_summary)}"
            )
            target = speeches if payload.tool_name == TOOL_NAME_SPEECH else actions
            target.append(text)
            continue
        text = f"{label}{without_tool_names(payload.output.prose)}"
        if payload.output.structured.get("type") in _SPEECH_OBSERVATION_TYPES:
            speeches.append(text)
        else:
            actions.append(text)
    return TurnMaterial(actions=tuple(actions), speeches=tuple(speeches))


def form_expectations_from_call(
    wiring: WorldLlmWiring,
    player_id: PlayerId,
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
    tools_payload: Any,
) -> None:
    """tool 呼び出しに書かれた予期を、この手のターンの予期として積む。

    予期の引数を付けて送った tool の呼び出しだけを読む。付けていない tool
    (記憶の tool、2 段階ターンの評価) の引数に予期が紛れていても積まない。
    行動の成否を待たずに積む。行動が失敗しても、本人がそう予期した事実は残り、
    失敗の結果は清算の材料になる。

    積む途中の失敗でゲームのターンを止めない。理由を trace に残す。
    """
    forming = wiring.expectation_forming
    if forming is None or not _offered_with_expectations(tools_payload, tool_name):
        return
    runtime = wiring.runtime
    read = read_written_expectations(arguments)
    trace: dict[str, Any] = {
        "being_id": None,
        "turn": None,
        "tool": tool_name,
        "argument_present": read.present,
        "formed_count": 0,
        "formed": [],
        "rejected": [
            {"index": r.index, "reason": r.reason, "raw": r.raw} for r in read.rejected
        ],
        "context_found": False,
        "beliefs_in_mind": [],
        "episodes_in_mind": [],
        "skipped_reason": None,
        "error": None,
    }
    try:
        acting = runtime._acting_being_for(player_id)
        if acting is None:
            trace["skipped_reason"] = "no_acting_being"
            return
        trace["being_id"] = acting.being_id.value
        trace["turn"] = runtime._expectation_store.current_turn(acting.being_id)
        ledger = runtime._get_prediction_context_ledger()
        context = None if ledger is None else ledger.peek(player_id)
        if context is None:
            # 台帳はプロンプトを組むたびに発行するので、ここで無いのは配線の崩れ。
            # 信念が 0 件だったのと区別できるよう、context_found に残す。
            logger.warning(
                "prediction context is missing for player=%s; expectations are "
                "formed without beliefs or episodes in mind",
                player_id.value,
            )
        trace["context_found"] = context is not None
        beliefs = () if context is None else context.belief_ids
        episodes = () if context is None else context.episode_ids
        trace["beliefs_in_mind"] = list(beliefs)
        trace["episodes_in_mind"] = list(episodes)
        try:
            formed = forming.form(
                acting.being_id,
                read.written,
                formed_with=format_action_summary_for_display(tool_name, arguments),
                beliefs_in_mind=beliefs,
                episodes_in_mind=episodes,
            )
        except ExpectationFormingInterrupted as interrupted:
            _fill_formed(trace, interrupted.saved)
            raise
        _fill_formed(trace, formed)
    except Exception as exc:
        logger.exception("expectation forming failed for player=%s", player_id.value)
        cause = exc.__cause__ if isinstance(exc, ExpectationFormingInterrupted) else exc
        trace["skipped_reason"] = "forming_failed"
        trace["error"] = f"{type(cause).__name__}: {cause}"
    finally:
        _record(runtime, TraceEventKind.EXPECTATION_FORMED, player_id, trace)


def _fill_formed(trace: dict[str, Any], formed: Iterable[Expectation]) -> None:
    trace["formed"] = [
        {
            "expectation_id": e.expectation_id.value,
            "what": e.content,
            "when": e.due,
            "likelihood": e.likelihood.value,
        }
        for e in formed
    ]
    trace["formed_count"] = len(trace["formed"])


def _offered_with_expectations(tools_payload: Any, name: str) -> bool:
    for tool in tools_payload or ():
        function = tool.get("function") if isinstance(tool, dict) else None
        if not isinstance(function, dict) or function.get("name") != name:
            continue
        parameters = function.get("parameters")
        properties = parameters.get("properties") if isinstance(parameters, dict) else None
        return isinstance(properties, dict) and EXPECTATIONS_FIELD_NAME in properties
    return False


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
    "form_expectations_from_call",
    "settle_expectations_after_turn",
    "turn_material",
    "without_tool_names",
]
