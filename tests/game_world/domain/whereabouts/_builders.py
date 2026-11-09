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
    PassageStateDeclaration,
    SpotAtmosphere,
    SpotDeclaration,
    SpotSectionDeclaration,
    Temperature,
)
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.sound import SoundLoss
from ai_rpg_world.game_world.domain.value_object import (
    Capacity,
    DescriptionText,
    DisplayName,
    ObjectId,
    PassageId,
    PassageStateName,
    SpotId,
    SpotSectionId,
    Ticks,
    WorldId,
)
from tests.game_world.support.declarations_for_tests import OPEN as OPEN_STATE
from tests.game_world.support.declarations_for_tests import open_passage_states

WORLD = WorldId("abandoned_mine_village")
OPEN = PassageStateName("open")
CLOSED = PassageStateName("closed")


def atmosphere(lighting: Lighting = Lighting.BRIGHT) -> SpotAtmosphere:
    return SpotAtmosphere(
        lighting=lighting,
        outdoor=False,
        temperature=Temperature.NORMAL,
        ambient_sound=NoAmbientSound(),
        smell=NoSmell(),
    )


def spot(name: str, lighting: Lighting = Lighting.BRIGHT) -> SpotDeclaration:
    return SpotDeclaration(
        spot_id=SpotId(name),
        name=DisplayName(name),
        description=DescriptionText(f"{name} の説明"),
        atmosphere=atmosphere(lighting),
    )


def path(
    name: str,
    a: str,
    b: str,
    *,
    ticks: int = 1,
    two_way: bool = True,
    hidden_until_revealed: bool = False,
) -> PassageDeclaration:
    return PassageDeclaration(
        passage_id=PassageId(name),
        name=DisplayName(f"{name} の通路"),
        description=DescriptionText(f"{name} の様子"),
        ends=(SpotId(a), SpotId(b)),
        two_way=two_way,
        travel_ticks=Ticks(ticks),
        states=open_passage_states(),
        initial_state=OPEN_STATE,
        hidden_until_revealed=hidden_until_revealed,
    )


def door(name: str, a: str, b: str, *, initial: PassageStateName = CLOSED, ticks: int = 1) -> PassageDeclaration:
    return PassageDeclaration(
        passage_id=PassageId(name),
        name=DisplayName(f"{name} の通路"),
        description=DescriptionText(f"{name} の様子"),
        ends=(SpotId(a), SpotId(b)),
        two_way=True,
        travel_ticks=Ticks(ticks),
        states=(
            PassageStateDeclaration(
                name=OPEN, display_name=DisplayName("開いている"), traversable=True, sound_loss=SoundLoss(0)
            ),
            PassageStateDeclaration(
                name=CLOSED, display_name=DisplayName("閉じている"), traversable=False, sound_loss=SoundLoss(20)
            ),
        ),
        initial_state=initial,
        hidden_until_revealed=False,
    )


def section(
    name: str,
    at: str,
    *,
    capacity: int | None = None,
    reachable: tuple[str, ...] = (),
) -> SpotSectionDeclaration:
    return SpotSectionDeclaration(
        section_id=SpotSectionId(name),
        spot_id=SpotId(at),
        name=DisplayName(name),
        capacity=NoCapacity() if capacity is None else Capacity(capacity),
        reachable_objects=tuple(ObjectId(obj) for obj in reachable),
    )


def thing(name: str, at: str) -> ObjectDeclaration:
    return ObjectDeclaration(
        object_id=ObjectId(name),
        spot_id=SpotId(at),
        name=DisplayName(name),
        description=DescriptionText(f"{name} の説明"),
        appearance=ObjectAppearance(seen_in_dark=False, hidden_until_revealed=False),
        state_keys=(),
        looks=(),
    )
