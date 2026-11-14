from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.action.action_refusal import ActionRefusal


@final
@dataclass(frozen=True)
class ActionDone:
    pass


@final
@dataclass(frozen=True)
class ActionRefused:
    refusal: ActionRefusal


ActionReply = ActionDone | ActionRefused
