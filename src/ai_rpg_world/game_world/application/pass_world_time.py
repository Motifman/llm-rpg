from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.objects_and_items import CarriedBy, LyingAt


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
    facts = session.facts()
    world = session.aggregates()
    clock = session.clock()
    clock.advance(facts.day_night())
    now = clock.now()
    world.whereabouts().advance_travels(facts.passages().closed_passages(), now)
    rules = facts.rules()
    for person in facts.people():
        world.vitals(person).pass_time(now, rules.death, rules.hunger)
    for person in facts.people():
        CarriedBy(person).run_out_aged_items(world, now)
    for spot in facts.nouns().all_spots():
        LyingAt(spot.spot_id).run_out_aged_items(world, now)
    facts.weather_declaration().pass_time_in(world, now, facts.random())
