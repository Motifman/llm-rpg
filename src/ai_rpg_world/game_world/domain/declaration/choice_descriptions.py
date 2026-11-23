from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from string import Formatter
from types import MappingProxyType
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.action.offered_action import ActionChoiceKind
from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.time_and_weather import DayNightDeclaration, NoDayNight
    from ai_rpg_world.game_world.domain.rules.world_rules import WorldRules

_TEND_NAMES = frozenset({"revive_percent", "death_after"})


def _names_in(text: str) -> frozenset[str]:
    try:
        return frozenset(name for _, name, _, _ in Formatter().parse(text) if name is not None)
    except ValueError as error:
        raise ValueOutOfRangeException(f"ChoiceDescriptions cannot read {text!r}") from error


@final
@dataclass(frozen=True)
class ChoiceDescriptions:
    by_choice: Mapping[str, str]
    tend_without_tending: str
    duration_hours: str
    duration_minutes: str
    duration_turns: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "by_choice", MappingProxyType(dict(self.by_choice)))
        expected = {kind.choice_name for kind in ActionChoiceKind}
        if set(self.by_choice) != expected:
            raise ValueOutOfRangeException(
                f"ChoiceDescriptions must describe exactly {sorted(expected)}, got {sorted(self.by_choice)}"
            )
        # Being は説明のすぐ後に引数の書き方の一文をつなぐので、説明は文で終わらせる
        for name, text in self.by_choice.items():
            allowed = _TEND_NAMES if name == ActionChoiceKind.TEND_TO_PLAYER.choice_name else frozenset()
            if not text.endswith("。") or _names_in(text) != allowed:
                raise ValueOutOfRangeException(
                    f"ChoiceDescriptions.{name} must write exactly {sorted(allowed)}, got {text!r}"
                )
        if not self.tend_without_tending.endswith("。") or _names_in(self.tend_without_tending):
            raise ValueOutOfRangeException(
                f"ChoiceDescriptions.tend_without_tending must end a sentence, got {self.tend_without_tending!r}"
            )
        for name, text, names in (
            ("duration_hours", self.duration_hours, frozenset({"hours"})),
            ("duration_minutes", self.duration_minutes, frozenset({"minutes"})),
            ("duration_turns", self.duration_turns, frozenset({"turns"})),
        ):
            if not text.strip() or _names_in(text) != names:
                raise ValueOutOfRangeException(
                    f"ChoiceDescriptions.{name} must write exactly {sorted(names)}, got {text!r}"
                )

    def description_of(
        self, kind: ActionChoiceKind, rules: WorldRules, day_night: DayNightDeclaration | NoDayNight
    ) -> str:
        if kind is ActionChoiceKind.TEND_TO_PLAYER:
            return rules.tend.described_with(self, day_night.rough_duration_text(rules.death.grace, self))
        return self.by_choice[kind.choice_name]

    def tending(self, revive_percent: int, death_after: str) -> str:
        return self.by_choice[ActionChoiceKind.TEND_TO_PLAYER.choice_name].format(
            revive_percent=revive_percent, death_after=death_after
        )
