from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.declaration.time_and_weather import NoWeather
from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
from ai_rpg_world.game_world.domain.objects_and_items import CarriedBy, ItemInstanceId, LyingAt, WhereItemWas
from ai_rpg_world.game_world.domain.value_object import WorldTick


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
    world.whereabouts().advance_travels(facts.passages().closed_passages())
    rules = facts.rules()
    for person in facts.people():
        world.vitals(person).pass_time(now, rules.death, rules.hunger)
    for person in facts.people():
        inventory = world.inventory(person)
        _run_out_items(world, now, inventory.items(), inventory.give_up, CarriedBy(person))
    for spot in facts.nouns().all_spots():
        ground = world.ground_items(spot.spot_id)
        _run_out_items(world, now, ground.items(), ground.take, LyingAt(spot.spot_id))
    weather = facts.weather_declaration()
    if not isinstance(weather, NoWeather):
        world.weather().pass_time(now, weather, facts.random())


def _run_out_items(
    world: WorldAggregates,
    now: WorldTick,
    items: tuple[ItemInstanceId, ...],
    give_up: Callable[[ItemInstanceId], None],
    where: WhereItemWas,
) -> None:
    for item_id in items:
        item = world.item(item_id)
        if item.has_run_out(now):
            give_up(item_id)
            item.run_out(now, where)
            world.take_item_out_of_world(item_id)
