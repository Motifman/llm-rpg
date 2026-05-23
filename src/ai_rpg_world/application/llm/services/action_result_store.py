"""行動結果ストアのデフォルト実装（in-memory）"""

from datetime import datetime
from typing import Dict, List, Optional

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.contracts.interfaces import IActionResultStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class DefaultActionResultStore(IActionResultStore):
    """プレイヤーごとに行動結果をリストで保持する in-memory 実装。"""

    def __init__(self, max_entries_per_player: int = 100) -> None:
        if max_entries_per_player <= 0:
            raise ValueError("max_entries_per_player must be greater than 0")
        self._max_entries = max_entries_per_player
        self._store: Dict[int, List[ActionResultEntry]] = {}

    def _key(self, player_id: PlayerId) -> int:
        return player_id.value

    def append(
        self,
        player_id: PlayerId,
        action_summary: str,
        result_summary: str,
        occurred_at: Optional[datetime] = None,
        *,
        success: bool = True,
        error_code: Optional[str] = None,
        tool_name: Optional[str] = None,
        argument_fingerprint: Optional[str] = None,
        should_reschedule: bool = False,
        game_time_label: Optional[str] = None,
        omit_result_in_prompt: bool = False,
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
        at = occurred_at if occurred_at is not None else datetime.now()
        entry = ActionResultEntry(
            occurred_at=at,
            action_summary=action_summary,
            result_summary=result_summary,
            success=success,
            error_code=error_code,
            tool_name=tool_name,
            argument_fingerprint=argument_fingerprint,
            should_reschedule=should_reschedule,
            game_time_label=game_time_label,
            omit_result_in_prompt=omit_result_in_prompt,
        )
        key = self._key(player_id)
        if key not in self._store:
            self._store[key] = []
        self._store[key].append(entry)
        if len(self._store[key]) > self._max_entries:
            self._store[key] = self._store[key][-self._max_entries :]

    def get_recent(self, player_id: PlayerId, limit: int) -> List[ActionResultEntry]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if limit < 0:
            raise ValueError("limit must be 0 or greater")
        key = self._key(player_id)
        entries = self._store.get(key, [])
        sorted_entries = sorted(entries, key=lambda e: e.occurred_at, reverse=True)
        return sorted_entries[:limit]
