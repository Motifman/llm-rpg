"""[PR #450 移動済] 後方互換 shim。実体は
``ai_rpg_world.application.escape_game.pipeline_event_publisher``。
"""

from __future__ import annotations

from ai_rpg_world.application.escape_game.pipeline_event_publisher import *  # noqa: F401, F403
