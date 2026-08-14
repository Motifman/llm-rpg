"""prediction_context_id の二段階発行 (issue / attach / discarded note)。"""

from typing import TYPE_CHECKING, Optional

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder


def begin_prediction_context(
    builder: "DefaultPromptBuilder",
    player_id: PlayerId,
) -> Optional[str]:
    """U1 (二段階発行の 1 段目): passive recall より前に id を発行する。

    ledger 未注入なら常に None を返す (= id 機構 OFF の既存ランタイムと
    後方互換)。未消費の前回分があれば破棄され (= no-tool ターン / 例外で
    record に届かなかった / 途中で再スケジュールされた 等の想定内動作)、
    ERROR ではなく trace NOTE を残す。in-context 集合はまだ空で、この build
    の passive recall 完了後に ``attach_prediction_context`` で確定する。
    """
    if builder._prediction_context_ledger is None:
        return None
    result = builder._prediction_context_ledger.issue(player_id)
    if result.discarded is not None:
        emit_prediction_context_discarded_note(
            builder,
            player_id=player_id,
            discarded_id=result.discarded.prediction_context_id,
        )
    return result.prediction_context_id


def attach_prediction_context(
    builder: "DefaultPromptBuilder",
    *,
    player_id: PlayerId,
    prediction_context_id: Optional[str],
    episode_ids: tuple[str, ...],
    belief_ids: tuple[str, ...],
) -> None:
    """U1 (二段階発行の 2 段目): 発行済み id に in-context 集合を後付けする。

    ledger 未注入 / id 未発行 (= 機構 OFF) なら no-op。
    """
    if builder._prediction_context_ledger is None or prediction_context_id is None:
        return
    builder._prediction_context_ledger.attach(
        player_id,
        prediction_context_id,
        episode_ids=episode_ids,
        belief_ids=belief_ids,
    )


def emit_prediction_context_discarded_note(
    builder: "DefaultPromptBuilder",
    *,
    player_id: PlayerId,
    discarded_id: str,
) -> None:
    """未消費のまま次の build に上書きされた prediction_context_id を
    ``TraceEventKind.NOTE`` に残す (失敗は握りつぶす)。"""
    recorder = builder._resolve_trace_recorder()
    if recorder is None:
        return
    tick: Optional[int] = None
    if builder._current_tick_provider is not None:
        try:
            tick = builder._current_tick_provider()
        except Exception:
            tick = None
    try:
        recorder.record(
            TraceEventKind.NOTE,
            tick=tick,
            player_id=int(player_id.value),
            message="prediction_context_id discarded unconsumed before next build",
            discarded_prediction_context_id=discarded_id,
        )
    except Exception:
        builder._logger.debug(
            "trace recorder.record raised for NOTE (prediction_context_id discard); skipping",
            exc_info=True,
        )
