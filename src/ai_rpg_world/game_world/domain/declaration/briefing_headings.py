from __future__ import annotations

from dataclasses import dataclass
from string import Formatter
from typing import final

from ai_rpg_world.being.contract import Description, Orientation
from ai_rpg_world.game_world.domain.declaration.world_introduction import WorldIntroduction
from ai_rpg_world.game_world.domain.exception.briefing_headings_exception import (
    MalformedBriefingHeadingException,
)
from ai_rpg_world.game_world.domain.value_object import DescriptionText

_LINE_NAMES = {"title": ("title",), "overview": ("text",)}


@final
@dataclass(frozen=True)
class BriefingHeadings:
    premises: str
    title: str
    overview: str
    world_map: str
    deadline: str
    rules: str
    rule_lines: tuple[str, ...]

    def __post_init__(self) -> None:
        for heading in (self.premises, self.rules):
            if not isinstance(heading, str) or not heading.strip() or any(c in heading for c in "【】\n"):
                raise MalformedBriefingHeadingException(
                    f"briefing heading must be a non-blank single line without 【】, got {heading!r}"
                )
        if not self.rule_lines or any("\n" in line for line in self.rule_lines):
            raise MalformedBriefingHeadingException(
                f"BriefingHeadings.rule_lines must be single lines, at least one, got {self.rule_lines!r}"
            )
        for line in (self.world_map, self.deadline, *self.rule_lines):
            if not isinstance(line, str) or not line.strip():
                raise MalformedBriefingHeadingException(f"briefing line must not be blank, got {line!r}")
        # 埋める値を書き忘れた言い回しは、題名や概要が静かに消えるので、読み込みで断る
        for field_name, names in _LINE_NAMES.items():
            text = getattr(self, field_name)
            try:
                written = {name for _, name, _, _ in Formatter().parse(text) if name is not None}
            except ValueError as error:
                raise MalformedBriefingHeadingException(f"BriefingHeadings.{field_name} cannot be read") from error
            if written != set(names):
                raise MalformedBriefingHeadingException(
                    f"BriefingHeadings.{field_name} must write exactly {list(names)}, got {text!r}"
                )

    def orientation(self, introduction: WorldIntroduction, world_map: str | None, has_deadline: bool) -> Orientation:
        lines = [
            self.title.format(title=introduction.title.text),
            self.overview.format(text=introduction.text.text),
            *(() if introduction.premises is None else introduction.premises.text.splitlines()),
        ]
        if world_map is not None:
            lines += ["", self.world_map, world_map]
        if has_deadline:
            lines.append(self.deadline)
        return Orientation(
            (
                Description(heading=self.premises, text="\n".join(lines)),
                Description(heading=self.rules, text="\n".join(self.rule_lines)),
            )
        )
