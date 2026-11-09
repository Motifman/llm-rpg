from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import TypeVar

from ai_rpg_world.game_world.domain.action.common_rule_refusal import CommonRuleRefusalKind
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.declaration.no_announcement import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.refusal_texts import RefusalTexts
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    ChangesEvery,
    DayNightDeclaration,
    DayPhaseDeclaration,
    DayPhaseName,
    NextWeatherOdds,
    NoChange,
    NoDayNight,
    NoWeather,
    TimeOfDay,
    WeatherDeclaration,
    WeatherTransitions,
    WeatherType,
    WeightedWeather,
)
from ai_rpg_world.game_world.domain.declaration.verb import (
    BuiltInActionPerceptions,
    BuiltInPerceptionRow,
    EndingDeclaration,
    PerceptionDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.world_introduction import WorldIntroduction
from ai_rpg_world.game_world.domain.lighting.sight_quality import SeesClearly, SeesNothing, SeesShapes, SightQuality
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.rules.death_rule import DeathRule
from ai_rpg_world.game_world.domain.rules.fatigue_rule import FatigueLevel, FatigueLevelName, FatigueRule
from ai_rpg_world.game_world.domain.rules.hunger_rule import (
    HungerLevel,
    HungerLevelName,
    HungerRule,
    NoStarvationDamage,
)
from ai_rpg_world.game_world.domain.rules.stealth_rule import StealthRule
from ai_rpg_world.game_world.domain.rules.tend_rule import NoTending, TendRule
from ai_rpg_world.game_world.domain.rules.world_rules import WorldRules
from ai_rpg_world.game_world.domain.sound.hearing_values import HearingValues
from ai_rpg_world.game_world.domain.sound.loudness import Loudness
from ai_rpg_world.game_world.domain.sound.sound_level import SoundLevel, SoundLoss
from ai_rpg_world.game_world.domain.value_object import (
    Capacity,
    Damage,
    FatigueAmount,
    HitPoints,
    HungerAmount,
    Multiplier,
    Probability,
    Rate,
)
from ai_rpg_world.game_world.infrastructure.scenario.condition_reader import ConditionReader
from ai_rpg_world.game_world.infrastructure.scenario.perception_reader import PerceptionReader
from ai_rpg_world.game_world.infrastructure.scenario.scenario_defaults import ScenarioDefaults
from ai_rpg_world.game_world.infrastructure.scenario.value_readers import description, people_text, ticks
from ai_rpg_world.game_world.infrastructure.scenario.yaml_node import YamlNode

_RULE_FIELDS = (
    "tend",
    "fatigue",
    "hunger",
    "death",
    "departed_persons_act",
    "name_tags",
    "hearing",
    "stealth",
    "action_durations",
    "person_max_hp",
    "pack_capacity",
)
_SIGHT_QUALITIES: dict[str, SightQuality] = {
    "sees_clearly": SeesClearly(),
    "sees_shapes": SeesShapes(),
    "sees_nothing": SeesNothing(),
}
_DEFAULT_TRANSITIONS = "default"

_Key = TypeVar("_Key")
_Value = TypeVar("_Value")
_Enum = TypeVar("_Enum", bound=Enum)


def world_rules(node: YamlNode) -> WorldRules:
    fields = node.fields(*_RULE_FIELDS)
    tend = fields.required("tend")
    return node.build(
        lambda: WorldRules(
            tend=NoTending() if tend.is_null() else _tend(tend),
            fatigue=_fatigue(fields.required("fatigue")),
            hunger=_hunger(fields.required("hunger")),
            death=DeathRule(grace=ticks(fields.required("death").fields("grace").required("grace"))),
            departed_persons_act=fields.required("departed_persons_act").boolean(),
            name_tags=fields.required("name_tags").boolean(),
            hearing=_hearing(fields.required("hearing")),
            stealth=_stealth(fields.required("stealth")),
            action_durations=_by_enum(fields.required("action_durations"), ActionKind, ticks),
            person_max_hp=_full_hp(fields.required("person_max_hp")),
            pack_capacity=_capacity(fields.required("pack_capacity")),
        )
    )


def refusal_texts(node: YamlNode) -> RefusalTexts:
    fields = node.fields("common_rules", "world_state", "hidden")
    return node.build(
        lambda: RefusalTexts(
            common_rules=_by_enum(fields.required("common_rules"), CommonRuleRefusalKind, people_text),
            world_state={
                code.build(lambda: RefusalCode(name)): people_text(code)
                for name, code in fields.required("world_state").entries()
            },
            hidden=people_text(fields.required("hidden")),
        )
    )


def built_in_action_perceptions(node: YamlNode, perceptions: PerceptionReader) -> BuiltInActionPerceptions:
    speech_and_arrival = (
        BuiltInPerceptionRow.whisper(),
        BuiltInPerceptionRow.speak(),
        BuiltInPerceptionRow.shout(),
        BuiltInPerceptionRow.arrival(),
    )
    entries = node.entries()
    rows = node.fields(*(name for name, _ in entries))

    def read(written: YamlNode, row: BuiltInPerceptionRow) -> PerceptionDeclaration:
        return perceptions.perception(written, has_target=row.has_target)

    def read_row(row: BuiltInPerceptionRow) -> PerceptionDeclaration:
        return read(rows.required(row.name), row)

    by_kind = {
        YamlNode(name, written.path).enum(ActionKind): written
        for name, written in entries
        if name not in {row.name for row in speech_and_arrival}
    }
    whisper, ordinary_voice, shout, arrival = speech_and_arrival
    return node.build(
        lambda: BuiltInActionPerceptions(
            by_kind={kind: read(written, BuiltInPerceptionRow.of_kind(kind)) for kind, written in by_kind.items()},
            whisper=read_row(whisper),
            ordinary_voice=read_row(ordinary_voice),
            shout=read_row(shout),
            arrival=read_row(arrival),
        )
    )


def introduction(node: YamlNode) -> WorldIntroduction:
    fields = node.fields("text", "objective")
    return node.build(
        lambda: WorldIntroduction(
            text=description(fields.required("text")), objective=description(fields.required("objective"))
        )
    )


def ending(node: YamlNode, conditions: ConditionReader) -> EndingDeclaration:
    return node.build(
        lambda: EndingDeclaration(ends_when=conditions.read(node.fields("ends_when").required("ends_when")))
    )


def day_night(node: YamlNode, defaults: ScenarioDefaults) -> DayNightDeclaration | NoDayNight:
    if node.is_null():
        return NoDayNight()
    fields = node.fields("ticks_per_day", "starts_at", "phases")
    return node.build(
        lambda: DayNightDeclaration(
            ticks_per_day=ticks(fields.required("ticks_per_day")),
            starts_at=_time_of_day(fields.required("starts_at")),
            phases=tuple(
                _day_phase(name, defaults.fill("day_phase", phase))
                for name, phase in fields.required("phases").entries()
            ),
        )
    )


def weather(node: YamlNode, defaults: ScenarioDefaults) -> WeatherDeclaration | NoWeather:
    if node.is_null():
        return NoWeather()
    fields = defaults.fill("weather", node).fields("initial", "changes", "announce_changes", "obscuring")
    changes = fields.required("changes")
    return node.build(
        lambda: WeatherDeclaration(
            initial=fields.required("initial").enum(WeatherType),
            changes=NoChange() if changes.is_null() else _changes_every(changes),
            announce_changes=fields.required("announce_changes").boolean(),
            obscuring=frozenset(item.enum(WeatherType) for item in fields.required("obscuring").items()),
        )
    )


def _tend(node: YamlNode) -> TendRule:
    rate = node.fields("revive_hp_rate").required("revive_hp_rate")
    return TendRule(revive_hp_rate=rate.build(lambda: Rate(rate.number())))


def _fatigue(node: YamlNode) -> FatigueRule:
    fields = node.fields("per_exertion", "limit", "levels")
    return node.build(
        lambda: FatigueRule(
            per_exertion=_amount(fields.required("per_exertion"), FatigueAmount),
            limit=_amount(fields.required("limit"), FatigueAmount),
            levels=tuple(
                FatigueLevel(starts_at=_amount(starts_at, FatigueAmount), name=FatigueLevelName(name.text()))
                for starts_at, name in _levels(fields.required("levels"))
            ),
        )
    )


def _hunger(node: YamlNode) -> HungerRule:
    fields = node.fields("per_tick", "limit", "starvation_damage", "levels")
    starvation = fields.required("starvation_damage")
    return node.build(
        lambda: HungerRule(
            per_tick=_amount(fields.required("per_tick"), HungerAmount),
            limit=_amount(fields.required("limit"), HungerAmount),
            starvation_damage=NoStarvationDamage() if starvation.is_null() else _amount(starvation, Damage),
            levels=tuple(
                HungerLevel(starts_at=_amount(starts_at, HungerAmount), name=HungerLevelName(name.text()))
                for starts_at, name in _levels(fields.required("levels"))
            ),
        )
    )


def _levels(node: YamlNode) -> list[tuple[YamlNode, YamlNode]]:
    levels = []
    for level in node.items():
        fields = level.fields("starts_at", "name")
        levels.append((fields.required("starts_at"), fields.required("name")))
    return levels


def _hearing(node: YamlNode) -> HearingValues:
    fields = node.fields(
        "loudness", "loss_per_passage", "clear_from", "muffled_from", "faint_from", "attentive_allowance"
    )
    return node.build(
        lambda: HearingValues(
            loudness=_by_enum(fields.required("loudness"), Loudness, lambda level: _amount(level, SoundLevel)),
            loss_per_passage=_amount(fields.required("loss_per_passage"), SoundLoss),
            clear_from=_amount(fields.required("clear_from"), SoundLevel),
            muffled_from=_amount(fields.required("muffled_from"), SoundLevel),
            faint_from=_amount(fields.required("faint_from"), SoundLevel),
            attentive_allowance=_amount(fields.required("attentive_allowance"), SoundLoss),
        )
    )


def _stealth(node: YamlNode) -> StealthRule:
    fields = node.fields("notice_by_bystander", "notice_by_target", "attentive_bonus", "duration_multiplier")
    multiplier = fields.required("duration_multiplier")
    return node.build(
        lambda: StealthRule(
            notice_by_bystander=_by_sight(fields.required("notice_by_bystander")),
            notice_by_target=_by_sight(fields.required("notice_by_target")),
            attentive_bonus=_probability(fields.required("attentive_bonus")),
            duration_multiplier=multiplier.build(lambda: Multiplier(multiplier.number())),
        )
    )


def _by_sight(node: YamlNode) -> dict[SightQuality, Probability]:
    chances: dict[SightQuality, Probability] = {}
    for name, chance in node.entries():
        if name not in _SIGHT_QUALITIES:
            raise chance.unreadable(f"expected one of {sorted(_SIGHT_QUALITIES)}, got {name!r}")
        chances[_SIGHT_QUALITIES[name]] = _probability(chance)
    return chances


def _by_enum(node: YamlNode, enum_type: type[_Enum], read: Callable[[YamlNode], _Value]) -> dict[_Enum, _Value]:
    return {YamlNode(name, value.path).enum(enum_type): read(value) for name, value in node.entries()}


def _day_phase(name: str, node: YamlNode) -> DayPhaseDeclaration:
    fields = node.fields("begins_at", "dark", "announcement")
    announcement = fields.required("announcement")
    return node.build(
        lambda: DayPhaseDeclaration(
            name=DayPhaseName(name),
            begins_at=_time_of_day(fields.required("begins_at")),
            dark=fields.required("dark").boolean(),
            announcement=NoAnnouncement() if announcement.is_null() else people_text(announcement),
        )
    )


def _changes_every(node: YamlNode) -> ChangesEvery:
    fields = node.fields("ticks", "transitions")
    transitions = fields.required("transitions")
    return node.build(
        lambda: ChangesEvery(
            ticks=ticks(fields.required("ticks")),
            transitions=(
                WeatherTransitions.default() if transitions.value == _DEFAULT_TRANSITIONS else _transitions(transitions)
            ),
        )
    )


def _transitions(node: YamlNode) -> WeatherTransitions:
    return node.build(
        lambda: WeatherTransitions(
            odds=tuple(
                NextWeatherOdds(
                    current=YamlNode(current, candidates.path).enum(WeatherType),
                    candidates=tuple(
                        weight.build(
                            lambda: WeightedWeather(
                                weather=YamlNode(name, weight.path).enum(WeatherType), weight=weight.integer()
                            )
                        )
                        for name, weight in candidates.entries()
                    ),
                )
                for current, candidates in node.entries()
            )
        )
    )


def _time_of_day(node: YamlNode) -> TimeOfDay:
    return node.build(lambda: TimeOfDay(node.integer()))


def _full_hp(node: YamlNode) -> HitPoints:
    return node.build(lambda: HitPoints(node.integer(), node.integer()))


def _capacity(node: YamlNode) -> Capacity:
    return node.build(lambda: Capacity(node.integer()))


def _probability(node: YamlNode) -> Probability:
    return node.build(lambda: Probability(node.number()))


def _amount(node: YamlNode, amount_type: Callable[[int], _Value]) -> _Value:
    return node.build(lambda: amount_type(node.integer()))
