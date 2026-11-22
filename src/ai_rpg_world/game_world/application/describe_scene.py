from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.being.contract import Scene
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.look_around import SurroundingsOf
from ai_rpg_world.game_world.application.world_perception_senses import perceiver_of
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.perception.surroundings import VisibleSurroundings
from ai_rpg_world.game_world.domain.value_object import DisplayName, PersonId, SpotId


@final
@dataclass(frozen=True)
class DescribeSceneCommand:
    person: PersonId


@final
class DescribeScene:
    def __init__(self, scope: CommandScope, design: WorldDesign) -> None:
        self._scope = scope
        self._design = design

    def __call__(self, command: DescribeSceneCommand) -> Scene:
        return self._scope.run(lambda session: self._describe(session, command.person))

    def _describe(self, session: WorldSession, person: PersonId) -> Scene:
        facts = session.facts()
        seen = VisibleSurroundings.seen_by(perceiver_of(facts, person), SurroundingsOf(person, facts, self._design))
        return seen.scene_with(self._design.surroundings_texts, _Names(facts, self._design))


@final
class _Names:
    def __init__(self, facts: WorldFacts, design: WorldDesign) -> None:
        self._facts = facts
        self._design = design

    def spot_name(self, spot: SpotId) -> DisplayName:
        return self._facts.nouns().spot_of(spot).name

    def item_name(self, item: ItemInstanceId) -> DisplayName:
        return self._design.nouns.item_spec_of(self._facts.item(item).spec_id).name
