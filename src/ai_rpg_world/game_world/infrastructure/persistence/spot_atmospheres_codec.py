from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.declaration.spot import NoAmbientSound, NoSmell, SpotAtmosphere, Temperature
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.value_object import DescriptionText, SpotId
from ai_rpg_world.game_world.domain.whereabouts import AtmosphereAtSpot, SpotAtmospheresMemento
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    JsonUnion,
    JsonUnionMember,
    distinct_items,
    enum_from_json,
    enum_to_json,
    exact_fields,
    json_bool,
    json_str,
    world_id_from_json,
)


def _description_text() -> JsonUnionMember[DescriptionText]:
    return JsonUnionMember(
        "description_text", DescriptionText, lambda text: text.text, lambda raw: DescriptionText(json_str(raw))
    )


_AMBIENT_SOUND: JsonUnion[DescriptionText | NoAmbientSound] = JsonUnion(
    _description_text(), JsonUnionMember.fieldless("no_ambient_sound", NoAmbientSound())
)
_SMELL: JsonUnion[DescriptionText | NoSmell] = JsonUnion(
    _description_text(), JsonUnionMember.fieldless("no_smell", NoSmell())
)


def _atmosphere_to_json(atmosphere: SpotAtmosphere) -> object:
    return {
        "lighting": enum_to_json(atmosphere.lighting),
        "outdoor": atmosphere.outdoor,
        "temperature": enum_to_json(atmosphere.temperature),
        "ambient_sound": _AMBIENT_SOUND.to_json(atmosphere.ambient_sound),
        "smell": _SMELL.to_json(atmosphere.smell),
    }


def _atmosphere_from_json(raw: object) -> SpotAtmosphere:
    fields = exact_fields(raw, ("lighting", "outdoor", "temperature", "ambient_sound", "smell"))
    return SpotAtmosphere(
        lighting=enum_from_json(fields["lighting"], Lighting),
        outdoor=json_bool(fields["outdoor"]),
        temperature=enum_from_json(fields["temperature"], Temperature),
        ambient_sound=_AMBIENT_SOUND.from_json(fields["ambient_sound"]),
        smell=_SMELL.from_json(fields["smell"]),
    )


def _atmosphere_at_spot_from_json(raw: object) -> AtmosphereAtSpot:
    fields = exact_fields(raw, ("spot", "atmosphere"))
    return AtmosphereAtSpot(SpotId(json_str(fields["spot"])), _atmosphere_from_json(fields["atmosphere"]))


@final
class SpotAtmospheresCodec:
    kind = "spot_atmospheres"
    version = 1
    memento_type = SpotAtmospheresMemento

    def to_json(self, memento: SpotAtmospheresMemento) -> object:
        return {
            "world_id": memento.world_id.value,
            "atmospheres": [
                {"spot": entry.spot.value, "atmosphere": _atmosphere_to_json(entry.atmosphere)}
                for entry in sorted(memento.atmospheres, key=lambda entry: entry.spot.value)
            ],
        }

    def from_json(self, raw: object) -> SpotAtmospheresMemento:
        fields = exact_fields(raw, ("world_id", "atmospheres"))
        return SpotAtmospheresMemento(
            world_id=world_id_from_json(fields["world_id"]),
            atmospheres=distinct_items(fields["atmospheres"], _atmosphere_at_spot_from_json),
        )
