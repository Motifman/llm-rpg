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

# プレフィックス一覧（ドキュメント・バリデーション用）。順序は表示に影響しない。
TOOL_NAME_PREFIXES: List[str] = [
    TOOL_NAME_PREFIX_WORLD,
    TOOL_NAME_PREFIX_MOVE,
    TOOL_NAME_PREFIX_SPEECH,
]

# プレフィックスと説明の対応（ドキュメント用）
TOOL_NAME_PREFIX_DESCRIPTIONS: List[Tuple[str, str]] = [
    (TOOL_NAME_PREFIX_WORLD, "ワールド・ゲーム全体"),
    (TOOL_NAME_PREFIX_MOVE, "移動"),
    (TOOL_NAME_PREFIX_SPEECH, "会話・発言"),
]

# --- ツール名（プレフィックス付き） ---
TOOL_NAME_NO_OP = TOOL_NAME_PREFIX_WORLD + "no_op"
# 移動は 1 ツール（set_destination と tick_movement を分けない）。内部で SetDestinationCommand を使用。
TOOL_NAME_MOVE_TO_DESTINATION = TOOL_NAME_PREFIX_MOVE + "to_destination"
TOOL_NAME_WHISPER = TOOL_NAME_PREFIX_SPEECH + "whisper"
