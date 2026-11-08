from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import final

from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
from ai_rpg_world.game_world.domain.declaration.progress import WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.design_flaw import DesignWarning
from ai_rpg_world.game_world.domain.exception.world_design_exception import WorldDesignFlawsException
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.infrastructure.scenario import world_reader
from ai_rpg_world.game_world.infrastructure.scenario.condition_reader import ConditionReader
from ai_rpg_world.game_world.infrastructure.scenario.declared_names import DeclaredNames
from ai_rpg_world.game_world.infrastructure.scenario.effect_reader import EffectReader
from ai_rpg_world.game_world.infrastructure.scenario.noun_reader import NounReader, ReadNouns
from ai_rpg_world.game_world.infrastructure.scenario.perception_reader import PerceptionReader
from ai_rpg_world.game_world.infrastructure.scenario.scenario_defaults import ScenarioDefaults
from ai_rpg_world.game_world.infrastructure.scenario.scenario_layout import YamlPath
from ai_rpg_world.game_world.infrastructure.scenario.scenario_source import read_scenario_source
from ai_rpg_world.game_world.infrastructure.scenario.verb_reader import VerbReader
from ai_rpg_world.game_world.infrastructure.scenario.yaml_node import FlawCollector, Unreadable, YamlFields, YamlNode

_TOP_FIELDS = (
    "introduction",
    "rules",
    "time",
    "flags",
    "groupings",
    "spots",
    "passages",
    "item_specs",
    "characters",
    "world_stages",
    "initial_stage",
    "group_decisions",
    "outcomes",
    "happenings",
    "reactions",
    "joint_actions",
    "person_interactions",
    "ending",
    "refusal_texts",
    "built_in_action_perceptions",
    "defaults",
    "perception_defaults",
)


@final
@dataclass(frozen=True)
class LoadedScenario:
    design: WorldDesign
    beings: Mapping[PersonId, Mapping[str, object]]
    loading_warnings: tuple[DesignWarning, ...]

    def warnings(self) -> tuple[DesignWarning, ...]:
        return (*self.loading_warnings, *self.design.warnings())


def load_scenario(scenario: Path) -> LoadedScenario:
    source = read_scenario_source(scenario)
    if source.flaws:
        raise WorldDesignFlawsException(source.flaws)
    collector = FlawCollector()
    try:
        return _loaded(source.value, collector)
    except Unreadable as unreadable:
        collector.record((unreadable.flaw,))
        raise WorldDesignFlawsException(collector.flaws) from unreadable


def _loaded(value: object, collector: FlawCollector) -> LoadedScenario:
    root = YamlNode(value, YamlPath.root())
    fields = collector.attempt(lambda: root.fields(*_TOP_FIELDS))
    if fields is None:
        raise WorldDesignFlawsException(collector.flaws)
    defaults = collector.attempt(lambda: ScenarioDefaults(fields.nested("defaults")))
    if defaults is None:
        raise WorldDesignFlawsException(collector.flaws)
    read_nouns = NounReader(defaults, collector).read(fields)
    nouns = _declared_nouns(read_nouns, collector)
    if nouns is None:
        raise WorldDesignFlawsException(collector.flaws)
    loading = _ScenarioLoading(fields, defaults, read_nouns, nouns, collector)
    design = loading.compose()
    return LoadedScenario(
        design=design,
        beings=MappingProxyType({person: MappingProxyType(being) for person, being in read_nouns.beings.items()}),
        loading_warnings=tuple(loading.warnings),
    )


def _declared_nouns(read_nouns: ReadNouns, collector: FlawCollector) -> DeclaredNouns | None:
    while True:
        try:
            return read_nouns.declared()
        except WorldDesignFlawsException as flawed:
            collector.record(flawed.flaws)
            flawed_nouns = {(flaw.location.declaration, flaw.location.name) for flaw in flawed.flaws}
            if not read_nouns.leave_out(flawed_nouns):
                return None


class _ScenarioLoading:
    def __init__(
        self,
        fields: YamlFields,
        defaults: ScenarioDefaults,
        read_nouns: ReadNouns,
        nouns: DeclaredNouns,
        collector: FlawCollector,
    ) -> None:
        self._fields = fields
        self._defaults = defaults
        self._nouns = nouns
        self._collector = collector
        self.warnings: list[DesignWarning] = []
        names = DeclaredNames(nouns, frozenset(read_nouns.unreadable))
        self._names = names
        self._conditions = ConditionReader(names)
        self._effects = EffectReader(
            names,
            self._conditions,
            lambda decision: self._verbs.voters_and_choices(decision, fields.nested("group_decisions")),
        )
        self._perceptions = PerceptionReader(
            defaults, fields.nested("perception_defaults"), names, self._conditions, self.warnings
        )
        self._verbs = VerbReader(defaults, names, self._conditions, self._effects, self._perceptions, collector)

    def compose(self) -> WorldDesign:
        verbs = self._verbs.read(self._fields)
        collector = self._collector
        time = self._fields.nested("time")
        time_fields = collector.attempt(lambda: time.fields("day_night", "weather"))
        rules = collector.attempt(lambda: world_reader.world_rules(self._fields.required("rules")))
        refusal_texts = collector.attempt(lambda: world_reader.refusal_texts(self._fields.required("refusal_texts")))
        built_in = collector.attempt(
            lambda: world_reader.built_in_action_perceptions(
                self._fields.required("built_in_action_perceptions"), self._perceptions
            )
        )
        introduction = collector.attempt(lambda: world_reader.introduction(self._fields.required("introduction")))
        ending = collector.attempt(lambda: world_reader.ending(self._fields.required("ending"), self._conditions))
        initial_stage = collector.attempt(self._initial_stage)
        day_night = (
            None
            if time_fields is None
            else collector.attempt(
                lambda: world_reader.day_night(time_fields.nested_or_null("day_night"), self._defaults)
            )
        )
        weather = (
            None
            if time_fields is None
            else collector.attempt(lambda: world_reader.weather(time_fields.nested_or_null("weather"), self._defaults))
        )
        if (
            collector.flaws
            or rules is None
            or refusal_texts is None
            or built_in is None
            or introduction is None
            or ending is None
            or initial_stage is None
            or day_night is None
            or weather is None
        ):
            raise WorldDesignFlawsException(collector.flaws)
        return WorldDesign.compose(
            nouns=self._nouns,
            object_interactions=verbs.object_interactions,
            item_interactions=verbs.item_interactions,
            item_uses=verbs.item_uses,
            section_accesses=verbs.section_accesses,
            passage_traversals=verbs.passage_traversals,
            world_stage_effects=verbs.world_stage_effects,
            group_decision_rules=verbs.group_decision_rules,
            happenings=verbs.happenings,
            reactions=verbs.reactions,
            discoverables=verbs.discoverables,
            joint_actions=verbs.joint_actions,
            person_interactions=verbs.person_interactions,
            ending=ending,
            world_rules=rules,
            refusal_texts=refusal_texts,
            built_in_action_perceptions=built_in,
            weather=weather,
            day_night=day_night,
            initial_stage=initial_stage,
            introduction=introduction,
        )

    def _initial_stage(self) -> WorldStageDeclaration | NoWorldStages:
        initial = self._fields.optional("initial_stage")
        if initial is None:
            if self._fields.nested("world_stages").entries():
                raise YamlNode(None, self._fields.node.path / "initial_stage").unreadable(
                    "initial_stage is required when world_stages are declared"
                )
            return NoWorldStages()
        return self._names.world_stage(initial)
