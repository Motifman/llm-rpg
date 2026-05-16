"""ツール名から ``IntentPhase`` を導く対応表。

設計
----
- 既存のツール名 prefix (``spot_graph_``, ``move_``, ``combat_``, ``speech_``,
  ``conversation_`` ...) を見て分類する
- 個別の tool name にも上書き可能 (例: ``spot_graph_travel_to`` は MOVEMENT、
  ``spot_graph_interact`` は INTERACTION)
- 未知のツールは ``IntentPhase.OTHER`` にフォールバック (BC で error にしない
  ことで新ツールの増設が容易)
"""

from __future__ import annotations

import logging

from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_PREFIX_COMBAT,
    TOOL_NAME_PREFIX_CONVERSATION,
    TOOL_NAME_PREFIX_MOVE,
    TOOL_NAME_PREFIX_SPEECH,
    TOOL_NAME_PREFIX_SPOT_GRAPH,
)
from ai_rpg_world.domain.intent.value_object.intent_phase import IntentPhase

logger = logging.getLogger(__name__)

# 具体的なツール名 → フェーズ (prefix より優先)
_EXPLICIT_TOOL_PHASE: dict[str, IntentPhase] = {
    "spot_graph_travel_to": IntentPhase.MOVEMENT,
    "spot_graph_interact": IntentPhase.INTERACTION,
    "spot_graph_explore": IntentPhase.INTERACTION,
    "spot_graph_set_sub_location": IntentPhase.MOVEMENT,
    "spot_graph_wait": IntentPhase.OTHER,
    "spot_graph_listen": IntentPhase.INTERACTION,
    "say": IntentPhase.SOCIAL,
    "whisper": IntentPhase.SOCIAL,
}

# prefix → フェーズ (汎用フォールバック)
_PREFIX_PHASE: tuple[tuple[str, IntentPhase], ...] = (
    (TOOL_NAME_PREFIX_MOVE, IntentPhase.MOVEMENT),
    (TOOL_NAME_PREFIX_COMBAT, IntentPhase.ATTACK),
    (TOOL_NAME_PREFIX_SPEECH, IntentPhase.SOCIAL),
    (TOOL_NAME_PREFIX_CONVERSATION, IntentPhase.SOCIAL),
    # SPOT_GRAPH は既定で INTERACTION 扱い (個別マッピングで上書き済みのものが
    # 優先される)
    (TOOL_NAME_PREFIX_SPOT_GRAPH, IntentPhase.INTERACTION),
)


def phase_for_tool(tool_name: str) -> IntentPhase:
    """ツール名から該当する ``IntentPhase`` を返す。

    1. 明示マッピングがあればそれを使う
    2. なければ prefix マッチ
    3. それでも見つからなければ ``IntentPhase.OTHER``
    """
    if not isinstance(tool_name, str) or not tool_name:
        # 上位で防いでいるはずの不正入力。診断のため警告ログを残しつつ
        # OTHER に倒すことで例外連鎖を防ぐ (post-tick hook を倒さない方針)。
        logger.warning("phase_for_tool got invalid tool_name=%r", tool_name)
        return IntentPhase.OTHER
    explicit = _EXPLICIT_TOOL_PHASE.get(tool_name)
    if explicit is not None:
        return explicit
    for prefix, phase in _PREFIX_PHASE:
        if tool_name.startswith(prefix):
            return phase
    return IntentPhase.OTHER
