"""
LLM ツール名のプレフィックスとツール名定数。

ツール名は「カテゴリプレフィックス_機能名」の形式とし、
利用可能ツール一覧でカテゴリが分かるようにする。
"""

from typing import List, Tuple

# --- プレフィックス一覧（カテゴリ） ---
TOOL_NAME_PREFIX_WORLD = "world_"
TOOL_NAME_PREFIX_MOVE = "move_"
TOOL_NAME_PREFIX_SPEECH = "speech_"
TOOL_NAME_PREFIX_HARVEST = "harvest_"
TOOL_NAME_PREFIX_CONVERSATION = "conversation_"
TOOL_NAME_PREFIX_COMBAT = "combat_"

# プレフィックス一覧（ドキュメント・バリデーション用）。順序は表示に影響しない。
TOOL_NAME_PREFIXES: List[str] = [
    TOOL_NAME_PREFIX_WORLD,
    TOOL_NAME_PREFIX_MOVE,
    TOOL_NAME_PREFIX_SPEECH,
    TOOL_NAME_PREFIX_HARVEST,
    TOOL_NAME_PREFIX_CONVERSATION,
    TOOL_NAME_PREFIX_COMBAT,
]

# プレフィックスと説明の対応（ドキュメント用）
TOOL_NAME_PREFIX_DESCRIPTIONS: List[Tuple[str, str]] = [
    (TOOL_NAME_PREFIX_WORLD, "ワールド・ゲーム全体"),
    (TOOL_NAME_PREFIX_MOVE, "移動"),
    (TOOL_NAME_PREFIX_SPEECH, "会話・発言"),
    (TOOL_NAME_PREFIX_HARVEST, "採集"),
    (TOOL_NAME_PREFIX_CONVERSATION, "会話進行"),
    (TOOL_NAME_PREFIX_COMBAT, "戦闘"),
]

# --- ツール名（プレフィックス付き） ---
TOOL_NAME_NO_OP = TOOL_NAME_PREFIX_WORLD + "no_op"
TOOL_NAME_INTERACT_WORLD_OBJECT = TOOL_NAME_PREFIX_WORLD + "interact"
TOOL_NAME_CHANGE_ATTENTION = TOOL_NAME_PREFIX_WORLD + "change_attention"
TOOL_NAME_PLACE_OBJECT = TOOL_NAME_PREFIX_WORLD + "place_object"
TOOL_NAME_DESTROY_PLACEABLE = TOOL_NAME_PREFIX_WORLD + "destroy_placeable"
# 移動は 1 ツール（set_destination と tick_movement を分けない）。内部で SetDestinationCommand を使用。
TOOL_NAME_MOVE_TO_DESTINATION = TOOL_NAME_PREFIX_MOVE + "to_destination"
TOOL_NAME_WHISPER = TOOL_NAME_PREFIX_SPEECH + "whisper"
TOOL_NAME_SAY = TOOL_NAME_PREFIX_SPEECH + "say"
TOOL_NAME_HARVEST_START = TOOL_NAME_PREFIX_HARVEST + "start"
TOOL_NAME_CONVERSATION_ADVANCE = TOOL_NAME_PREFIX_CONVERSATION + "advance"
TOOL_NAME_CHEST_STORE = TOOL_NAME_PREFIX_WORLD + "chest_store"
TOOL_NAME_CHEST_TAKE = TOOL_NAME_PREFIX_WORLD + "chest_take"
TOOL_NAME_COMBAT_USE_SKILL = TOOL_NAME_PREFIX_COMBAT + "use_skill"
