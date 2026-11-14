from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.value_object import PassageId, SpotId, SpotSectionId, Ticks
from ai_rpg_world.game_world.domain.whereabouts import (
    AtSpot,
    DepartedPerson,
    Occupant,
    OccupantLocation,
    OpenArea,
    PersonBody,
    TravelPosition,
    WhereaboutsMemento,
)
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    JsonUnion,
    JsonUnionMember,
    distinct_items,
    exact_fields,
    json_int,
    json_str,
    ordered_items,
    person_id_from_json,
    world_id_from_json,
)


def _spot_id_from_json(raw: object) -> SpotId:
    return SpotId(json_str(raw))


_OCCUPANT: JsonUnion[Occupant] = JsonUnion(
    JsonUnionMember(
        "person_body",
        PersonBody,
        lambda body: {"person": body.person.value},
        lambda raw: PersonBody(person_id_from_json(exact_fields(raw, ("person",))["person"])),
    ),
    JsonUnionMember(
        "departed_person",
        DepartedPerson,
        lambda departed: {"person": departed.person.value},
        lambda raw: DepartedPerson(person_id_from_json(exact_fields(raw, ("person",))["person"])),
    ),
)

_SECTION: JsonUnion[SpotSectionId | OpenArea] = JsonUnion(
    JsonUnionMember(
        "spot_section_id", SpotSectionId, lambda section: section.value, lambda raw: SpotSectionId(json_str(raw))
    ),
    JsonUnionMember.fieldless("open_area", OpenArea()),
)


def _at_spot_from_json(raw: object) -> AtSpot:
    fields = exact_fields(raw, ("spot", "section"))
    return AtSpot(spot=_spot_id_from_json(fields["spot"]), section=_SECTION.from_json(fields["section"]))


def _travel_position_to_json(position: TravelPosition) -> object:
    return {
        "route_start": position.route_start.value,
        "route_passages": [passage.value for passage in position.route_passages],
        "passage_index": position.passage_index,
        "ticks_left_on_passage": position.ticks_left_on_passage.value,
        "departed_from": position.departed_from.value,
    }


def _travel_position_from_json(raw: object) -> TravelPosition:
    fields = exact_fields(
        raw, ("route_start", "route_passages", "passage_index", "ticks_left_on_passage", "departed_from")
    )
    return TravelPosition(
        route_start=_spot_id_from_json(fields["route_start"]),
        route_passages=ordered_items(fields["route_passages"], lambda passage: PassageId(json_str(passage))),
        passage_index=json_int(fields["passage_index"]),
        ticks_left_on_passage=Ticks(json_int(fields["ticks_left_on_passage"])),
        departed_from=_spot_id_from_json(fields["departed_from"]),
    )


_LOCATION: JsonUnion[AtSpot | TravelPosition] = JsonUnion(
    JsonUnionMember(
        "at_spot",
        AtSpot,
        lambda at: {"spot": at.spot.value, "section": _SECTION.to_json(at.section)},
        _at_spot_from_json,
    ),
    JsonUnionMember("travel_position", TravelPosition, _travel_position_to_json, _travel_position_from_json),
)


def _occupant_location_from_json(raw: object) -> OccupantLocation:
    fields = exact_fields(raw, ("occupant", "location"))
    return OccupantLocation(_OCCUPANT.from_json(fields["occupant"]), _LOCATION.from_json(fields["location"]))


def _occupant_order(entry: OccupantLocation) -> tuple[str, str]:
    return (entry.occupant.person.value, type(entry.occupant).__name__)


@final
class WhereaboutsCodec:
    kind = "whereabouts"
    version = 1
    memento_type = WhereaboutsMemento

    def to_json(self, memento: WhereaboutsMemento) -> object:
        return {
            "world_id": memento.world_id.value,
            "locations": [
                {"occupant": _OCCUPANT.to_json(entry.occupant), "location": _LOCATION.to_json(entry.location)}
                for entry in sorted(memento.locations, key=_occupant_order)
            ],
        }

    def from_json(self, raw: object) -> WhereaboutsMemento:
        fields = exact_fields(raw, ("world_id", "locations"))
        return WhereaboutsMemento(
            world_id=world_id_from_json(fields["world_id"]),
            locations=distinct_items(fields["locations"], _occupant_location_from_json),
        )
