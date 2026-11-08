from __future__ import annotations

from ai_rpg_world.game_world.domain.action.action_attempt import LivingOnly, UsesBody
from ai_rpg_world.game_world.domain.action.argument_declaration import ArgumentDeclaration
from ai_rpg_world.game_world.domain.action.declared_interaction import DeclaredInteraction
from ai_rpg_world.game_world.domain.action.trigger import CompletedJointAction, FiredHappening, FiredReaction
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.declaration.no_announcement import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration
from ai_rpg_world.game_world.domain.declaration.verb import (
    AnnouncementTo,
    DefaultDuration,
    GroupDecisionRulesDeclaration,
    HappeningDeclaration,
    InteractionDeclaration,
    JointActionDeclaration,
    NoFailureWitness,
    PerceptionDeclaration,
    ReactionDeclaration,
    SightTextsDeclaration,
    Silent,
)
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import (
    Background,
    Notable,
    NoTarget,
    NotNoticedLater,
    NotSeenInDim,
    NotSeenWithoutActor,
)
from ai_rpg_world.game_world.domain.value_object import DisplayName, InteractionId
from tests.game_world.support.verb_parts_for_tests import AlwaysHolds, ChangesNothing


def seen_clearly_only(clear: str) -> SightTextsDeclaration:
    return SightTextsDeclaration(
        clear=TextWithUnassignedPeople(clear),
        dim=NotSeenInDim(),
        unseen_actor=NotSeenWithoutActor(),
        noticed_later=NotNoticedLater(),
    )


def lever_pulled_quietly() -> PerceptionDeclaration:
    return PerceptionDeclaration(
        witness=seen_clearly_only("{actor}がレバーを引いた。"),
        target=NoTarget(),
        sound=Silent(),
        seen_in_dark=False,
        announcement=NoAnnouncement(),
        on_failure=NoFailureWitness(),
        salience=Background(),
    )


def bell_rung_for_everyone() -> PerceptionDeclaration:
    return PerceptionDeclaration(
        witness=seen_clearly_only("{actor}が鐘を鳴らした。"),
        target=NoTarget(),
        sound=Silent(),
        seen_in_dark=False,
        announcement=AnnouncementTo(
            audience=PeopleSelection(where=AlwaysHolds()),
            text=TextWithUnassignedPeople("招集の鐘が鳴り響いた。"),
            salience=Notable(),
        ),
        on_failure=NoFailureWitness(),
        salience=Notable(),
    )


def pull_lever(arguments: tuple[ArgumentDeclaration, ...]) -> InteractionDeclaration:
    return InteractionDeclaration(
        interaction_id=InteractionId("pull_lever"),
        display_label=DisplayName("レバーを引く"),
        precondition=AlwaysHolds(),
        effect=ChangesNothing(),
        success_text=TextWithUnassignedPeople("レバーを引いた。"),
        shows_on_success=(),
        exertion=UsesBody(),
        actor_requirement=LivingOnly(),
        perceived_as=lever_pulled_quietly(),
        reaches_unseen=False,
        duration=DefaultDuration(),
        allows_stealth=False,
        arguments=arguments,
    )


def everyone_votes_on(decision: GroupDecisionDeclaration) -> GroupDecisionRulesDeclaration:
    return GroupDecisionRulesDeclaration(
        decision=decision,
        voters=PeopleSelection(where=AlwaysHolds()),
        choices=PeopleSelection(where=AlwaysHolds()),
        when_decided=ChangesNothing(),
        when_undecided=ChangesNothing(),
    )


def as_declared_interaction(declaration: InteractionDeclaration) -> DeclaredInteraction:
    return declaration


def as_fired_happening(declaration: HappeningDeclaration) -> FiredHappening:
    return declaration


def as_fired_reaction(declaration: ReactionDeclaration) -> FiredReaction:
    return declaration


def as_completed_joint_action(declaration: JointActionDeclaration) -> CompletedJointAction:
    return declaration
