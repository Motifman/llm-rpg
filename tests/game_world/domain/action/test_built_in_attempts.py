from __future__ import annotations

from dataclasses import dataclass

import pytest

from ai_rpg_world.game_world.domain.action.action_attempt import (
    ActionAttempt,
    CopresenceRequirement,
    DoesNotUseBody,
    Exertion,
    LivingOnly,
    LivingOrDeparted,
    UsesBody,
    WithGroundItem,
    WithPerson,
)
from ai_rpg_world.game_world.domain.action.built_in_attempts import (
    EnterSectionAttempt,
    GroundItemPickupAttempt,
    GroupDecisionBallotAttempt,
    HoldItemAttempt,
    ItemDropAttempt,
    ItemHandOverAttempt,
    ItemUseAttempt,
    LeaveSectionAttempt,
    ListeningAttempt,
    PutAwayItemAttempt,
    SpeechAttempt,
    SpotSearchAttempt,
    TendAttempt,
    TravelAttempt,
    WaitAttempt,
)
from ai_rpg_world.game_world.domain.action.delivery import Delivery
from ai_rpg_world.game_world.domain.action.manner import Openly, Stealthily
from ai_rpg_world.game_world.domain.action.speech import OrdinaryVoice, Shout, SpeechContent, Whisper
from ai_rpg_world.game_world.domain.action.wait_reason import NoReason, WaitReason
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.declaration.progress import (
    AllActionsAllowed,
    GroupDecisionDeclaration,
    WorldStageDeclaration,
)
from ai_rpg_world.game_world.domain.exception.action_exception import (
    BlankSpeechContentException,
    BlankWaitReasonException,
    NoDeliveriesException,
)
from ai_rpg_world.game_world.domain.exception.trigger_exception import (
    ArgumentNotInTriggerException,
    ItemNotInTriggerException,
    SubjectNotInTriggerException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.person import StruckByPerson, WorldHappening
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import (
    DescriptionText,
    DisplayName,
    GroupDecisionId,
    PersonId,
    WorldStageId,
)
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from ai_rpg_world.game_world.domain.world_progress.group_decision import Abstain, VoteFor
from tests.game_world.domain.whereabouts._builders import section, spot
from tests.game_world.support.declarations_for_tests import SectionAccessForTests

ALICE = PersonId("alice")
BOB = PersonId("bob")
CAROL = PersonId("carol")
LAMP = ItemInstanceId("lamp_1")
ROPE = ItemInstanceId("rope_1")
CAGE = section("lift_cage", "lift_landing")
EXILE = GroupDecisionDeclaration(
    decision_id=GroupDecisionId("exile"), name=DisplayName("追放"), abstain_allowed=True, reveals_ballots=False
)


@dataclass(frozen=True)
class _Row:
    attempt: ActionAttempt
    kind: ActionKind
    exertion: Exertion
    startable_while_busy: bool
    copresence: tuple[CopresenceRequirement, ...]
    departed_too: bool

    def __str__(self) -> str:
        return self.kind.name


_TABLE = [
    _Row(TravelAttempt(ALICE, spot("shore")), ActionKind.TRAVEL, UsesBody(), False, (), True),
    _Row(
        SpeechAttempt(ALICE, OrdinaryVoice(), SpeechContent("おはよう")),
        ActionKind.SPEAK,
        DoesNotUseBody(),
        True,
        (),
        False,
    ),
    _Row(ListeningAttempt(ALICE), ActionKind.LISTEN, DoesNotUseBody(), False, (), True),
    _Row(WaitAttempt(ALICE, NoReason()), ActionKind.WAIT, DoesNotUseBody(), False, (), True),
    _Row(TendAttempt(ALICE, BOB), ActionKind.TEND, UsesBody(), False, (WithPerson(BOB),), False),
    _Row(
        ItemHandOverAttempt(ALICE, (Delivery(LAMP, BOB),), Openly()),
        ActionKind.HAND_OVER,
        UsesBody(),
        False,
        (WithPerson(BOB),),
        False,
    ),
    _Row(
        GroundItemPickupAttempt(ALICE, LAMP, Openly()),
        ActionKind.PICK_UP,
        UsesBody(),
        False,
        (WithGroundItem(LAMP),),
        False,
    ),
    _Row(ItemDropAttempt(ALICE, LAMP, Openly()), ActionKind.DROP, UsesBody(), False, (), False),
    _Row(SpotSearchAttempt(ALICE), ActionKind.SEARCH, UsesBody(), False, (), False),
    _Row(ItemUseAttempt(ALICE, LAMP), ActionKind.USE_ITEM, UsesBody(), False, (), False),
    _Row(
        EnterSectionAttempt(ALICE, SectionAccessForTests(CAGE, UsesBody())),
        ActionKind.ENTER_SECTION,
        UsesBody(),
        False,
        (),
        False,
    ),
    _Row(
        LeaveSectionAttempt(ALICE, SectionAccessForTests(CAGE, DoesNotUseBody())),
        ActionKind.LEAVE_SECTION,
        DoesNotUseBody(),
        False,
        (),
        False,
    ),
    _Row(HoldItemAttempt(ALICE, LAMP), ActionKind.HOLD, DoesNotUseBody(), False, (), False),
    _Row(PutAwayItemAttempt(ALICE, LAMP), ActionKind.PUT_AWAY, DoesNotUseBody(), False, (), False),
    _Row(
        GroupDecisionBallotAttempt(ALICE, EXILE, VoteFor(BOB)),
        ActionKind.CAST_BALLOT,
        DoesNotUseBody(),
        False,
        (),
        False,
    ),
]


def _stage(allowed: frozenset[ActionKind]) -> WorldStageDeclaration:
    return WorldStageDeclaration(
        stage_id=WorldStageId("night"),
        name=DisplayName("夜"),
        description=DescriptionText("夜の説明"),
        allowed_actions=allowed,
    )


class TestPropertiesOfBuiltInAttempts:
    """組み込みの行為の型が、action.md の「行為ごとの性質」の表の値を自分で答えることを保証する。"""

    @pytest.mark.parametrize("row", _TABLE, ids=str)
    def test_answers_its_kind(self, row: _Row) -> None:
        """行為の型は、表の行の ActionKind を kind() で答える。"""
        assert row.attempt.kind() is row.kind

    @pytest.mark.parametrize("row", _TABLE, ids=str)
    def test_answers_whether_it_uses_the_body(self, row: _Row) -> None:
        """行為の型は、表の「体を使う」の列を exertion() で答える。区画の出入りは渡した出入りの宣言の exertion を答える。"""
        assert row.attempt.exertion() == row.exertion

    @pytest.mark.parametrize("row", _TABLE, ids=str)
    def test_answers_whether_it_can_start_while_busy(self, row: _Row) -> None:
        """行為の型は、表の「最中でも始められる」の列を答える。真なのは話すことだけ。"""
        assert row.attempt.can_start_while_busy() is row.startable_while_busy

    @pytest.mark.parametrize("row", _TABLE, ids=str)
    def test_answers_whom_or_what_it_must_be_near(self, row: _Row) -> None:
        """行為の型は、表の「近くにいる必要」の列を copresence_requirements() で答える。"""
        assert row.attempt.copresence_requirements() == row.copresence

    @pytest.mark.parametrize("row", _TABLE, ids=str)
    def test_answers_whether_a_departed_person_may_do_it(self, row: _Row) -> None:
        """去った人にもできるのは移動・耳を澄ます・待つだけで、ほかの行為は LivingOnly を答える。"""
        expected = LivingOrDeparted() if row.departed_too else LivingOnly()

        assert row.attempt.actor_requirement() == expected

    @pytest.mark.parametrize("row", _TABLE, ids=str)
    def test_is_allowed_only_in_stages_listing_its_kind(self, row: _Row) -> None:
        """組み込みの行為は、段階の allowed_actions に自分の ActionKind があるときだけ許される。"""
        others = frozenset(ActionKind) - {row.kind}

        assert row.attempt.is_allowed_in(_stage(frozenset({row.kind})))
        assert not row.attempt.is_allowed_in(_stage(others))

    @pytest.mark.parametrize("row", _TABLE, ids=str)
    def test_answers_its_actor_as_the_acting_person(self, row: _Row) -> None:
        """行為の型は、行った人を actor、acting_person()、person_as(ACTOR) で同じく答える。"""
        assert row.attempt.actor == ALICE
        assert row.attempt.acting_person() == ALICE
        assert row.attempt.person_as(SubjectKind.ACTOR) == ALICE

    @pytest.mark.parametrize("row", _TABLE, ids=str)
    def test_built_in_attempts_take_no_arguments(self, row: _Row) -> None:
        """組み込みの行為は引数を持たず、argument() は ArgumentNotInTriggerException を投げる。"""
        with pytest.raises(ArgumentNotInTriggerException):
            row.attempt.argument(ArgumentName("words"))

    @pytest.mark.parametrize("row", _TABLE, ids=str)
    def test_fall_cause_is_struck_by_actor_for_others(self, row: _Row) -> None:
        """行為で傷ついたのが行った人以外なら StruckByPerson(行った人)、行った人自身なら WorldHappening を答える。"""
        assert row.attempt.fall_cause_for(BOB) == StruckByPerson(ALICE)
        assert row.attempt.fall_cause_for(ALICE) == WorldHappening()

    def test_all_actions_allowed_allows_every_built_in_attempt(self) -> None:
        """段階の allowed_actions が AllActionsAllowed なら、どの組み込みの行為も許される。"""
        stage = WorldStageDeclaration(
            stage_id=WorldStageId("day"),
            name=DisplayName("昼"),
            description=DescriptionText("昼の説明"),
            allowed_actions=AllActionsAllowed(),
        )

        assert all(row.attempt.is_allowed_in(stage) for row in _TABLE)


class TestWhisperNeedsTheListenerNearby:
    """話すことの近くにいる必要が、声の届き方で変わることを保証する。"""

    def test_whisper_requires_being_with_the_listener(self) -> None:
        """ささやき (Whisper) は相手と同じ場所にいる必要 (WithPerson) を答える。"""
        attempt = SpeechAttempt(ALICE, Whisper(BOB), SpeechContent("内緒だよ"))

        assert attempt.copresence_requirements() == (WithPerson(BOB),)

    def test_shout_requires_no_one_nearby(self) -> None:
        """叫ぶ (Shout) は誰の近くにいる必要も答えない。"""
        attempt = SpeechAttempt(ALICE, Shout(), SpeechContent("助けて"))

        assert attempt.copresence_requirements() == ()


class TestSubjectsAndItemsOfBuiltInAttempts:
    """組み込みの行為が、条件と効果の読む主語と品物を、持っているものだけ答えることを保証する。"""

    def test_tend_answers_its_target(self) -> None:
        """介抱 (TendAttempt) は person_as(TARGET) に介抱する相手を答える。"""
        assert TendAttempt(ALICE, BOB).person_as(SubjectKind.TARGET) == BOB

    @pytest.mark.parametrize(
        "attempt",
        [
            ItemUseAttempt(ALICE, LAMP),
            GroundItemPickupAttempt(ALICE, LAMP, Openly()),
            ItemDropAttempt(ALICE, LAMP, Openly()),
            HoldItemAttempt(ALICE, LAMP),
            PutAwayItemAttempt(ALICE, LAMP),
        ],
        ids=lambda attempt: attempt.kind().name,
    )
    def test_attempts_on_one_item_answer_the_item(self, attempt: ActionAttempt) -> None:
        """品物 1 つを扱う行為は、this_item() にその品物を答える。"""
        assert attempt.this_item() == LAMP

    def test_attempt_without_target_raises_for_target(self) -> None:
        """相手のいない行為 (探す) に person_as(TARGET) を尋ねると SubjectNotInTriggerException を投げる。"""
        with pytest.raises(SubjectNotInTriggerException):
            SpotSearchAttempt(ALICE).person_as(SubjectKind.TARGET)

    def test_hand_over_answers_no_single_item(self) -> None:
        """渡す (ItemHandOverAttempt) は品物を 1 つに決められないので、this_item() は ItemNotInTriggerException を投げる。"""
        attempt = ItemHandOverAttempt(ALICE, (Delivery(LAMP, BOB), Delivery(ROPE, CAROL)), Openly())

        with pytest.raises(ItemNotInTriggerException):
            attempt.this_item()


class TestHandOver:
    """渡す行為 (ItemHandOverAttempt) の届け先と、形の誤りを保証する。"""

    def test_requires_being_with_each_recipient_once(self) -> None:
        """複数の相手に渡すとき、相手ごとに 1 つずつ WithPerson を、最初に出てきた順に答える。"""
        attempt = ItemHandOverAttempt(
            ALICE, (Delivery(LAMP, BOB), Delivery(ROPE, CAROL), Delivery(ItemInstanceId("knife_1"), BOB)), Openly()
        )

        assert attempt.copresence_requirements() == (WithPerson(BOB), WithPerson(CAROL))

    def test_can_be_done_stealthily(self) -> None:
        """渡すことはこっそり (Stealthily) 行える。作るときに断らない。"""
        attempt = ItemHandOverAttempt(ALICE, (Delivery(LAMP, BOB),), Stealthily())

        assert attempt.manner == Stealthily()

    def test_without_deliveries_raises(self) -> None:
        """渡す品物が 1 件も無いと NoDeliveriesException を投げる。"""
        with pytest.raises(NoDeliveriesException):
            ItemHandOverAttempt(ALICE, (), Openly())


class TestTextsOfAttempts:
    """話す内容と待つ理由が、空の文を受け付けないことを保証する。"""

    @pytest.mark.parametrize("text", ["", "   "])
    def test_blank_speech_content_raises(self, text: str) -> None:
        """話す内容 (SpeechContent) に空や空白だけの文を渡すと BlankSpeechContentException を投げる。"""
        with pytest.raises(BlankSpeechContentException):
            SpeechContent(text)

    @pytest.mark.parametrize("text", ["", "   "])
    def test_blank_wait_reason_raises(self, text: str) -> None:
        """待つ理由 (WaitReason) に空や空白だけの文を渡すと BlankWaitReasonException を投げる。理由が無いときは NoReason を使う。"""
        with pytest.raises(BlankWaitReasonException):
            WaitReason(text)

    def test_abstain_ballot_is_accepted(self) -> None:
        """投票は棄権 (Abstain) でも作れる。棄権が許されるかは集団の決定の集約が確かめる。"""
        attempt = GroupDecisionBallotAttempt(ALICE, EXILE, Abstain())

        assert attempt.choice == Abstain()
