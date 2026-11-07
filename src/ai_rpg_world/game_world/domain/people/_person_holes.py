from __future__ import annotations

from string import Formatter

from ai_rpg_world.game_world.domain.exception.people_exception import MalformedTemplateException


def person_holes_in(template: str) -> frozenset[str]:
    try:
        parsed = list(Formatter().parse(template))
    except ValueError as error:
        raise MalformedTemplateException(f"unbalanced braces in {template!r}") from error
    holes: set[str] = set()
    rebuilt: list[str] = []
    for literal, field_name, _, _ in parsed:
        rebuilt.append(literal.replace("{", "{{").replace("}", "}}"))
        if field_name is None:
            continue
        # 穴は人を名前で置くだけにする。書式や属性を許すと、文が人の中身 (名前など) を読みに行けてしまう。
        if not field_name.isidentifier():
            raise MalformedTemplateException(f"hole {{{field_name}}} in {template!r} is not a named person hole")
        rebuilt.append(f"{{{field_name}}}")
        holes.add(field_name)
    # parse は空の書式指定 ({actor:}) を書式指定なしと区別しないので、組み直して元の文と比べる。
    if "".join(rebuilt) != template:
        raise MalformedTemplateException(f"{template!r} has a hole with a conversion or format spec")
    return frozenset(holes)
