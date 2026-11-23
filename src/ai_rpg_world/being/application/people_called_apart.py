"""1 ターンに出てくる人を、重ならない呼び方で呼び分ける。"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from ai_rpg_world.being.contract import PersonInText, PersonPlaceholderValue


class PeopleCalledApart:
    """呼び方が重なった人にだけ、人の印の小さい順に「 #1」「 #2」を添える。

    印の順にするのは、同じ顔ぶれならターンが変わっても同じ人に同じ番号が付くようにするため。
    """

    def __init__(self, name_for: Callable[[PersonPlaceholderValue], str], people: Iterable[PersonInText]) -> None:
        self._name_for = name_for
        by_handle = {person.handle: person for person in people}
        called: dict[str, list[PersonInText]] = {}
        for person in sorted(by_handle.values(), key=lambda p: p.handle):
            called.setdefault(name_for(person), []).append(person)
        self._names: dict[int, str] = {}
        for name, same in called.items():
            for number, person in enumerate(same, start=1):
                self._names[person.handle] = name if len(same) == 1 else f"{name} #{number}"
        self._people = {self._names[handle]: person for handle, person in by_handle.items()}

    def name_of(self, person: PersonInText) -> str:
        return self._names[person.handle]

    def called(self, person: PersonPlaceholderValue) -> str:
        """理由の文にだけ出る人は、番号を付けずに呼ぶ。表に出ない人に番号を付けると、表の人と取り違える。"""
        if isinstance(person, PersonInText) and person.handle in self._names:
            return self._names[person.handle]
        return self._name_for(person)

    def person_named(self, name: str) -> PersonInText | None:
        return self._people.get(name)


__all__ = ["PeopleCalledApart"]
