from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import TypeVar

from ai_rpg_world.game_world.domain.action.common_rule_refusal import CommonRuleRefusalKind
from ai_rpg_world.game_world.domain.action.offered_action import ActionChoiceKind
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.declaration.belongings_texts import BelongingsTexts
from ai_rpg_world.game_world.domain.declaration.body_tiers import HitPointsTier, HitPointsTiers, NeedTier, NeedTiers
from ai_rpg_world.game_world.domain.declaration.briefing_headings import BriefingHeadings
from ai_rpg_world.game_world.domain.declaration.choice_descriptions import ChoiceDescriptions
from ai_rpg_world.game_world.domain.declaration.no_announcement import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.refusal_texts import RefusalTexts
from ai_rpg_world.game_world.domain.declaration.spot.temperature import Temperature
from ai_rpg_world.game_world.domain.declaration.surroundings_texts import (
    SCENE_LINE_NAMES,
    SceneTexts,
    SurroundingsTexts,
)
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    ChangesEvery,
    ClockWording,
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
from ai_rpg_world.game_world.domain.declaration.time_and_weather.everyone_awake import EveryoneAwake
from ai_rpg_world.game_world.domain.declaration.verb import (
    BuiltInActionPerceptions,
    BuiltInPerceptionRow,
    EndingDeclaration,
    PerceptionDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.verb.action_texts import ActionTextKey, ActionTexts
from ai_rpg_world.game_world.domain.declaration.verb.item_name_joiner import ItemNameJoiner
from ai_rpg_world.game_world.domain.declaration.world_introduction import WorldIntroduction
from ai_rpg_world.game_world.domain.declaration.world_map import WorldMapWording
from ai_rpg_world.game_world.domain.declaration.world_words import WorldWords
from ai_rpg_world.game_world.domain.lighting import Lighting
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
    DisplayName,
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
from ai_rpg_world.game_world.infrastructure.scenario.value_readers import description, display_name, people_text, ticks
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
_EVERYONE_AWAKE = "everyone_awake"

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
    fields = node.fields("common_rules", "world_state", "hidden", "unlisted")
    return node.build(
        lambda: RefusalTexts(
            common_rules=_by_enum(fields.required("common_rules"), CommonRuleRefusalKind, people_text),
            world_state={
                code.build(lambda: RefusalCode(name)): people_text(code)
                for name, code in fields.required("world_state").entries()
            },
            hidden=people_text(fields.required("hidden")),
            unlisted=people_text(fields.required("unlisted")),
        )
    )


def action_texts(node: YamlNode) -> ActionTexts:
    keys = {key.written_as: key for key in ActionTextKey}
    rows = node.fields(*keys)
    summaries = {}
    done = {}
    ongoing = {}
    for written_as, key in keys.items():
        row = rows.required(written_as).fields("summary", "done", "ongoing")
        summaries[key] = people_text(row.required("summary"))
        written_done = row.optional("done")
        if written_done is not None:
            done[key] = people_text(written_done)
        written_ongoing = row.optional("ongoing")
        if written_ongoing is not None:
            ongoing[key] = people_text(written_ongoing)
    return node.build(lambda: ActionTexts(summaries=summaries, done=done, ongoing=ongoing))


_ITEM_JOINER = "item_joiner"


def built_in_action_perceptions(node: YamlNode, perceptions: PerceptionReader) -> BuiltInActionPerceptions:
    speech_and_arrival = (
        BuiltInPerceptionRow.whisper(),
        BuiltInPerceptionRow.speak(),
        BuiltInPerceptionRow.shout(),
        BuiltInPerceptionRow.arrival(),
    )
    entries = node.entries()
    rows = node.fields(*(name for name, _ in entries), _ITEM_JOINER)

    def read(written: YamlNode, row: BuiltInPerceptionRow) -> PerceptionDeclaration:
        return perceptions.perception(written, has_target=row.has_target, target_is_down=row.target_is_down)

    def read_row(row: BuiltInPerceptionRow) -> PerceptionDeclaration:
        return read(rows.required(row.name), row)

    by_kind = {
        YamlNode(name, written.path).enum(ActionKind): written
        for name, written in entries
        if name not in {row.name for row in speech_and_arrival} | {_ITEM_JOINER}
    }
    whisper, ordinary_voice, shout, arrival = speech_and_arrival
    return node.build(
        lambda: BuiltInActionPerceptions(
            by_kind={kind: read(written, BuiltInPerceptionRow.of_kind(kind)) for kind, written in by_kind.items()},
            whisper=read_row(whisper),
            ordinary_voice=read_row(ordinary_voice),
            shout=read_row(shout),
            arrival=read_row(arrival),
            item_joiner=ItemNameJoiner(rows.required(_ITEM_JOINER).text()),
        )
    )


def belongings_texts(node: YamlNode) -> BelongingsTexts:
    fields = node.fields("received", "given_up")
    return node.build(
        lambda: BelongingsTexts(
            received=people_text(fields.required("received")), given_up=people_text(fields.required("given_up"))
        )
    )


def clock_wording(node: YamlNode) -> ClockWording:
    fields = node.fields("day", "late_night", "late_night_before_hour")
    return node.build(
        lambda: ClockWording(
            day=fields.required("day").text(),
            late_night=fields.required("late_night").text(),
            late_night_before_hour=fields.required("late_night_before_hour").integer(),
        )
    )


_DESCRIPTION_EXTRAS = (
    "tend_to_player_without_tending",
    "duration_hours",
    "duration_minutes",
    "duration_turns",
    "closing",
    "listing_note",
)


def choice_descriptions(node: YamlNode) -> ChoiceDescriptions:
    choices = tuple(kind.choice_name for kind in ActionChoiceKind)
    fields = node.fields(*choices, *_DESCRIPTION_EXTRAS)
    return node.build(
        lambda: ChoiceDescriptions(
            by_choice={name: fields.required(name).text() for name in choices},
            tend_without_tending=fields.required("tend_to_player_without_tending").text(),
            duration_hours=fields.required("duration_hours").text(),
            duration_minutes=fields.required("duration_minutes").text(),
            duration_turns=fields.required("duration_turns").text(),
            closing=fields.required("closing").text(),
            listing_note=fields.required("listing_note").text(),
        )
    )


def world_map_wording(node: YamlNode) -> WorldMapWording:
    fields = node.fields(
        "place", "place_without_exits", "exit", "joiner", "minutes", "turns", "lighting", "outdoor_lighting"
    )
    return node.build(
        lambda: WorldMapWording(
            place=fields.required("place").text(),
            place_without_exits=fields.required("place_without_exits").text(),
            exit=fields.required("exit").text(),
            joiner=fields.required("joiner").text(),
            minutes=fields.required("minutes").text(),
            turns=fields.required("turns").text(),
            lighting=_by_enum(fields.required("lighting"), Lighting, lambda value: value.text()),
            outdoor_lighting=fields.required("outdoor_lighting").text(),
        )
    )


def surroundings_texts(node: YamlNode) -> SurroundingsTexts:
    fields = node.fields("people_here", "bodies_here", "joiner", "waking", "darkening", "scene")
    return node.build(
        lambda: SurroundingsTexts(
            people_here=people_text(fields.required("people_here")),
            bodies_here=people_text(fields.required("bodies_here")),
            joiner=fields.required("joiner").text(),
            waking=people_text(fields.required("waking")),
            darkening=people_text(fields.required("darkening")),
            scene=scene_texts(fields.required("scene")),
        )
    )


_SCENE_LINES = tuple(SCENE_LINE_NAMES)


def scene_texts(node: YamlNode) -> SceneTexts:
    fields = node.fields(
        "heading", *_SCENE_LINES, "need_tiers", "hit_points_tiers", "ground_items", "count_mark", "pitch_dark"
    )
    need_tiers = tuple(_need_tier(tier) for tier in fields.required("need_tiers").items())
    hit_points_tiers = tuple(_hit_points_tier(tier) for tier in fields.required("hit_points_tiers").items())
    return node.build(
        lambda: SceneTexts(
            heading=DisplayName(fields.required("heading").text()),
            **{line: fields.required(line).text() for line in _SCENE_LINES},
            need_tiers=NeedTiers(need_tiers),
            hit_points_tiers=HitPointsTiers(hit_points_tiers),
            ground_items=DisplayName(fields.required("ground_items").text()),
            count_mark=DisplayName(fields.required("count_mark").text()),
            pitch_dark=DisplayName(fields.required("pitch_dark").text()),
        )
    )


def _need_tier(node: YamlNode) -> NeedTier:
    fields = node.fields("from_percent", "name")
    return node.build(
        lambda: NeedTier(fields.required("from_percent").integer(), DisplayName(fields.required("name").text()))
    )


def _hit_points_tier(node: YamlNode) -> HitPointsTier:
    fields = node.fields("up_to_percent", "name")
    return node.build(
        lambda: HitPointsTier(fields.required("up_to_percent").integer(), DisplayName(fields.required("name").text()))
    )


def world_words(node: YamlNode) -> WorldWords:
    fields = node.fields("lighting", "temperature", "weather")
    return node.build(
        lambda: WorldWords(
            lighting=_by_enum(fields.required("lighting"), Lighting, lambda value: value.text()),
            temperature=_by_enum(fields.required("temperature"), Temperature, lambda value: value.text()),
            weather=_by_enum(fields.required("weather"), WeatherType, lambda value: value.text()),
        )
    )


def briefing_headings(node: YamlNode) -> BriefingHeadings:
    fields = node.fields("premises", "title", "overview", "world_map", "deadline", "rules", "rule_lines")
    return node.build(
        lambda: BriefingHeadings(
            premises=fields.required("premises").text(),
            title=fields.required("title").text(),
            overview=fields.required("overview").text(),
            world_map=fields.required("world_map").text(),
            deadline=fields.required("deadline").text(),
            rules=fields.required("rules").text(),
            rule_lines=tuple(line.text() for line in fields.required("rule_lines").items()),
        )
    )


def introduction(node: YamlNode) -> WorldIntroduction:
    fields = node.fields("title", "text", "premises", "show_world_map")
    shown = fields.optional("show_world_map")
    premises = fields.optional("premises")
    return node.build(
        lambda: WorldIntroduction(
            title=display_name(fields.required("title")),
            text=description(fields.required("text")),
            premises=description(premises) if premises is not None else None,
            shows_world_map=shown.boolean() if shown is not None else False,
        )
    )


def ending(node: YamlNode, conditions: ConditionReader) -> EndingDeclaration:
    return node.build(
        lambda: EndingDeclaration(ends_when=conditions.read(node.fields("ends_when").required("ends_when")))
    )


def day_night(
    node: YamlNode, defaults: ScenarioDefaults, conditions: ConditionReader
) -> DayNightDeclaration | NoDayNight:
    if node.is_null():
        return NoDayNight()
    fields = node.fields("ticks_per_day", "starts_at", "phases")
    return node.build(
        lambda: DayNightDeclaration(
            ticks_per_day=ticks(fields.required("ticks_per_day")),
            starts_at=_time_of_day(fields.required("starts_at")),
            phases=tuple(
                _day_phase(name, defaults.fill("day_phase", phase), conditions)
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
            levels=tuple(_fatigue_level(level) for level in fields.required("levels").items()),
        )
    )


def _fatigue_level(node: YamlNode) -> FatigueLevel:
    fields = node.fields("starts_at", "name", "seen_as", "felt_as")
    seen_as = fields.optional("seen_as")
    felt_as = fields.optional("felt_as")
    return FatigueLevel(
        starts_at=_amount(fields.required("starts_at"), FatigueAmount),
        name=FatigueLevelName(fields.required("name").text()),
        seen_as=None if seen_as is None else DisplayName(seen_as.text()),
        felt_as=None if felt_as is None else DisplayName(felt_as.text()),
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


def _day_phase(name: str, node: YamlNode, conditions: ConditionReader) -> DayPhaseDeclaration:
    fields = node.fields("display", "begins_at", "dark", "announcement", "audience")
    announcement = fields.required("announcement")
    return node.build(
        lambda: DayPhaseDeclaration(
            name=DayPhaseName(name),
            display_name=DisplayName(fields.required("display").text()),
            begins_at=_time_of_day(fields.required("begins_at")),
            dark=fields.required("dark").boolean(),
            announcement=NoAnnouncement() if announcement.is_null() else people_text(announcement),
            audience=_day_phase_audience(fields.required("audience"), conditions),
        )
    )


def _day_phase_audience(node: YamlNode, conditions: ConditionReader) -> PeopleSelection | EveryoneAwake:
    if node.value == _EVERYONE_AWAKE:
        return EveryoneAwake()
    if not node.is_mapping():
        raise node.unreadable(f"expected {_EVERYONE_AWAKE} or a people selection {{ where }}, got {node.value!r}")
    return conditions.people(node)


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
