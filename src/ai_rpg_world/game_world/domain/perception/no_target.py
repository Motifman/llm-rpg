from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.lighting.sight_quality import SightQuality
from ai_rpg_world.game_world.domain.rules.stealth_rule import StealthRule
from ai_rpg_world.game_world.domain.value_object import PersonId, Probability

if TYPE_CHECKING:
    # 実行時に import すると循環する。
    from ai_rpg_world.game_world.domain.perception.sight_stimulus import SightTexts


@final
@dataclass(frozen=True)
class NoTarget:
    def require_among(self, involved: tuple[PersonId, ...]) -> None:
        pass

    def texts_for(self, viewer: PersonId, witness: SightTexts) -> SightTexts:
        return witness

    def notice_chances_for(self, viewer: PersonId, stealth: StealthRule) -> Mapping[SightQuality, Probability]:
        return stealth.notice_by_bystander
