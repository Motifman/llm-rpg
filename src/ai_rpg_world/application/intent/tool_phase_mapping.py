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
    # PR-DD (Y_after_pr639_640): speech_speak → speak にリネームされた
    # 統合発話 tool。channel 引数で whisper/say/shout を選ぶ。
    "speak": IntentPhase.SOCIAL,
    # PR-CC: 旧 spot_graph_ prefix 廃止に伴い、spot_graph 系 tool の
    # phase を個別に明示する (prefix loop に依存できないため)。
    "attack": IntentPhase.ATTACK,
    "use_item": IntentPhase.INTERACTION,
    "drop_item": IntentPhase.INTERACTION,
    "pickup_item": IntentPhase.INTERACTION,
    "give_item": IntentPhase.SOCIAL,
    # PR-α (Y_after_pr639_640 後続): 旧 give_items は give_item に統合
    # (batch-always)。dict の dead entry は残さない。
    "tend_to_player": IntentPhase.SOCIAL,
    # 投票は「誰を追放するか」を全員で決める行為。移動や採取ではなく、
    # 他者との関係を動かす手なので SOCIAL に置く。
    "vote": IntentPhase.SOCIAL,
    "report_body": IntentPhase.SOCIAL,
    "prepare_action": IntentPhase.INTERACTION,
    # 商人との売買は NPC 相手のやり取りで、他のエージェントとの関係を動かす
    # 行為ではない。物と金が動く操作なので、拾う・置くと同じ INTERACTION に
    # 置く (give_item を SOCIAL にしたのは相手が同席のエージェントだから)。
    "buy_item": IntentPhase.INTERACTION,
    "sell_item": IntentPhase.INTERACTION,
    # 人同士の取引は SOCIAL。相手はエージェントで、持ちかける・受ける・断るは
    # 関係を動かす行為 (give_item を SOCIAL にしたのと同じ理由)。NPC 商人との
    # 売買を INTERACTION にしたのは、相手が関係を持たない存在だから。
    "trade_offer": IntentPhase.SOCIAL,
    # 市場は「品と金を動かす」ので、売買と同じ INTERACTION に置く。板越しでも
    # 相手が要る点は取引に近いが、同席した誰かへの働きかけではない。
    "market_view": IntentPhase.INTERACTION,
    "market_list_item": IntentPhase.INTERACTION,
    "market_buy": IntentPhase.INTERACTION,
    "market_reprice": IntentPhase.INTERACTION,
    "market_cancel": IntentPhase.INTERACTION,
    "market_bid": IntentPhase.INTERACTION,
    "market_sell": IntentPhase.INTERACTION,
    "trade_accept": IntentPhase.SOCIAL,
    "trade_decline": IntentPhase.SOCIAL,
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
