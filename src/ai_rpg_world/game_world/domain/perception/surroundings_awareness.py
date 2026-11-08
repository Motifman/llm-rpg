from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.not_noticed_later import NotNoticedLater
from ai_rpg_world.game_world.domain.perception.perception_outcome import NoticedLater, NotPerceived, PerceptionOutcome

# 気づかない人のために偶然を引いたり文を組んだりしないよう、結果は呼ぶまで作らない。
OutcomeWhenAware = Callable[[], PerceptionOutcome]
NoticeOnWaking = Callable[[], MissedNotice | NotNoticedLater]


@final
@dataclass(frozen=True)
class Aware:
    def outcome(self, when_aware: OutcomeWhenAware, on_waking: NoticeOnWaking) -> PerceptionOutcome:
        return when_aware()


@final
@dataclass(frozen=True)
class AwareOnWaking:
    def outcome(self, when_aware: OutcomeWhenAware, on_waking: NoticeOnWaking) -> PerceptionOutcome:
        notice = on_waking()
        if isinstance(notice, NotNoticedLater):
            return NotPerceived()
        return NoticedLater(notice=notice)


@final
@dataclass(frozen=True)
class Unaware:
    def outcome(self, when_aware: OutcomeWhenAware, on_waking: NoticeOnWaking) -> PerceptionOutcome:
        return NotPerceived()


SurroundingsAwareness = Aware | AwareOnWaking | Unaware
