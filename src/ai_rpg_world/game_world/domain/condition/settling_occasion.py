from __future__ import annotations

from enum import Enum

from ai_rpg_world.game_world.domain.condition.condition import Condition


class SettlingOccasion(Enum):
    AFTER_WORLD_TIME_PASSED = "AFTER_WORLD_TIME_PASSED"
    AFTER_COMMAND = "AFTER_COMMAND"

    def checks(self, condition: Condition) -> bool:
        # コマンドのたびに偶然を確かめると 1 tick にくじを何度も引き、書いた確率より高くなる (#1978 の D2)
        return self is SettlingOccasion.AFTER_WORLD_TIME_PASSED or not condition.requirements().uses_chance
