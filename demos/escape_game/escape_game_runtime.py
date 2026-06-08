"""[PR #450 移動済] 後方互換 shim。実体は ``ai_rpg_world.application.escape_game.escape_game_runtime``。

# 何のため

architect レビュー (PR #444 後) で指摘: ``demos/escape_game/escape_game_runtime.py``
は実際には ``presentation/spot_graph_game/runtime_manager`` から import される
**本流の runtime** で、demo ではなかった。「demo を本流が踏む」倒錯が、PR #439
や PR #446 の config-init split silent failure を生む土壌になっていた。

PR #450 で実体を ``src/ai_rpg_world/application/escape_game/`` に移動。本 file は
**既存の 32 か所の import を即時破壊しない** ための shim として残置する。
新規 import は移動先 (``ai_rpg_world.application.escape_game.escape_game_runtime``)
を直接使うこと。

# 廃止予定

PR 6/6 (Builder pattern) で shim を含めて削除予定。
"""

from __future__ import annotations

from ai_rpg_world.application.escape_game.escape_game_runtime import *  # noqa: F401, F403

# 明示的に re-export しておくと、type checker / IDE が補完しやすい。
# 新規追加された名前は ``from ...escape_game_runtime import *`` で自動的に
# 拾われるが、よく使う名前は読みやすさのため明示する。
from ai_rpg_world.application.escape_game.escape_game_runtime import (  # noqa: F401
    EscapeGameRuntime,
    create_escape_game_runtime,
)
