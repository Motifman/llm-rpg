from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.being.contract import Description, Orientation
from ai_rpg_world.game_world.domain.declaration.world_introduction import WorldIntroduction
from ai_rpg_world.game_world.domain.exception.briefing_headings_exception import (
    MalformedBriefingHeadingException,
    RepeatedBriefingHeadingException,
)
from ai_rpg_world.game_world.domain.value_object import DescriptionText


@final
@dataclass(frozen=True)
class BriefingHeadings:
    introduction: str
    premises: str
    known_facts: str
    world_map: str

    def __post_init__(self) -> None:
        headings = (self.introduction, self.premises, self.known_facts, self.world_map)
        for heading in headings:
            if not isinstance(heading, str) or not heading.strip() or any(c in heading for c in "【】\n"):
                raise MalformedBriefingHeadingException(
                    f"briefing heading must be a non-blank single line without 【】, got {heading!r}"
                )
        if len(set(headings)) != len(headings):
            raise RepeatedBriefingHeadingException(f"briefing headings must differ, got {headings!r}")

    def orientation(
        self, introduction: WorldIntroduction, known_facts: DescriptionText, world_map: str | None
    ) -> Orientation:
        return Orientation(
            (
                Description(heading=self.introduction, text=introduction.text.text),
                Description(heading=self.premises, text=introduction.premises.text),
                *(() if world_map is None else (Description(heading=self.world_map, text=world_map),)),
                Description(heading=self.known_facts, text=known_facts.text),
            )
        )
