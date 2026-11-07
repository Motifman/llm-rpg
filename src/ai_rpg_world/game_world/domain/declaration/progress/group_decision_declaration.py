from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.value_object import DisplayName, GroupDecisionId


@final
@dataclass(frozen=True)
class GroupDecisionDeclaration:
    decision_id: GroupDecisionId
    name: DisplayName
    abstain_allowed: bool
    reveals_ballots: bool
