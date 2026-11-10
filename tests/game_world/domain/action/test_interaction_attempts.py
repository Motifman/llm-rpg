from __future__ import annotations

from collections.abc import Callable

import pytest

from ai_rpg_world.game_world.domain.action.action_arguments import ActionArguments, TextArgumentValue
from ai_rpg_world.game_world.domain.action.action_attempt import (
    ActionAttempt,
    DoesNotUseBody,
    LivingOnly,
    LivingOrDeparted,
    UsesBody,
    WithObject,
    WithPerson,
)
from ai_rpg_world.game_world.domain.action.argument_declaration import (
    ArgumentDeclaration,
    ItemArgument,
    TextArgument,
)
from ai_rpg_world.game_world.domain.action.declared_interaction import DeclaredInteraction
from ai_rpg_world.game_world.domain.action.interaction_attempts import (
    CarriedItemInteractionAttempt,
    ObjectInteractionAttempt,
    PersonInteractionAttempt,
    SomeoneInTheDark,
)
from ai_rpg_world.game_world.domain.action.manner import Manner, Openly, Stealthily
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.declaration.progress import WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.exception.action_exception import (
    ArgumentsDoNotMatchDeclarationException,
    StealthNotAllowedException,
    UnseenTargetNotAllowedException,
)
from ai_rpg_world.game_world.domain.exception.trigger_exception import (
    ArgumentNotInTriggerException,
    ItemNotInTriggerException,
    SubjectNotInTriggerException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import (
    DescriptionText,
    DisplayName,
    InteractionId,
    ObjectId,
    PersonId,
    WorldStageId,
)
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from tests.game_world.domain.whereabouts._builders import thing
from tests.game_world.support.declarations_for_tests import InteractionForTests

ALICE = PersonId("alice")
BOB = PersonId("bob")
NOTEBOOK = ItemInstanceId("notebook_1")
LEVER = thing("lever", "lift_landing")
WORDS = ArgumentName("words")

_NO_ARGUMENTS: ActionArguments = {}

_Build = Callable[[DeclaredInteraction, Manner, ActionArguments], ActionAttempt]

_BUILDERS: dict[str, _Build] = {
    "object": lambda interaction, manner, arguments: ObjectInteractionAttempt(
        ALICE, LEVER, interaction, arguments, manner
    ),
    "carried_item": lambda interaction, manner, arguments: CarriedItemInteractionAttempt(
        ALICE, NOTEBOOK, interaction, arguments, manner
    ),
    "person": lambda interaction, manner, arguments: PersonInteractionAttempt(
        ALICE, BOB, interaction, arguments, manner
    ),
}

_KINDS = {
    "object": ActionKind.INTERACT_WITH_OBJECT,
    "carried_item": ActionKind.INTERACT_WITH_CARRIED_ITEM,
    "person": ActionKind.INTERACT_WITH_PERSON,
}


def _stage(allowed: frozenset[ActionKind | InteractionId]) -> WorldStageDeclaration:
    return WorldStageDeclaration(
        stage_id=WorldStageId("night"),
        name=DisplayName("夜"),
        description=DescriptionText("夜の説明"),
        allowed_actions=allowed,
    )


class TestPropertiesReadFromTheDeclaration:
    """物・品物・人への操作が、性質を操作の宣言の欄から答えることを保証する。"""

    @pytest.mark.parametrize("target", _BUILDERS)
    def test_answers_kind_by_what_it_acts_on(self, target: str) -> None:
        """物への操作は INTERACT_WITH_OBJECT、持っている品物は INTERACT_WITH_CARRIED_ITEM、人は INTERACT_WITH_PERSON を答える。"""
        attempt = _BUILDERS[target](InteractionForTests(InteractionId("pull")), Openly(), _NO_ARGUMENTS)

        assert attempt.kind() is _KINDS[target]

    @pytest.mark.parametrize("target", _BUILDERS)
    @pytest.mark.parametrize("exertion", [UsesBody(), DoesNotUseBody()])
    def test_answers_exertion_of_the_declaration(self, target: str, exertion: UsesBody | DoesNotUseBody) -> None:
        """exertion() は、操作の宣言の exertion をそのまま答える。"""
        interaction = InteractionForTests(InteractionId("pull"), exertion=exertion)

        assert _BUILDERS[target](interaction, Openly(), _NO_ARGUMENTS).exertion() == exertion

    @pytest.mark.parametrize("target", _BUILDERS)
    @pytest.mark.parametrize("requirement", [LivingOnly(), LivingOrDeparted()])
    def test_answers_actor_requirement_of_the_declaration(
        self, target: str, requirement: LivingOnly | LivingOrDeparted
    ) -> None:
        """actor_requirement() は、操作の宣言の actor_requirement をそのまま答える。"""
        interaction = InteractionForTests(InteractionId("pull"), actor_requirement=requirement)

        assert _BUILDERS[target](interaction, Openly(), _NO_ARGUMENTS).actor_requirement() == requirement

    @pytest.mark.parametrize("target", _BUILDERS)
    def test_cannot_start_while_busy(self, target: str) -> None:
        """操作は、前の行為を行っているあいだには始められない。"""
        attempt = _BUILDERS[target](InteractionForTests(InteractionId("pull")), Openly(), _NO_ARGUMENTS)

        assert not attempt.can_start_while_busy()

    @pytest.mark.parametrize("target", _BUILDERS)
    def test_is_allowed_by_interaction_id_not_by_kind(self, target: str) -> None:
        """操作は、段階の allowed_actions に自分の InteractionId があるときだけ許され、ActionKind だけでは許されない。"""
        attempt = _BUILDERS[target](InteractionForTests(InteractionId("pull")), Openly(), _NO_ARGUMENTS)

        assert attempt.is_allowed_in(_stage(frozenset({InteractionId("pull")})))
        assert not attempt.is_allowed_in(_stage(frozenset({_KINDS[target]})))

    @pytest.mark.parametrize("target", _BUILDERS)
    def test_world_without_stages_allows_the_interaction(self, target: str) -> None:
        """段階を宣言しない世界 (NoWorldStages) では、操作は許される。"""
        attempt = _BUILDERS[target](InteractionForTests(InteractionId("pull")), Openly(), _NO_ARGUMENTS)

        assert attempt.is_allowed_in(NoWorldStages())

    @pytest.mark.parametrize("target", _BUILDERS)
    def test_is_done_as_its_kind_and_its_interaction(self, target: str) -> None:
        """操作は、最後に行った行為として、自分の ActionKind と自分の InteractionId の両方で記録される。"""
        attempt = _BUILDERS[target](InteractionForTests(InteractionId("pull")), Openly(), _NO_ARGUMENTS)

        assert attempt.done_as() == frozenset({_KINDS[target], InteractionId("pull")})

    def test_object_interaction_requires_being_with_the_object(self) -> None:
        """物への操作は、その物の近くにいる必要 (WithObject) を答える。"""
        attempt = ObjectInteractionAttempt(ALICE, LEVER, InteractionForTests(InteractionId("pull")), {}, Openly())

        assert attempt.copresence_requirements() == (WithObject(ObjectId("lever")),)

    def test_carried_item_interaction_requires_no_one_nearby(self) -> None:
        """持っている品物への操作は、何の近くにいる必要も答えない。"""
        attempt = CarriedItemInteractionAttempt(
            ALICE, NOTEBOOK, InteractionForTests(InteractionId("read")), {}, Openly()
        )

        assert attempt.copresence_requirements() == ()

    def test_person_interaction_requires_being_with_the_target(self) -> None:
        """人への操作は、相手と同じ場所にいる必要 (WithPerson) を答え、person_as(TARGET) に相手を答える。"""
        attempt = PersonInteractionAttempt(ALICE, BOB, InteractionForTests(InteractionId("hit")), {}, Openly())

        assert attempt.copresence_requirements() == (WithPerson(BOB),)
        assert attempt.person_as(SubjectKind.TARGET) == BOB

    def test_carried_item_interaction_answers_the_item(self) -> None:
        """持っている品物への操作は、this_item() にその品物を答える。"""
        attempt = CarriedItemInteractionAttempt(
            ALICE, NOTEBOOK, InteractionForTests(InteractionId("read")), {}, Openly()
        )

        assert attempt.this_item() == NOTEBOOK

    def test_object_interaction_answers_no_item(self) -> None:
        """物への操作は品物を持たず、this_item() は ItemNotInTriggerException を投げる。"""
        attempt = ObjectInteractionAttempt(ALICE, LEVER, InteractionForTests(InteractionId("pull")), {}, Openly())

        with pytest.raises(ItemNotInTriggerException):
            attempt.this_item()


    def test_unanswered_subject_message_names_the_attempt_and_the_kind(self) -> None:
        """物への操作に TARGET を尋ねると、文は「<操作の repr> does not answer TARGET」。"""
        attempt = ObjectInteractionAttempt(ALICE, LEVER, InteractionForTests(InteractionId("pull")), {}, Openly())

        with pytest.raises(SubjectNotInTriggerException) as raised:
            attempt.person_as(SubjectKind.TARGET)

        assert str(raised.value) == f"{attempt!r} does not answer TARGET"

    def test_unanswered_item_message_names_the_attempt(self) -> None:
        """物への操作に品物を尋ねると、文は「<操作の repr> does not answer the item」。"""
        attempt = ObjectInteractionAttempt(ALICE, LEVER, InteractionForTests(InteractionId("pull")), {}, Openly())

        with pytest.raises(ItemNotInTriggerException) as raised:
            attempt.this_item()

        assert str(raised.value) == f"{attempt!r} does not answer the item"


class TestStealthily:
    """こっそり (Stealthily) 行えるのが、allows_stealth の操作だけであることを保証する。"""

    @pytest.mark.parametrize("target", _BUILDERS)
    def test_stealthily_on_interaction_not_allowing_stealth_raises(self, target: str) -> None:
        """allows_stealth が偽の操作を Stealthily で作ると StealthNotAllowedException を投げる。"""
        interaction = InteractionForTests(InteractionId("pull"), allows_stealth=False)

        with pytest.raises(StealthNotAllowedException):
            _BUILDERS[target](interaction, Stealthily(), _NO_ARGUMENTS)

    @pytest.mark.parametrize("target", _BUILDERS)
    def test_stealthily_on_interaction_allowing_stealth_is_accepted(self, target: str) -> None:
        """allows_stealth が真の操作は Stealthily で作れる。"""
        interaction = InteractionForTests(InteractionId("steal"), allows_stealth=True)

        assert _BUILDERS[target](interaction, Stealthily(), _NO_ARGUMENTS).manner == Stealthily()


class TestSomeoneInTheDark:
    """暗がりの誰か (SomeoneInTheDark) に向けられるのが、reaches_unseen の操作だけであることを保証する。"""

    def test_unseen_target_on_interaction_not_reaching_unseen_raises(self) -> None:
        """reaches_unseen が偽の操作を SomeoneInTheDark に向けると UnseenTargetNotAllowedException を投げる。"""
        interaction = InteractionForTests(InteractionId("hit"), reaches_unseen=False)

        with pytest.raises(UnseenTargetNotAllowedException):
            PersonInteractionAttempt(ALICE, SomeoneInTheDark(), interaction, {}, Openly())

    def test_unseen_target_is_not_yet_a_person(self) -> None:
        """SomeoneInTheDark に向けた操作は、相手がまだ決まっていないので、近くにいる必要を答えず、person_as(TARGET) は SubjectNotInTriggerException を投げる。"""
        interaction = InteractionForTests(InteractionId("hit"), reaches_unseen=True)
        attempt = PersonInteractionAttempt(ALICE, SomeoneInTheDark(), interaction, {}, Openly())

        assert attempt.copresence_requirements() == ()
        with pytest.raises(SubjectNotInTriggerException):
            attempt.person_as(SubjectKind.TARGET)


class TestArguments:
    """操作に渡す引数が、操作の宣言の arguments と名前と種類で合うことを保証する。"""

    def test_answers_declared_arguments(self) -> None:
        """宣言どおりの引数を渡すと、argument(name) はその値を答える。"""
        interaction = InteractionForTests(
            InteractionId("write"),
            arguments=(
                ArgumentDeclaration(WORDS, TextArgument()),
                ArgumentDeclaration(ArgumentName("pen"), ItemArgument()),
            ),
        )
        pen = ItemInstanceId("pen_1")
        attempt = CarriedItemInteractionAttempt(
            ALICE,
            NOTEBOOK,
            interaction,
            {WORDS: TextArgumentValue("ここを掘れ"), ArgumentName("pen"): pen},
            Openly(),
        )

        assert attempt.argument(WORDS) == TextArgumentValue("ここを掘れ")
        assert attempt.argument(ArgumentName("pen")) == pen

    def test_undeclared_argument_name_raises_when_asked(self) -> None:
        """宣言に無い名前を argument() に尋ねると ArgumentNotInTriggerException を投げる。"""
        attempt = CarriedItemInteractionAttempt(
            ALICE, NOTEBOOK, InteractionForTests(InteractionId("read")), {}, Openly()
        )

        with pytest.raises(ArgumentNotInTriggerException):
            attempt.argument(WORDS)

    def test_undeclared_argument_message_names_the_attempt_and_the_argument(self) -> None:
        """宣言に無い引数 words を尋ねると、文は「<操作の repr> does not answer the argument 'words'」。"""
        attempt = CarriedItemInteractionAttempt(
            ALICE, NOTEBOOK, InteractionForTests(InteractionId("read")), {}, Openly()
        )

        with pytest.raises(ArgumentNotInTriggerException) as raised:
            attempt.argument(WORDS)

        assert str(raised.value) == f"{attempt!r} does not answer the argument 'words'"

    @pytest.mark.parametrize(
        "arguments",
        [
            {},
            {WORDS: TextArgumentValue("ここを掘れ"), ArgumentName("extra"): TextArgumentValue("余分")},
            {WORDS: ItemInstanceId("pen_1")},
        ],
        ids=["missing", "undeclared_name", "wrong_kind"],
    )
    def test_arguments_not_matching_declaration_raise(self, arguments: ActionArguments) -> None:
        """宣言の引数が欠けている、宣言に無い名前がある、文の引数に品物を渡したとき、作るときに ArgumentsDoNotMatchDeclarationException を投げる。"""
        interaction = InteractionForTests(
            InteractionId("write"), arguments=(ArgumentDeclaration(WORDS, TextArgument()),)
        )

        with pytest.raises(ArgumentsDoNotMatchDeclarationException):
            CarriedItemInteractionAttempt(ALICE, NOTEBOOK, interaction, arguments, Openly())

    def test_text_given_for_item_argument_raises(self) -> None:
        """品物の引数 (ItemArgument) に文を渡すと ArgumentsDoNotMatchDeclarationException を投げる。"""
        interaction = InteractionForTests(
            InteractionId("give"), arguments=(ArgumentDeclaration(ArgumentName("gift"), ItemArgument()),)
        )

        with pytest.raises(ArgumentsDoNotMatchDeclarationException):
            PersonInteractionAttempt(ALICE, BOB, interaction, {ArgumentName("gift"): TextArgumentValue("花")}, Openly())
