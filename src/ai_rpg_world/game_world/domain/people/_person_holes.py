from __future__ import annotations

from string import Formatter

from ai_rpg_world.game_world.domain.exception.people_exception import MalformedTemplateException


def person_holes_in(template: str) -> frozenset[str]:
    try:
        parsed = list(Formatter().parse(template))
    except ValueError as error:
        raise MalformedTemplateException(f"unbalanced braces in {template!r}") from error
    holes: set[str] = set()
    for _, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        # 穴は人を名前で置くだけにする。書式や属性を許すと、文が人の中身 (名前など) を読みに行けてしまう。
        if not field_name.isidentifier() or format_spec or conversion is not None:
            raise MalformedTemplateException(f"hole {{{field_name}}} in {template!r} is not a named person hole")
        holes.add(field_name)
    return frozenset(holes)
