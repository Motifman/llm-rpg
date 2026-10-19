"""行動結果の記録を 1 箇所に束ねる共有サービス (U1)。

従来 world_runtime._record_action_result が inline で持っていた store への append を
共有コアに抽出した。直後に回していた古いエピソードの区切りの書き込みと
クラスタ昇格は #1631 で消した。独白 (inner_thought) や fingerprint 等は optional
引数として通す。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ai_rpg_world.application.common.execution_provenance import current_execution_provenance
from ai_rpg_world.application.llm.contracts.interfaces import IActionResultStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class ActionResultRecorder:
    """行動結果を store に積む共有の入口。"""

    def __init__(self, action_result_store: IActionResultStore) -> None:
        if action_result_store is None:
            raise TypeError("action_result_store must not be None")
        self._store = action_result_store

    def record(
        self,
        player_id: PlayerId,
        *,
        action_summary: str,
        result_summary: str,
        occurred_at: datetime | None = None,
        tool_name: str | None = None,
        identifier_arguments: Mapping[str, str] | None = None,
        free_text_argument_names: tuple[str, ...] = (),
        success: bool = True,
        error_code: str | None = None,
        occurred_tick: int | None = None,
        game_time_label: str | None,
        inner_thought: str | None = None,
        argument_fingerprint: str | None = None,
        should_reschedule: bool = False,
        omit_result_in_prompt: bool = False,
    ) -> None:
        """action を store に積む。"""
        self._store.append(
            player_id,
            action_summary=action_summary,
            result_summary=result_summary,
            occurred_at=occurred_at,
            success=success,
            error_code=error_code,
            tool_name=tool_name,
            identifier_arguments=identifier_arguments,
            free_text_argument_names=free_text_argument_names,
            argument_fingerprint=argument_fingerprint,
            should_reschedule=should_reschedule,
            game_time_label=game_time_label,
            omit_result_in_prompt=omit_result_in_prompt,
            execution_provenance=current_execution_provenance(),
            inner_thought=inner_thought,
            occurred_tick=occurred_tick,
        )


__all__ = ["ActionResultRecorder"]
