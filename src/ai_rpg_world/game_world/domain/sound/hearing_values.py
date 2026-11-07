from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import final

from ai_rpg_world.game_world.domain.exception.sound_exception import (
    HearingBoundariesOutOfOrderException,
    MissingLoudnessLevelException,
)
from ai_rpg_world.game_world.domain.sound.hearing_quality import (
    HearingQuality,
    HearsClearly,
    HearsFaintly,
    HearsMuffled,
    HearsNothing,
)
from ai_rpg_world.game_world.domain.sound.loudness import Loudness
from ai_rpg_world.game_world.domain.sound.sound_level import SoundLevel, SoundLoss
from ai_rpg_world.game_world.domain.sound.sound_network import NotReached


@final
@dataclass(frozen=True)
class HearingValues:
    loudness: Mapping[Loudness, SoundLevel]
    loss_per_passage: SoundLoss
    clear_from: SoundLevel
    muffled_from: SoundLevel
    faint_from: SoundLevel
    attentive_allowance: SoundLoss

    def __post_init__(self) -> None:
        missing = [loudness.name for loudness in Loudness if loudness not in self.loudness]
        if missing:
            raise MissingLoudnessLevelException(f"HearingValues.loudness lacks {missing}")
        if self.clear_from.is_below(self.muffled_from) or self.muffled_from.is_below(self.faint_from):
            raise HearingBoundariesOutOfOrderException(
                "HearingValues boundaries must satisfy clear_from >= muffled_from >= faint_from, "
                f"got {self.clear_from.value}, {self.muffled_from.value}, {self.faint_from.value}"
            )
        object.__setattr__(self, "loudness", MappingProxyType(dict(self.loudness)))

    def level_of(self, loudness: Loudness) -> SoundLevel:
        return self.loudness[loudness]

    def quietest_audible(self) -> SoundLevel:
        return self.faint_from.weakened_by(self.attentive_allowance)

    def quality(self, level: SoundLevel | NotReached, attentive: bool) -> HearingQuality:
        if isinstance(level, NotReached):
            return HearsNothing()
        allowance = self.attentive_allowance if attentive else SoundLoss(0)
        if not level.is_below(self.clear_from.weakened_by(allowance)):
            return HearsClearly()
        if not level.is_below(self.muffled_from.weakened_by(allowance)):
            return HearsMuffled()
        if not level.is_below(self.faint_from.weakened_by(allowance)):
            return HearsFaintly()
        return HearsNothing()
