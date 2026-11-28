from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.objects_and_items.items_running_out import ItemsRunningOut


@final
@dataclass(frozen=True)
class PassWorldTimeCommand:
    pass


@final
class PassWorldTime:
    def __init__(self, scope: CommandScope) -> None:
        self._scope = scope

    def __call__(self, command: PassWorldTimeCommand) -> None:
        self._scope.run(_pass_one_tick)


def _pass_one_tick(session: WorldSession) -> None:
    session.ending().admit_change()
    facts = session.facts()
    world = session.aggregates()
    clock = session.clock()
    clock.advance(facts.day_night(), facts)
    now = clock.now()
    world.whereabouts().advance_travels(facts.passages().closed_passages(), now)
    rules = facts.rules()
    people_in_world = facts.outcomes().people_in_world()
    for person in people_in_world:
        world.vitals(person).pass_time(now, rules.death, rules.hunger)
    items = ItemsRunningOut(world)
    for person in people_in_world:
        items.run_out_carried_by(person, now)
    for spot in facts.nouns().all_spots():
        items.run_out_lying_at(spot.spot_id, now)
    facts.weather_declaration().pass_time_in(world, now, facts.random())
