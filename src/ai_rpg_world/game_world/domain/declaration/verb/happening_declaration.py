from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.action.refusal_code import NoRefusal, RefusalCode
from ai_rpg_world.game_world.domain.condition.condition import Condition
from ai_rpg_world.game_world.domain.declaration.verb.happening_notice import HappeningNotice, NoNotice
from ai_rpg_world.game_world.domain.effect.effect import Effect
from ai_rpg_world.game_world.domain.perception import Stimulus
from ai_rpg_world.game_world.domain.perception.people_present import PeopleWhoWereThere
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId


@final
@dataclass(frozen=True)
class HappeningDeclaration:
    happening_id: HappeningId
    condition: Condition
    effect: Effect
    once: bool
    notice: HappeningNotice | NoNotice

    def stimuli_when_fired(
        self,
        refusal: RefusalCode | NoRefusal,
        audience: frozenset[PersonId],
        present: PeopleWhoWereThere,
        at: WorldTick,
    ) -> tuple[Stimulus, ...]:
        # 断られた発火は巻き戻っていて、世界では何も起きていない。
        if isinstance(refusal, RefusalCode):
            return ()
        return self.notice.stimuli(audience, present, at)
