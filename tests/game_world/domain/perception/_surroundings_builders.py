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
from ai_rpg_world.game_world.domain.declaration.spot.passage_declaration import PassageStateDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_and_clock_time import DayAndClockTime
from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_phase_declaration import DayPhaseDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_type import WeatherType
from ai_rpg_world.game_world.domain.declaration.verb import NoLook
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import NoVisibleName, PersonHandle, PersonRef
from ai_rpg_world.game_world.domain.perception.scene_conditions import SceneConditions
from ai_rpg_world.game_world.domain.perception.surroundings import (
    ContainedObject,
    ContainedPassage,
    PersonCondition,
    PresentPerson,
    SeenObject,
    SpotContents,
    Up,
)
from ai_rpg_world.game_world.domain.sound.sound_level import SoundLoss
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


def passage(
    name: str,
    *,
    to: str = "mine_entrance",
    at: str = HERE,
    revealed: bool = True,
    state: str = "open",
    two_way: bool = True,
) -> ContainedPassage:
    declaration = PassageDeclaration(
        passage_id=PassageId(name),
        name=DisplayName(f"{name} の通路"),
        description=DescriptionText(f"{name} の様子"),
        ends=(SpotId(at), SpotId(to)),
        two_way=two_way,
        travel_ticks=Ticks(1),
        states=(
            *open_passage_states(),
            PassageStateDeclaration(
                name=PassageStateName("closed"),
                display_name=DisplayName("閉じている"),
                traversable=False,
                sound_loss=SoundLoss(0),
            ),
        ),
        initial_state=OPEN_STATE,
        hidden_until_revealed=not revealed,
    )
    return ContainedPassage(passage=PassageInState(declaration, PassageStateName(state)), revealed=revealed)


def thing(
    name: str,
    *,
    seen_in_dark: bool = False,
    revealed: bool = True,
    at: str = HERE,
    look: DescriptionText | NoLook = NoLook(),
) -> ContainedObject:
    declaration = ObjectDeclaration(
        object_id=ObjectId(name),
        spot_id=SpotId(at),
        name=DisplayName(name),
        description=DescriptionText(f"{name} の説明"),
        appearance=ObjectAppearance(seen_in_dark=seen_in_dark, hidden_until_revealed=not revealed),
        state_keys=(),
    )
    return ContainedObject(declaration=declaration, revealed=revealed, look=look)


def seen(contained: ContainedObject) -> SeenObject:
    return SeenObject(declaration=contained.declaration, look=contained.look)


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
    condition: PersonCondition = Up(looks=None),
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
        condition=condition,
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


def conditions(
    *,
    lighting: Lighting = Lighting.BRIGHT,
    weather: WeatherType | None = None,
    time: DayAndClockTime | None = None,
    phase: DayPhaseDeclaration | None = None,
) -> SceneConditions:
    return SceneConditions(atmosphere=spot().atmosphere, lighting=lighting, weather=weather, time=time, phase=phase)
