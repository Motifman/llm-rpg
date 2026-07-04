"""ツール名から ``IntentPhase`` を導く対応表。

設計
----
- 既存のツール名 prefix (``move_``, ``combat_``, ``speech_``,
  ``conversation_`` ...) を見て分類する
- 個別の tool name にも上書き可能 (例: ``travel_to`` は MOVEMENT、
  ``interact`` は INTERACTION)
- 未知のツールは ``IntentPhase.OTHER`` にフォールバック (BC で error にしない
  ことで新ツールの増設が容易)

PR-CC (Y_after_pr639_640 後続): ``spot_graph_`` prefix を廃止したため、
spot_graph 系の tool は各個別マッピング (``interact`` / ``explore`` /
``travel_to`` など) で分類する。prefix loop からは削除。
"""

from __future__ import annotations

import logging

from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_PREFIX_COMBAT,
    TOOL_NAME_PREFIX_CONVERSATION,
    TOOL_NAME_PREFIX_MOVE,
    TOOL_NAME_PREFIX_SPEECH,
)
from ai_rpg_world.domain.intent.value_object.intent_phase import IntentPhase

logger = logging.getLogger(__name__)

# 具体的なツール名 → フェーズ (prefix より優先)
_EXPLICIT_TOOL_PHASE: dict[str, IntentPhase] = {
    "travel_to": IntentPhase.MOVEMENT,
    "interact": IntentPhase.INTERACTION,
    "explore": IntentPhase.INTERACTION,
    "set_sub_location": IntentPhase.MOVEMENT,
    "wait": IntentPhase.OTHER,
    "listen": IntentPhase.INTERACTION,
    "say": IntentPhase.SOCIAL,
    "whisper": IntentPhase.SOCIAL,
    # PR-CC: 旧 spot_graph_ prefix 廃止に伴い、spot_graph 系 tool の
    # phase を個別に明示する (prefix loop に依存できないため)。
    "attack": IntentPhase.ATTACK,
    "use_item": IntentPhase.INTERACTION,
    "drop_item": IntentPhase.INTERACTION,
    "pickup_item": IntentPhase.INTERACTION,
    "give_item": IntentPhase.SOCIAL,
    "give_items": IntentPhase.SOCIAL,
    "tend_to_player": IntentPhase.SOCIAL,
    "prepare_action": IntentPhase.INTERACTION,
}

# prefix → フェーズ (汎用フォールバック)。
# PR-CC (Y_after_pr639_640 後続): ``spot_graph_`` prefix は空文字化されたため
# loop から除外 (空 prefix は startswith で全マッチしてしまうため危険)。
# spot_graph 系 tool の phase 分類は _EXPLICIT_TOOL_PHASE で個別に持つ。
# attack は _EXPLICIT_TOOL_PHASE に追加した。
_PREFIX_PHASE: tuple[tuple[str, IntentPhase], ...] = (
    (TOOL_NAME_PREFIX_MOVE, IntentPhase.MOVEMENT),
    (TOOL_NAME_PREFIX_COMBAT, IntentPhase.ATTACK),
    (TOOL_NAME_PREFIX_SPEECH, IntentPhase.SOCIAL),
    (TOOL_NAME_PREFIX_CONVERSATION, IntentPhase.SOCIAL),
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
