from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.object_and_item.object_declaration import (
    ObjectAppearance,
    ObjectDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.spot import (
    NoAmbientSound,
    NoCapacity,
    NoSmell,
    PassageDeclaration,
    SpotAtmosphere,
    SpotDeclaration,
    SpotSectionDeclaration,
    Temperature,
)
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import NoVisibleName, PersonHandle, PersonRef
from ai_rpg_world.game_world.domain.perception.surroundings import (
    ContainedObject,
    ContainedPassage,
    PresentPerson,
    SpotContents,
)
from ai_rpg_world.game_world.domain.value_object import (
    DescriptionText,
    DisplayName,
    ObjectId,
    PassageId,
    PassageStateName,
    SpotId,
    SpotSectionId,
    Ticks,
)
from ai_rpg_world.game_world.domain.whereabouts.location import OpenArea
from ai_rpg_world.game_world.domain.whereabouts.passage_in_state import PassageInState
from tests.game_world.support.declarations_for_tests import OPEN as OPEN_STATE
from tests.game_world.support.declarations_for_tests import open_passage_states

HERE = "mine_depths"


def spot(name: str = HERE) -> SpotDeclaration:
    return SpotDeclaration(
        spot_id=SpotId(name),
        name=DisplayName(name),
        description=DescriptionText(f"{name} の説明"),
        atmosphere=SpotAtmosphere(
            lighting=Lighting.BRIGHT,
            outdoor=False,
            temperature=Temperature.NORMAL,
            ambient_sound=NoAmbientSound(),
            smell=NoSmell(),
        ),
    )


def passage(name: str, *, to: str = "mine_entrance", at: str = HERE, revealed: bool = True) -> ContainedPassage:
    declaration = PassageDeclaration(
        passage_id=PassageId(name),
        name=DisplayName(f"{name} の通路"),
        description=DescriptionText(f"{name} の様子"),
        ends=(SpotId(at), SpotId(to)),
        two_way=True,
        travel_ticks=Ticks(1),
        states=open_passage_states(),
        initial_state=OPEN_STATE,
        hidden_until_revealed=not revealed,
    )
    return ContainedPassage(passage=PassageInState(declaration, PassageStateName("open")), revealed=revealed)


def thing(name: str, *, seen_in_dark: bool = False, revealed: bool = True, at: str = HERE) -> ContainedObject:
    declaration = ObjectDeclaration(
        object_id=ObjectId(name),
        spot_id=SpotId(at),
        name=DisplayName(name),
        description=DescriptionText(f"{name} の説明"),
        appearance=ObjectAppearance(seen_in_dark=seen_in_dark, hidden_until_revealed=not revealed),
        state_keys=(),
    )
    return ContainedObject(declaration=declaration, revealed=revealed)


def section(name: str, *, at: str = HERE) -> SpotSectionDeclaration:
    return SpotSectionDeclaration(
        section_id=SpotSectionId(name),
        spot_id=SpotId(at),
        name=DisplayName(name),
        capacity=NoCapacity(),
        reachable_objects=(),
    )


def item(name: str) -> ItemInstanceId:
    return ItemInstanceId(name)


def person(
    handle: int,
    *,
    held: tuple[ItemInstanceId, ...] = (),
    carried: tuple[ItemInstanceId, ...] = (),
    section: SpotSectionId | OpenArea = OpenArea(),
) -> PresentPerson:
    return PresentPerson(
        person=PersonRef(
            handle=PersonHandle(handle),
            appearance=DescriptionText(f"{handle} 番の見た目"),
            visible_name=NoVisibleName(),
        ),
        section=section,
        held_items=held,
        all_items=held + carried,
    )


def contents(
    *,
    passages: tuple[ContainedPassage, ...] = (),
    sections: tuple[SpotSectionDeclaration, ...] = (),
    objects: tuple[ContainedObject, ...] = (),
    ground_items: tuple[ItemInstanceId, ...] = (),
    people: tuple[PresentPerson, ...] = (),
    bodies: tuple[PresentPerson, ...] = (),
) -> SpotContents:
    return SpotContents(
        spot=spot(),
        passages=passages,
        sections=sections,
        objects=objects,
        ground_items=ground_items,
        people=people,
        bodies=bodies,
    )
