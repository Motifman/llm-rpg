from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.people.person_handle import PersonHandle
from ai_rpg_world.game_world.domain.people.person_ref import NoVisibleName, PersonRef, Unidentified
from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName
from ai_rpg_world.game_world.domain.world_records import MissedNoticesMemento
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    JsonUnion,
    JsonUnionMember,
    exact_fields,
    json_int,
    json_str,
    keyed_items,
    ordered_items,
    person_id_from_json,
    world_tick_from_json,
)

_VISIBLE_NAME: JsonUnion[DisplayName | NoVisibleName] = JsonUnion(
    JsonUnionMember("display_name", DisplayName, lambda name: name.text, lambda raw: DisplayName(json_str(raw))),
    JsonUnionMember.fieldless("no_visible_name", NoVisibleName()),
)


def _person_ref_to_json(ref: PersonRef) -> object:
    return {
        "handle": ref.handle.value,
        "appearance": ref.appearance.text,
        "visible_name": _VISIBLE_NAME.to_json(ref.visible_name),
    }


def _person_ref_from_json(raw: object) -> PersonRef:
    fields = exact_fields(raw, ("handle", "appearance", "visible_name"))
    return PersonRef(
        handle=PersonHandle(json_int(fields["handle"])),
        appearance=DescriptionText(json_str(fields["appearance"])),
        visible_name=_VISIBLE_NAME.from_json(fields["visible_name"]),
    )


_PERSON: JsonUnion[PersonRef | Unidentified] = JsonUnion(
    JsonUnionMember("person_ref", PersonRef, _person_ref_to_json, _person_ref_from_json),
    JsonUnionMember.fieldless("unidentified", Unidentified()),
)


def _notice_to_json(notice: MissedNotice) -> object:
    return {
        "text": {
            "template": notice.text.template,
            "people": {placeholder: _PERSON.to_json(person) for placeholder, person in notice.text.people.items()},
        },
        "happened_at": notice.happened_at.value,
    }


def _notice_from_json(raw: object) -> MissedNotice:
    fields = exact_fields(raw, ("text", "happened_at"))
    text = exact_fields(fields["text"], ("template", "people"))
    return MissedNotice(
        text=TextWithAssignedPeople(
            template=json_str(text["template"]),
            people=keyed_items(text["people"], str, _PERSON.from_json),
        ),
        happened_at=world_tick_from_json(fields["happened_at"]),
    )


@final
class MissedNoticesCodec:
    kind = "missed_notices"
    version = 1
    memento_type = MissedNoticesMemento

    def to_json(self, memento: MissedNoticesMemento) -> object:
        return {"person": memento.person.value, "notices": [_notice_to_json(notice) for notice in memento.notices]}

    def from_json(self, raw: object) -> MissedNoticesMemento:
        fields = exact_fields(raw, ("person", "notices"))
        return MissedNoticesMemento(
            person=person_id_from_json(fields["person"]),
            notices=ordered_items(fields["notices"], _notice_from_json),
        )
