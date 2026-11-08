from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.design_flaw import DesignLocation

_WORLD = "world"

_NAMED_AT_TOP = {
    "flags": "flag",
    "spots": "spot",
    "passages": "passage",
    "item_specs": "item_spec",
    "groupings": "grouping",
    "characters": "character",
    "world_stages": "world_stage",
    "group_decisions": "group_decision",
    "outcomes": "outcome",
    "happenings": "happening",
    "reactions": "reaction",
    "joint_actions": "joint_action",
    "person_interactions": "person_interaction",
}

_NAMED_INSIDE = {
    "spot": {"sections": "section", "objects": "object", "discoverables": "discoverable"},
    "grouping": {"groups": "group"},
}

Step = str | int


@final
@dataclass(frozen=True)
class YamlPath:
    steps: tuple[Step, ...]

    @classmethod
    def root(cls) -> YamlPath:
        return cls(())

    def __truediv__(self, step: Step) -> YamlPath:
        return YamlPath((*self.steps, step))

    def location(self) -> DesignLocation:
        steps = list(self.steps)
        if len(steps) < 2 or steps[0] not in _NAMED_AT_TOP:
            return DesignLocation(_WORLD, _WORLD, _field(steps))
        kind, name, rest = _NAMED_AT_TOP[str(steps[0])], str(steps[1]), steps[2:]
        while len(rest) >= 2 and rest[0] in _NAMED_INSIDE.get(kind, {}):
            kind, name, rest = _NAMED_INSIDE[kind][str(rest[0])], str(rest[1]), rest[2:]
        return DesignLocation(kind, name, _field(rest))


def _field(steps: list[Step]) -> str:
    written = ""
    for step in steps:
        if isinstance(step, int):
            written += f"[{step}]"
        else:
            written += f".{step}" if written else step
    return written
