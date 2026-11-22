from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import final

from ai_rpg_world.game_world.domain.exception.surroundings_texts_exception import BodyTierLadderException
from ai_rpg_world.game_world.domain.value_object import DisplayName, HitPoints


@final
@dataclass(frozen=True)
class NeedTier:
    from_percent: int
    name: DisplayName


@final
@dataclass(frozen=True)
class NeedTiers:
    tiers: tuple[NeedTier, ...]

    def __post_init__(self) -> None:
        starts = [tier.from_percent for tier in self.tiers]
        if not starts or starts[0] != 0:
            raise BodyTierLadderException(f"NeedTiers must start at 0 percent, got {starts}")
        if any(lower >= upper for lower, upper in pairwise(starts)) or starts[-1] >= 100:
            raise BodyTierLadderException(f"NeedTiers must rise below 100 percent, got {starts}")

    def name_of(self, amount: int, limit: int) -> DisplayName:
        return next(tier.name for tier in reversed(self.tiers) if amount * 100 >= tier.from_percent * limit)


@final
@dataclass(frozen=True)
class HitPointsTier:
    up_to_percent: int
    name: DisplayName


@final
@dataclass(frozen=True)
class HitPointsTiers:
    tiers: tuple[HitPointsTier, ...]

    def __post_init__(self) -> None:
        ends = [tier.up_to_percent for tier in self.tiers]
        if not ends or ends[-1] != 100:
            raise BodyTierLadderException(f"HitPointsTiers must end at 100 percent, got {ends}")
        if any(lower >= upper for lower, upper in pairwise(ends)) or ends[0] < 0:
            raise BodyTierLadderException(f"HitPointsTiers must rise from 0 percent, got {ends}")

    def name_of(self, hp: HitPoints) -> DisplayName:
        return next(tier.name for tier in self.tiers if hp.current * 100 <= tier.up_to_percent * hp.maximum)
