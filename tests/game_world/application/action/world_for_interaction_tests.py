from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.application.action.action_reply import ActionReply
from ai_rpg_world.game_world.application.action.carry_out_action import CarryOutAction
from ai_rpg_world.game_world.application.action.interact_with_carried_item import (
    InteractWithCarriedItem,
    InteractWithCarriedItemCommand,
)
from ai_rpg_world.game_world.application.action.interact_with_object import (
    InteractWithObject,
    InteractWithObjectCommand,
)
from ai_rpg_world.game_world.application.action.interact_with_person import (
    InteractWithPerson,
    InteractWithPersonCommand,
)
from ai_rpg_world.game_world.application.action.use_item import UseItem, UseItemCommand
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.built_in_attempts import ItemUseAttempt
from ai_rpg_world.game_world.domain.action.interaction_attempts import (
    CarriedItemInteractionAttempt,
    ObjectInteractionAttempt,
    PersonInteractionAttempt,
    SomeoneInTheDark,
)
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.condition.flag_conditions import FlagIsRaisedCondition
from ai_rpg_world.game_world.domain.condition.subject import Actor, Target
from ai_rpg_world.game_world.domain.declaration.object_and_item import ItemSpecDeclaration
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.interaction_declaration import InteractionDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.item_use_declaration import ItemUseDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.noun_interaction_declarations import (
    ItemInteractionDeclaration,
    ObjectInteractionDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.effect.body_effects import DamageEffect
from ai_rpg_world.game_world.domain.effect.combined_effects import SequenceEffect
from ai_rpg_world.game_world.domain.effect.flag_effects import RaiseFlagEffect
from ai_rpg_world.game_world.domain.effect.item_effects import TakeItemEffect
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import (
    Count,
    Damage,
    DescriptionText,
    FlagId,
    InteractionId,
    PersonId,
    Ticks,
    WorldId,
)
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.verb_declarations_for_tests import pull_lever
from tests.game_world.support.world_design_for_tests import (
    character,
    compose_world,
    item_spec,
    nouns,
    obj,
    passage,
    spot,
)

WORLD = WorldId("interaction_world")
ALICE = PersonId("alice")
BOB = PersonId("bob")
CAROL = PersonId("carol")
GATE_OPEN_TEXT = "水門が開いている。"
GATE_CLOSED = FlagDeclaration(FlagId("gate_closed"), DescriptionText("水門が閉じた"), initially_raised=False)
POWERED = FlagDeclaration(FlagId("powered"), DescriptionText("電気が来た"), initially_raised=False)
LAMP_RUBBED = FlagDeclaration(FlagId("lamp_rubbed"), DescriptionText("ランプを磨いた"), initially_raised=False)
LAMP_LIT = FlagDeclaration(FlagId("lamp_lit"), DescriptionText("ランプを灯した"), initially_raised=False)
LEVER = obj("lever", "dam")
LAMP = item_spec("lamp")
ROCK = item_spec("rock")
KEY = item_spec("key")
PULL = replace(pull_lever(()), effect=RaiseFlagEffect(GATE_CLOSED), duration=Ticks(4))
PUSH_BUTTON = replace(
    pull_lever(()),
    interaction_id=InteractionId("push_button"),
    precondition=FlagIsRaisedCondition(GATE_CLOSED, TextWithUnassignedPeople(GATE_OPEN_TEXT)),
    effect=RaiseFlagEffect(POWERED),
)
JAM_WITH_KEY = replace(
    pull_lever(()),
    interaction_id=InteractionId("jam_with_key"),
    effect=SequenceEffect((RaiseFlagEffect(GATE_CLOSED), TakeItemEffect(Actor(), KEY, Count(1)))),
)
RUB = replace(pull_lever(()), interaction_id=InteractionId("rub"), effect=RaiseFlagEffect(LAMP_RUBBED))
TAP_SHOULDER: InteractionDeclaration = replace(
    pull_lever(()),
    interaction_id=InteractionId("tap_shoulder"),
    effect=DamageEffect(Target(), Damage(1)),
    reaches_unseen=True,
)


class WorldForInteractions:
    def __init__(self, *, carol_at: str = "shore") -> None:
        self.design = _design(carol_at)
        self.store = SqliteWorldStore.create(
            ":memory:",
            world_id=WORLD,
            scenario="interaction_world",
            scenario_hash="interaction_world",
            design=self.design,
            random=SeedableRandomSource(0),
        )
        OpenWorld(self.store)(OpenWorldCommand(world_id=WORLD, design=self.design))
        distributor = CommittedEventsDistributor()
        self.events_received: list[DomainEvent] = []
        distributor.register_receiver(self)
        self.scope = CommandScope(self.store, distributor)
        self.carry_out = CarryOutAction(self.scope, self.design)

    def receive(self, events: tuple[DomainEvent, ...]) -> None:
        self.events_received.extend(events)

    def interact_with_lever(self, actor: PersonId, interaction: InteractionDeclaration) -> ActionReply:
        attempt = ObjectInteractionAttempt(actor, LEVER, interaction, {}, Openly())
        return InteractWithObject(self.carry_out, self.design)(InteractWithObjectCommand(attempt))

    def rub(self, actor: PersonId, item: ItemInstanceId) -> ActionReply:
        attempt = CarriedItemInteractionAttempt(actor, item, RUB, {}, Openly())
        return InteractWithCarriedItem(self.carry_out, self.design)(InteractWithCarriedItemCommand(attempt))

    def use(self, actor: PersonId, item: ItemInstanceId) -> ActionReply:
        return UseItem(self.carry_out, self.design)(UseItemCommand(ItemUseAttempt(actor, item)))

    def tap(self, actor: PersonId, target: PersonId | SomeoneInTheDark) -> ActionReply:
        attempt = PersonInteractionAttempt(actor, target, TAP_SHOULDER, {}, Openly())
        return InteractWithPerson(self.carry_out, self.design)(InteractWithPersonCommand(attempt))

    def item_of(self, person: PersonId, spec: ItemSpecDeclaration) -> ItemInstanceId:
        session = self.read()
        facts = session.facts()
        found = next(item for item in facts.inventory(person).items() if facts.item(item).spec_id == spec.item_spec_id)
        session.roll_back()
        return found

    def read(self) -> WorldSession:
        return self.store.session()


def _design(carol_at: str) -> WorldDesign:
    return compose_world(
        nouns(
            flags=[GATE_CLOSED, POWERED, LAMP_RUBBED, LAMP_LIT],
            spots=[spot("dam"), spot("shore")],
            passages=[passage("path", ("dam", "shore"))],
            objects=[LEVER],
            item_specs=[LAMP, ROCK, KEY],
            characters=[
                replace(character("alice", "dam"), initial_items=(LAMP.item_spec_id, ROCK.item_spec_id)),
                replace(character("bob", "dam"), initial_items=(LAMP.item_spec_id,)),
                character("carol", carol_at),
            ],
        ),
        object_interactions=[
            ObjectInteractionDeclaration(obj=LEVER, interaction=interaction)
            for interaction in (PULL, PUSH_BUTTON, JAM_WITH_KEY)
        ],
        item_interactions=[ItemInteractionDeclaration(item_spec=LAMP, interaction=RUB)],
        item_uses=[ItemUseDeclaration(item_spec=LAMP, effect=RaiseFlagEffect(LAMP_LIT))],
        person_interactions=[TAP_SHOULDER],
    )
