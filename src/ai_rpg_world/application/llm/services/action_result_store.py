"""行動結果ストアのデフォルト実装（in-memory）"""

from collections.abc import Mapping
from datetime import datetime, timezone

from ai_rpg_world.application.common.execution_provenance import ExecutionProvenance
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.contracts.interfaces import IActionResultStore
from ai_rpg_world.application.llm.services.unified_recent_event_store import (
    UnifiedRecentEventStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class DefaultActionResultStore(IActionResultStore):
    """プレイヤーごとに行動結果をリストで保持する in-memory 実装。"""

    def __init__(
        self,
        max_entries_per_player: int = 100,
        *,
        event_store: UnifiedRecentEventStore | None = None,
    ) -> None:
        if max_entries_per_player <= 0:
            raise ValueError("max_entries_per_player must be greater than 0")
        self._max_entries = max_entries_per_player
        self._event_store = event_store or UnifiedRecentEventStore()

    def _key(self, player_id: PlayerId) -> int:
        return player_id.value

    def append(
        self,
        player_id: PlayerId,
        action_summary: str,
        result_summary: str,
        occurred_at: datetime | None = None,
        *,
        success: bool = True,
        error_code: str | None = None,
        tool_name: str | None = None,
        identifier_arguments: Mapping[str, str] | None = None,
        free_text_argument_names: tuple[str, ...] = (),
        argument_fingerprint: str | None = None,
        should_reschedule: bool = False,
        game_time_label: str | None = None,
        omit_result_in_prompt: bool = False,
        inner_thought: str | None = None,
        intention: str | None = None,
        emotion_hint: str | None = None,
        occurred_tick: int | None = None,
        execution_provenance: ExecutionProvenance | None = None,
    ) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(action_summary, str):
            raise TypeError("action_summary must be str")
        if not isinstance(result_summary, str):
            raise TypeError("result_summary must be str")
        if occurred_at is not None and not isinstance(occurred_at, datetime):
            raise TypeError("occurred_at must be datetime or None")
        if not isinstance(success, bool):
            raise TypeError("success must be bool")
        if error_code is not None and not isinstance(error_code, str):
            raise TypeError("error_code must be str or None")
        if tool_name is not None and not isinstance(tool_name, str):
            raise TypeError("tool_name must be str or None")
        if identifier_arguments is not None and not isinstance(
            identifier_arguments, Mapping
        ):
            raise TypeError("identifier_arguments must be Mapping[str, str] or None")
        if not isinstance(free_text_argument_names, tuple):
            raise TypeError("free_text_argument_names must be tuple[str, ...]")
        if argument_fingerprint is not None and not isinstance(
            argument_fingerprint, str
        ):
            raise TypeError("argument_fingerprint must be str or None")
        if not isinstance(should_reschedule, bool):
            raise TypeError("should_reschedule must be bool")
        if game_time_label is not None and not isinstance(game_time_label, str):
            raise TypeError("game_time_label must be str or None")
        if not isinstance(omit_result_in_prompt, bool):
            raise TypeError("omit_result_in_prompt must be bool")
        if inner_thought is not None and not isinstance(inner_thought, str):
            raise TypeError("inner_thought must be str or None")
        if intention is not None and not isinstance(intention, str):
            raise TypeError("intention must be str or None")
        if emotion_hint is not None and not isinstance(emotion_hint, str):
            raise TypeError("emotion_hint must be str or None")
        if occurred_tick is not None and (
            not isinstance(occurred_tick, int) or isinstance(occurred_tick, bool)
        ):
            raise TypeError("occurred_tick must be int or None")
        # Issue #311 後続: フォールバックを tz-aware UTC に統一。
        # world_runtime は明示的に渡すが、それ以外の caller の取りこぼし防止。
        at = occurred_at if occurred_at is not None else datetime.now(timezone.utc)
        entry = ActionResultEntry(
            occurred_at=at,
            action_summary=action_summary,
            result_summary=result_summary,
            success=success,
            error_code=error_code,
            tool_name=tool_name,
            identifier_arguments=dict(identifier_arguments or {}),
            free_text_argument_names=free_text_argument_names,
            argument_fingerprint=argument_fingerprint,
            should_reschedule=should_reschedule,
            game_time_label=game_time_label,
            omit_result_in_prompt=omit_result_in_prompt,
            inner_thought=inner_thought,
            intention=intention,
            emotion_hint=emotion_hint,
            occurred_tick=occurred_tick,
            execution_provenance=execution_provenance,
        )
        self._event_store.append_action_result(
            player_id, entry, max_entries=self._max_entries
        )

    def get_recent(self, player_id: PlayerId, limit: int) -> list[ActionResultEntry]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if limit < 0:
            raise ValueError("limit must be 0 or greater")
        return self._event_store.get_recent_action_results(player_id, limit)
