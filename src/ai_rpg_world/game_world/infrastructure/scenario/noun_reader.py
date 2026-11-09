from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, TypeVar, final

from ai_rpg_world.game_world.domain.declaration.character import (
    CharacterDeclaration,
    GroupDeclaration,
    GroupingDeclaration,
    MembershipVisibility,
    NoSharedDescription,
    UsesWorldDefault,
)
from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ChoiceName,
    ChoiceStateKind,
    CountStateKind,
    FlagStateKind,
    ItemSpecDeclaration,
    ItemStateKeyDeclaration,
    ItemStateKind,
    LitWhen,
    NoRefill,
    NotALightSource,
    ObjectAppearance,
    ObjectDeclaration,
    ObjectStateKeyDeclaration,
    StateKind,
    StateValue,
    StockStateKind,
    WrittenTextStateKind,
)
from ai_rpg_world.game_world.domain.declaration.progress import (
    AllActionsAllowed,
    FlagDeclaration,
    GroupDecisionDeclaration,
    OutcomeDeclaration,
    WorldStageDeclaration,
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
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.sound import SoundLoss
from ai_rpg_world.game_world.domain.value_object import (
    Capacity,
    FlagId,
    GroupDecisionId,
    GroupId,
    GroupingId,
    HandsNeeded,
    HitPoints,
    InteractionId,
    ItemSpecId,
    ObjectId,
    OutcomeId,
    PassageId,
    PassageStateName,
    PersonId,
    SpotId,
    SpotSectionId,
    StateKeyId,
    Ticks,
    WorldStageId,
)
from ai_rpg_world.game_world.infrastructure.scenario.kinded_node import split_kind
from ai_rpg_world.game_world.infrastructure.scenario.scenario_defaults import ScenarioDefaults
from ai_rpg_world.game_world.infrastructure.scenario.value_readers import (
    action,
    count,
    description,
    display_name,
    people_text,
    state_value,
    ticks,
)
from ai_rpg_world.game_world.infrastructure.scenario.yaml_node import FlawCollector, YamlFields, YamlNode

SPOT_FIELDS = ("name", "description", "atmosphere", "sections", "objects", "discoverables")
SECTION_FIELDS = ("name", "capacity", "reachable_objects", "access")
OBJECT_FIELDS = ("name", "description", "appearance", "state_keys", "looks", "interactions")
PASSAGE_FIELDS = (
    "name",
    "description",
    "ends",
    "two_way",
    "travel_ticks",
    "states",
    "initial_state",
    "hidden_until_revealed",
    "condition",
)
ITEM_SPEC_FIELDS = ("name", "description", "state_keys", "lights_up", "hands_needed", "interactions", "use")
GROUPING_FIELDS = ("name", "visibility", "changes", "groups")
CHARACTER_FIELDS = (
    "appearance",
    "spawn_spot",
    "initial_items",
    "initial_held",
    "initial_groups",
    "knows_at_start",
    "max_hp",
    "pack_capacity",
    "being",
)
WORLD_STAGE_FIELDS = ("name", "description", "allowed_actions", "when_entered", "when_left")
GROUP_DECISION_FIELDS = (
    "name",
    "abstain_allowed",
    "reveals_ballots",
    "voters",
    "choices",
    "when_decided",
    "when_undecided",
)

_STATE_KINDS = ("flag", "count", "choice", "stock", "written_text")
_ALL = "all"

_Declaration = TypeVar("_Declaration")


@final
@dataclass
class ReadNouns:
    flags: list[FlagDeclaration] = field(default_factory=list)
    spots: list[SpotDeclaration] = field(default_factory=list)
    passages: list[PassageDeclaration] = field(default_factory=list)
    objects: list[ObjectDeclaration] = field(default_factory=list)
    item_specs: list[ItemSpecDeclaration] = field(default_factory=list)
    groupings: list[GroupingDeclaration] = field(default_factory=list)
    groups: list[GroupDeclaration] = field(default_factory=list)
    characters: list[CharacterDeclaration] = field(default_factory=list)
    world_stages: list[WorldStageDeclaration] = field(default_factory=list)
    group_decisions: list[GroupDecisionDeclaration] = field(default_factory=list)
    sections: list[SpotSectionDeclaration] = field(default_factory=list)
    outcomes: list[OutcomeDeclaration] = field(default_factory=list)
    beings: dict[PersonId, dict[str, object]] = field(default_factory=dict)
    unreadable: set[tuple[str, str]] = field(default_factory=set)

    def declared(self) -> DeclaredNouns:
        self._leave_out_those_pointing_at_unreadable()
        return DeclaredNouns(
            flags=self.flags,
            spots=self.spots,
            passages=self.passages,
            objects=self.objects,
            item_specs=self.item_specs,
            groupings=self.groupings,
            groups=self.groups,
            characters=self.characters,
            world_stages=self.world_stages,
            group_decisions=self.group_decisions,
            sections=self.sections,
            outcomes=self.outcomes,
        )

    def leave_out(self, names: set[tuple[str, str]]) -> int:
        lists: tuple[tuple[str, list[Any], str], ...] = (
            ("flag", self.flags, "flag_id"),
            ("spot", self.spots, "spot_id"),
            ("passage", self.passages, "passage_id"),
            ("object", self.objects, "object_id"),
            ("item_spec", self.item_specs, "item_spec_id"),
            ("grouping", self.groupings, "grouping_id"),
            ("group", self.groups, "group_id"),
            ("character", self.characters, "person_id"),
            ("world_stage", self.world_stages, "stage_id"),
            ("group_decision", self.group_decisions, "decision_id"),
            ("section", self.sections, "section_id"),
            ("outcome", self.outcomes, "outcome_id"),
        )
        left_out = 0
        for kind, declarations, id_field in lists:
            for declaration in list(declarations):
                name = getattr(declaration, id_field).value
                if (kind, name) in names:
                    declarations.remove(declaration)
                    self.unreadable.add((kind, name))
                    left_out += 1
        return left_out

    def _leave_out_those_pointing_at_unreadable(self) -> None:
        while True:
            left_out = (
                self._leave_out(self.passages, "passage", lambda p: p.passage_id.value, _passage_points_at)
                + self._leave_out(self.objects, "object", lambda o: o.object_id.value, _object_points_at)
                + self._leave_out(self.sections, "section", lambda s: s.section_id.value, _section_points_at)
                + self._leave_out(self.characters, "character", lambda c: c.person_id.value, _character_points_at)
            )
            if not left_out:
                return

    def _leave_out(
        self,
        declarations: list[_Declaration],
        kind: str,
        name_of: Callable[[_Declaration], str],
        points_at: Callable[[_Declaration], Iterable[tuple[str, str]]],
    ) -> int:
        pointing = [declaration for declaration in declarations if self.unreadable & set(points_at(declaration))]
        for declaration in pointing:
            declarations.remove(declaration)
            self.unreadable.add((kind, name_of(declaration)))
        return len(pointing)


def _passage_points_at(passage: PassageDeclaration) -> Iterable[tuple[str, str]]:
    return [("spot", end.value) for end in passage.ends]


def _object_points_at(obj: ObjectDeclaration) -> Iterable[tuple[str, str]]:
    return [("spot", obj.spot_id.value)]


def _section_points_at(section: SpotSectionDeclaration) -> Iterable[tuple[str, str]]:
    return [("spot", section.spot_id.value), *(("object", obj.value) for obj in section.reachable_objects)]


def _character_points_at(character: CharacterDeclaration) -> Iterable[tuple[str, str]]:
    return [
        ("spot", character.spawn_spot.value),
        *(("item_spec", item.value) for item in character.initial_items),
        *(("group", group.value) for group in character.initial_groups),
        *(("character", person.value) for person in character.knows_at_start),
    ]


class NounReader:
    def __init__(self, defaults: ScenarioDefaults, collector: FlawCollector) -> None:
        self._defaults = defaults
        self._collector = collector
        self._read = ReadNouns()

    def read(self, scenario: YamlFields) -> ReadNouns:
        self._each(scenario.nested("flags"), "flag", self._read.flags, self._flag)
        for spot_name, spot in self._entries(scenario.nested("spots")):
            if self._attempt("spot", spot_name, self._read.spots, lambda: self._spot(spot_name, spot)) is None:
                self._mark_inside_unreadable(spot)
                continue
            fields = self._defaults.fill("spot", spot).fields(*SPOT_FIELDS)
            for name, obj in self._entries(fields.nested("objects")):
                self._attempt("object", name, self._read.objects, lambda: self._object(name, spot_name, obj))
            for name, section in self._entries(fields.nested("sections")):
                self._attempt("section", name, self._read.sections, lambda: self._section(name, spot_name, section))
        self._each(scenario.nested("passages"), "passage", self._read.passages, self._passage)
        self._each(scenario.nested("item_specs"), "item_spec", self._read.item_specs, self._item_spec)
        for grouping_name, grouping_node in self._entries(scenario.nested("groupings")):
            grouping = self._attempt(
                "grouping", grouping_name, self._read.groupings, lambda: self._grouping(grouping_name, grouping_node)
            )
            groups = self._collector.attempt(
                lambda: self._defaults.fill("grouping", grouping_node).fields(*GROUPING_FIELDS).nested("groups")
            )
            if groups is None:
                continue
            for name, group in self._entries(groups):
                if grouping is None:
                    self._read.unreadable.add(("group", name))
                    continue
                read_grouping = grouping
                self._attempt("group", name, self._read.groups, lambda: self._group(name, read_grouping, group))
        self._each(scenario.nested("characters"), "character", self._read.characters, self._character)
        self._each(scenario.nested("world_stages"), "world_stage", self._read.world_stages, self._world_stage)
        self._each(
            scenario.nested("group_decisions"), "group_decision", self._read.group_decisions, self._group_decision
        )
        self._each(scenario.nested("outcomes"), "outcome", self._read.outcomes, self._outcome)
        return self._read

    def _entries(self, node: YamlNode) -> list[tuple[str, YamlNode]]:
        return self._collector.attempt(node.entries) or []

    def _mark_inside_unreadable(self, spot: YamlNode) -> None:
        if not isinstance(spot.value, dict):
            return
        for nested, kind in (("objects", "object"), ("sections", "section"), ("discoverables", "discoverable")):
            inside = spot.value.get(nested)
            if isinstance(inside, dict):
                self._read.unreadable.update((kind, str(name)) for name in inside)

    def _each(
        self,
        declarations: YamlNode,
        kind: str,
        into: list[_Declaration],
        read: Callable[[str, YamlNode], _Declaration],
    ) -> None:
        for name, node in self._entries(declarations):
            self._attempt(kind, name, into, lambda: read(name, node))

    def _attempt(
        self, kind: str, name: str, into: list[_Declaration], read: Callable[[], _Declaration]
    ) -> _Declaration | None:
        declaration = self._collector.attempt(read)
        if declaration is None:
            self._read.unreadable.add((kind, name))
            return None
        into.append(declaration)
        return declaration

    def _flag(self, name: str, node: YamlNode) -> FlagDeclaration:
        fields = self._defaults.fill("flag", node).fields("meaning", "initially_raised")
        return node.build(
            lambda: FlagDeclaration(
                flag_id=FlagId(name),
                meaning=description(fields.required("meaning")),
                initially_raised=fields.required("initially_raised").boolean(),
            )
        )

    def _spot(self, name: str, node: YamlNode) -> SpotDeclaration:
        fields = self._defaults.fill("spot", node).fields(*SPOT_FIELDS)
        atmosphere = self._defaults.fill("atmosphere", fields.nested("atmosphere")).fields(
            "lighting", "outdoor", "temperature", "ambient_sound", "smell"
        )
        ambient_sound = atmosphere.required("ambient_sound")
        smell = atmosphere.required("smell")
        return node.build(
            lambda: SpotDeclaration(
                spot_id=SpotId(name),
                name=display_name(fields.required("name")),
                description=description(fields.required("description")),
                atmosphere=SpotAtmosphere(
                    lighting=atmosphere.required("lighting").enum(Lighting),
                    outdoor=atmosphere.required("outdoor").boolean(),
                    temperature=atmosphere.required("temperature").enum(Temperature),
                    ambient_sound=NoAmbientSound() if ambient_sound.is_null() else description(ambient_sound),
                    smell=NoSmell() if smell.is_null() else description(smell),
                ),
            )
        )

    def _section(self, name: str, spot: str, node: YamlNode) -> SpotSectionDeclaration:
        fields = self._defaults.fill("section", node).fields(*SECTION_FIELDS)
        capacity = fields.required("capacity")
        return node.build(
            lambda: SpotSectionDeclaration(
                section_id=SpotSectionId(name),
                spot_id=SpotId(spot),
                name=display_name(fields.required("name")),
                capacity=NoCapacity() if capacity.is_null() else capacity.build(lambda: Capacity(capacity.integer())),
                reachable_objects=tuple(ObjectId(item.text()) for item in fields.required("reachable_objects").items()),
            )
        )

    def _object(self, name: str, spot: str, node: YamlNode) -> ObjectDeclaration:
        fields = self._defaults.fill("object", node).fields(*OBJECT_FIELDS)
        appearance = self._defaults.fill("appearance", fields.nested("appearance")).fields(
            "seen_in_dark", "hidden_until_revealed"
        )
        return node.build(
            lambda: ObjectDeclaration(
                object_id=ObjectId(name),
                spot_id=SpotId(spot),
                name=display_name(fields.required("name")),
                description=description(fields.required("description")),
                appearance=ObjectAppearance(
                    seen_in_dark=appearance.required("seen_in_dark").boolean(),
                    hidden_until_revealed=appearance.required("hidden_until_revealed").boolean(),
                ),
                state_keys=tuple(
                    key.build(
                        lambda: ObjectStateKeyDeclaration(
                            object_id=ObjectId(name), key=StateKeyId(key_name), kind=kind, initial=initial
                        )
                    )
                    for key_name, key, kind, initial in self._state_keys(fields.required("state_keys"))
                ),
            )
        )

    def _state_keys(self, node: YamlNode) -> Iterable[tuple[str, YamlNode, StateKind, StateValue]]:
        read: list[tuple[str, YamlNode, StateKind, StateValue]] = []
        for key_name, key in node.entries():
            fields = self._defaults.fill("state_key", key).fields("kind", "initial")
            kind = self._state_kind(fields.required("kind"))
            read.append((key_name, key, kind, state_value(kind, fields.required("initial"))))
        return read

    def _state_kind(self, node: YamlNode) -> StateKind:
        kinded = split_kind(node, _STATE_KINDS, explains_failure=False)
        if kinded.kind == "flag":
            kinded.nothing()
            return FlagStateKind()
        if kinded.kind == "count":
            kinded.nothing()
            return CountStateKind()
        if kinded.kind == "written_text":
            kinded.nothing()
            return WrittenTextStateKind()
        if kinded.kind == "choice":
            choices = kinded.single("choices")
            return choices.build(
                lambda: ChoiceStateKind(choices=tuple(ChoiceName(choice.text()) for choice in choices.items()))
            )
        fields = kinded.fields("capacity", "refills_every")
        refills_every = fields.required("refills_every")
        return kinded.body.build(
            lambda: StockStateKind(
                capacity=count(fields.required("capacity")),
                refills_every=NoRefill() if refills_every.is_null() else ticks(refills_every),
            )
        )

    def _passage(self, name: str, node: YamlNode) -> PassageDeclaration:
        fields = self._defaults.fill("passage", node).fields(*PASSAGE_FIELDS)
        ends = fields.required("ends").items()
        if len(ends) != 2:
            raise fields.required("ends").unreadable(f"a passage has two ends, got {len(ends)}")
        return node.build(
            lambda: PassageDeclaration(
                passage_id=PassageId(name),
                name=display_name(fields.required("name")),
                description=description(fields.required("description")),
                ends=(SpotId(ends[0].text()), SpotId(ends[1].text())),
                two_way=fields.required("two_way").boolean(),
                travel_ticks=ticks(fields.required("travel_ticks")),
                states=tuple(
                    self._passage_state(state_name, state) for state_name, state in fields.required("states").entries()
                ),
                initial_state=PassageStateName(fields.required("initial_state").text()),
                hidden_until_revealed=fields.required("hidden_until_revealed").boolean(),
            )
        )

    def _passage_state(self, name: str, node: YamlNode) -> PassageStateDeclaration:
        fields = self._defaults.fill("passage_state", node).fields("display_name", "traversable", "sound_loss")
        sound_loss = fields.required("sound_loss")
        return node.build(
            lambda: PassageStateDeclaration(
                name=PassageStateName(name),
                display_name=display_name(fields.required("display_name")),
                traversable=fields.required("traversable").boolean(),
                sound_loss=sound_loss.build(lambda: SoundLoss(sound_loss.integer())),
            )
        )

    def _item_spec(self, name: str, node: YamlNode) -> ItemSpecDeclaration:
        fields = self._defaults.fill("item_spec", node).fields(*ITEM_SPEC_FIELDS)
        state_keys = tuple(
            key.build(
                lambda: ItemStateKeyDeclaration(
                    item_spec_id=ItemSpecId(name), key=StateKeyId(key_name), kind=_item_kind(kind, key), initial=initial
                )
            )
            for key_name, key, kind, initial in self._state_keys(fields.required("state_keys"))
        )
        hands_needed = fields.required("hands_needed")
        return node.build(
            lambda: ItemSpecDeclaration(
                item_spec_id=ItemSpecId(name),
                name=display_name(fields.required("name")),
                description=description(fields.required("description")),
                state_keys=state_keys,
                lights_up=self._lights_up(fields.required("lights_up"), state_keys),
                hands_needed=hands_needed.build(lambda: HandsNeeded(hands_needed.integer())),
            )
        )

    def _lights_up(self, node: YamlNode, state_keys: tuple[ItemStateKeyDeclaration, ...]) -> LitWhen | NotALightSource:
        if node.is_null():
            return NotALightSource()
        fields = node.fields("key", "value")
        key_name = fields.required("key").text()
        state_key = next((key for key in state_keys if key.key.value == key_name), None)
        if state_key is None:
            raise fields.required("key").unreadable(f"the item has no state key {key_name!r}")
        return LitWhen(key=state_key.key, value=state_value(state_key.kind, fields.required("value")))

    def _grouping(self, name: str, node: YamlNode) -> GroupingDeclaration:
        fields = self._defaults.fill("grouping", node).fields(*GROUPING_FIELDS)
        return node.build(
            lambda: GroupingDeclaration(
                grouping_id=GroupingId(name),
                name=display_name(fields.required("name")),
                visibility=fields.required("visibility").enum(MembershipVisibility),
                changes=fields.required("changes").boolean(),
            )
        )

    def _group(self, name: str, grouping: GroupingDeclaration, node: YamlNode) -> GroupDeclaration:
        fields = self._defaults.fill("group", node).fields("name", "members_know_each_other", "shared_description")
        shared = fields.required("shared_description")
        return node.build(
            lambda: GroupDeclaration(
                group_id=GroupId(name),
                grouping=grouping,
                name=display_name(fields.required("name")),
                members_know_each_other=fields.required("members_know_each_other").boolean(),
                shared_description=NoSharedDescription() if shared.is_null() else description(shared),
            )
        )

    def _character(self, name: str, node: YamlNode) -> CharacterDeclaration:
        fields = self._defaults.fill("character", node).fields(*CHARACTER_FIELDS)
        max_hp = fields.optional("max_hp")
        pack_capacity = fields.optional("pack_capacity")
        being = fields.optional("being")
        if being is not None:
            if not isinstance(being.value, dict):
                raise being.unreadable(f"being must be a mapping, got {being.value!r}")
            self._read.beings[node.build(lambda: PersonId(name))] = {
                str(key): value for key, value in being.value.items()
            }
        return node.build(
            lambda: CharacterDeclaration(
                person_id=PersonId(name),
                appearance=description(fields.required("appearance")),
                spawn_spot=SpotId(fields.required("spawn_spot").text()),
                initial_items=tuple(ItemSpecId(item.text()) for item in fields.required("initial_items").items()),
                initial_held=tuple(ItemSpecId(item.text()) for item in fields.required("initial_held").items()),
                initial_groups=tuple(GroupId(group.text()) for group in fields.required("initial_groups").items()),
                knows_at_start=tuple(PersonId(person.text()) for person in fields.required("knows_at_start").items()),
                max_hp=(
                    UsesWorldDefault()
                    if max_hp is None or max_hp.is_null()
                    else max_hp.build(lambda: HitPoints(max_hp.integer(), max_hp.integer()))
                ),
                pack_capacity=(
                    UsesWorldDefault()
                    if pack_capacity is None or pack_capacity.is_null()
                    else pack_capacity.build(lambda: Capacity(pack_capacity.integer()))
                ),
            )
        )

    def _world_stage(self, name: str, node: YamlNode) -> WorldStageDeclaration:
        fields = self._defaults.fill("world_stage", node).fields(*WORLD_STAGE_FIELDS)
        allowed = fields.required("allowed_actions")
        return node.build(
            lambda: WorldStageDeclaration(
                stage_id=WorldStageId(name),
                name=display_name(fields.required("name")),
                description=description(fields.required("description")),
                allowed_actions=(
                    AllActionsAllowed()
                    if allowed.value == _ALL
                    else frozenset[ActionKind | InteractionId](action(item) for item in allowed.items())
                ),
            )
        )

    def _group_decision(self, name: str, node: YamlNode) -> GroupDecisionDeclaration:
        fields = self._defaults.fill("group_decision", node).fields(*GROUP_DECISION_FIELDS)
        return node.build(
            lambda: GroupDecisionDeclaration(
                decision_id=GroupDecisionId(name),
                name=display_name(fields.required("name")),
                abstain_allowed=fields.required("abstain_allowed").boolean(),
                reveals_ballots=fields.required("reveals_ballots").boolean(),
            )
        )

    def _outcome(self, name: str, node: YamlNode) -> OutcomeDeclaration:
        fields = self._defaults.fill("outcome", node).fields("name", "announcement")
        return node.build(
            lambda: OutcomeDeclaration(
                outcome_id=OutcomeId(name),
                name=display_name(fields.required("name")),
                announcement=people_text(fields.required("announcement")),
            )
        )


def _item_kind(kind: StateKind, node: YamlNode) -> ItemStateKind:
    if isinstance(kind, (FlagStateKind, CountStateKind, ChoiceStateKind)):
        return kind
    raise node.unreadable("an item state key is a flag, a count or a choice")
