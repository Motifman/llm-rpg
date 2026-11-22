"""環境が人の穴で渡した人を、Being が何と呼ぶか (D1928)。"""

from __future__ import annotations

from ai_rpg_world.being.contract import PersonInText, PersonPlaceholderValue, TextWithPeople

SOMEONE = "誰か"


def name_for(person: PersonPlaceholderValue) -> str:
    if not isinstance(person, PersonInText):
        return SOMEONE
    return person.visible_name or person.appearance


def text_naming_people(text: TextWithPeople) -> str:
    return text.template.format_map({key: name_for(person) for key, person in text.people.items()})


__all__ = ["SOMEONE", "name_for", "text_naming_people"]
