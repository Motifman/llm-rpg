from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.exception.action_exception import UndeclaredNounException
from ai_rpg_world.game_world.domain.exception.game_world_exception import RepeatedMementoKeyException
from ai_rpg_world.game_world.domain.exception.world_progress_exception import (
    AbstainNotAllowedException,
    BallotAlreadyCastException,
    ChoiceNotInDecisionException,
    GroupDecisionAlreadyOpenException,
    GroupDecisionLeftOpenAfterEveryoneCastException,
    GroupDecisionNotOpenException,
    NoChoicesGivenException,
    NoVotersGivenException,
    VoterNotInDecisionException,
)
from ai_rpg_world.game_world.domain.value_object import DisplayName, GroupDecisionId, PersonId
from ai_rpg_world.game_world.domain.world_progress import (
    Abstain,
    Ballot,
    BallotCastEvent,
    ChoiceWithdrawnEvent,
    GroupDecision,
    GroupDecisionMemento,
    GroupDecisionReachedEvent,
    GroupDecisionStartedEvent,
    GroupDecisionUnresolvedEvent,
    VoteFor,
    VoterWithdrawnEvent,
)
from tests.game_world.support.memento_for_tests import rebuilt_from_memento
from tests.game_world.support.verb_declarations_for_tests import everyone_votes_on
from tests.game_world.support.world_design_for_tests import compose_world, nouns

_DECISION = GroupDecisionId("exile_vote")
_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_CAROL = PersonId("carol")
_DAVE = PersonId("dave")


def _declaration(*, abstain_allowed: bool = True) -> GroupDecisionDeclaration:
    return GroupDecisionDeclaration(
        decision_id=_DECISION,
        name=DisplayName("追放の投票"),
        abstain_allowed=abstain_allowed,
        reveals_ballots=False,
    )


def _design_with(declaration: GroupDecisionDeclaration) -> WorldDesign:
    return compose_world(nouns(group_decisions=(declaration,)), group_decision_rules=(everyone_votes_on(declaration),))


def _decision(*, abstain_allowed: bool = True) -> GroupDecision:
    return GroupDecision.not_started(_declaration(abstain_allowed=abstain_allowed))


def _started(
    voters: frozenset[PersonId] = frozenset({_ALICE, _BOB, _CAROL}),
    choices: frozenset[PersonId] = frozenset({_ALICE, _BOB, _CAROL}),
    *,
    abstain_allowed: bool = True,
) -> GroupDecision:
    decision = _decision(abstain_allowed=abstain_allowed)
    decision.start(voters, choices)
    decision.clear_events()
    return decision


def _last_event(decision: GroupDecision) -> object:
    return decision.get_events()[-1]


class TestGroupDecisionStart:
    """GroupDecision.start が投票する人と候補を決めて決定を開き、開けない始め方を断ることを保証する。"""

    def test_decision_is_not_open_before_start(self) -> None:
        """作ったばかりの決定は開いていない。"""
        assert _decision().is_open() is False

    def test_start_opens_and_records_started_event(self) -> None:
        """start すると開き、決定の ID と投票する人と候補を持つ GroupDecisionStartedEvent をためる。"""
        decision = _decision()

        decision.start(frozenset({_ALICE, _BOB}), frozenset({_CAROL}))

        assert decision.is_open() is True
        [event] = decision.get_events()
        assert isinstance(event, GroupDecisionStartedEvent)
        assert (event.decision_id, event.voters, event.choices) == (
            _DECISION,
            frozenset({_ALICE, _BOB}),
            frozenset({_CAROL}),
        )

    def test_start_while_open_raises_and_records_nothing(self) -> None:
        """開いているうちにもう一度 start すると GroupDecisionAlreadyOpenException を投げ、イベントを足さない。"""
        decision = _started()

        with pytest.raises(GroupDecisionAlreadyOpenException):
            decision.start(frozenset({_ALICE}), frozenset({_BOB}))

        assert decision.get_events() == []

    def test_start_without_voters_raises(self) -> None:
        """投票する人が空の start は NoVotersGivenException で断り、開かない。"""
        decision = _decision()

        with pytest.raises(NoVotersGivenException):
            decision.start(frozenset(), frozenset({_BOB}))

        assert decision.is_open() is False

    def test_start_without_choices_raises(self) -> None:
        """候補が空の start は NoChoicesGivenException で断り、開かない。"""
        decision = _decision()

        with pytest.raises(NoChoicesGivenException):
            decision.start(frozenset({_ALICE}), frozenset())

        assert decision.is_open() is False

    def test_can_start_again_with_fresh_ballots_after_tally(self) -> None:
        """集計して閉じた決定は start し直せ、前の票は残らない。"""
        decision = _started(frozenset({_ALICE}), frozenset({_BOB}))
        decision.cast(_ALICE, VoteFor(_BOB))

        decision.start(frozenset({_ALICE}), frozenset({_BOB, _CAROL}))
        decision.cast(_ALICE, VoteFor(_CAROL))

        event = _last_event(decision)
        assert isinstance(event, GroupDecisionReachedEvent)
        assert event.chosen == _CAROL


class TestGroupDecisionCastRefusals:
    """GroupDecision.cast が文書の決まりに合わない票を断り、そのときイベントを出さないことを保証する。"""

    def test_cast_before_start_raises(self) -> None:
        """開いていない決定への票は GroupDecisionNotOpenException で断る。"""
        with pytest.raises(GroupDecisionNotOpenException):
            _decision().cast(_ALICE, VoteFor(_BOB))

    def test_cast_by_non_voter_raises_and_records_nothing(self) -> None:
        """投票する人にいない人の票は VoterNotInDecisionException で断り、イベントを足さない。"""
        decision = _started()

        with pytest.raises(VoterNotInDecisionException):
            decision.cast(_DAVE, VoteFor(_ALICE))

        assert decision.get_events() == []

    def test_second_ballot_raises_and_keeps_first(self) -> None:
        """同じ人の二度目の票は BallotAlreadyCastException で断り、1 票目は変わらない。"""
        decision = _started()
        decision.cast(_ALICE, VoteFor(_BOB))

        with pytest.raises(BallotAlreadyCastException):
            decision.cast(_ALICE, VoteFor(_CAROL))

        decision.cast(_BOB, VoteFor(_BOB))
        decision.cast(_CAROL, VoteFor(_CAROL))
        event = _last_event(decision)
        assert isinstance(event, GroupDecisionReachedEvent)
        assert Ballot(_ALICE, VoteFor(_BOB)) in event.ballots

    def test_vote_for_non_choice_raises(self) -> None:
        """候補にいない人への票は ChoiceNotInDecisionException で断る。"""
        decision = _started(choices=frozenset({_BOB}))

        with pytest.raises(ChoiceNotInDecisionException):
            decision.cast(_ALICE, VoteFor(_DAVE))

    def test_abstain_when_not_allowed_raises(self) -> None:
        """abstain_allowed が偽の決定での棄権は AbstainNotAllowedException で断る。"""
        decision = _started(abstain_allowed=False)

        with pytest.raises(AbstainNotAllowedException):
            decision.cast(_ALICE, Abstain())

        assert decision.get_events() == []


class TestGroupDecisionCast:
    """GroupDecision.cast が票を受けてイベントにし、全員が投じたらその場で集計することを保証する。"""

    def test_cast_records_ballot_cast_event(self) -> None:
        """票は、決定の ID と投じた人と票を持つ BallotCastEvent になる。"""
        decision = _started()

        decision.cast(_ALICE, VoteFor(_BOB))

        [event] = decision.get_events()
        assert isinstance(event, BallotCastEvent)
        assert (event.decision_id, event.voter, event.choice) == (_DECISION, _ALICE, VoteFor(_BOB))

    def test_does_not_tally_until_everyone_has_cast(self) -> None:
        """3 人のうち 2 人が投じただけでは集計せず、開いたまま。"""
        decision = _started()

        decision.cast(_ALICE, VoteFor(_BOB))
        decision.cast(_BOB, VoteFor(_CAROL))

        assert decision.is_open() is True
        assert all(isinstance(event, BallotCastEvent) for event in decision.get_events())

    def test_single_top_choice_beating_abstentions_is_reached(self) -> None:
        """全員が投じ、最多の bob が 1 人で棄権より多ければ、bob と票の内訳を持つ GroupDecisionReachedEvent をためて閉じる。"""
        decision = _started()

        decision.cast(_ALICE, VoteFor(_BOB))
        decision.cast(_BOB, Abstain())
        decision.cast(_CAROL, VoteFor(_BOB))

        event = _last_event(decision)
        assert isinstance(event, GroupDecisionReachedEvent)
        assert (event.decision_id, event.chosen) == (_DECISION, _BOB)
        assert event.ballots == frozenset(
            {Ballot(_ALICE, VoteFor(_BOB)), Ballot(_BOB, Abstain()), Ballot(_CAROL, VoteFor(_BOB))}
        )
        assert decision.is_open() is False

    def test_tie_for_top_is_unresolved(self) -> None:
        """最多が 2 人に並ぶと、票の内訳を持つ GroupDecisionUnresolvedEvent をためて閉じる。"""
        decision = _started(frozenset({_ALICE, _BOB}))

        decision.cast(_ALICE, VoteFor(_BOB))
        decision.cast(_BOB, VoteFor(_CAROL))

        event = _last_event(decision)
        assert isinstance(event, GroupDecisionUnresolvedEvent)
        assert event.ballots == frozenset({Ballot(_ALICE, VoteFor(_BOB)), Ballot(_BOB, VoteFor(_CAROL))})
        assert decision.is_open() is False

    def test_top_choice_not_beating_abstentions_is_unresolved(self) -> None:
        """最多が 1 人でも、その票数が棄権の数と同じなら GroupDecisionUnresolvedEvent になる。"""
        decision = _started(frozenset({_ALICE, _BOB}))

        decision.cast(_ALICE, VoteFor(_BOB))
        decision.cast(_BOB, Abstain())

        assert isinstance(_last_event(decision), GroupDecisionUnresolvedEvent)

    def test_majority_of_split_votes_is_reached(self) -> None:
        """3 人が bob 2 票・carol 1 票に分かれると、bob に決まる。"""
        decision = _started()

        decision.cast(_ALICE, VoteFor(_BOB))
        decision.cast(_BOB, VoteFor(_CAROL))
        decision.cast(_CAROL, VoteFor(_BOB))

        event = _last_event(decision)
        assert isinstance(event, GroupDecisionReachedEvent)
        assert event.chosen == _BOB

    def test_top_choice_outnumbered_by_abstentions_is_unresolved(self) -> None:
        """bob への 1 票より棄権の 2 票が多いと、GroupDecisionUnresolvedEvent になる。"""
        decision = _started()

        decision.cast(_ALICE, VoteFor(_BOB))
        decision.cast(_BOB, Abstain())
        decision.cast(_CAROL, Abstain())

        assert isinstance(_last_event(decision), GroupDecisionUnresolvedEvent)

    def test_everyone_abstaining_is_unresolved(self) -> None:
        """全員が棄権すると、GroupDecisionUnresolvedEvent になる。"""
        decision = _started(frozenset({_ALICE, _BOB}))

        decision.cast(_ALICE, Abstain())
        decision.cast(_BOB, Abstain())

        assert isinstance(_last_event(decision), GroupDecisionUnresolvedEvent)

    def test_cast_after_tally_raises(self) -> None:
        """集計して閉じた決定への票は GroupDecisionNotOpenException で断る。"""
        decision = _started(frozenset({_ALICE}))
        decision.cast(_ALICE, VoteFor(_BOB))

        with pytest.raises(GroupDecisionNotOpenException):
            decision.cast(_ALICE, VoteFor(_CAROL))


class TestGroupDecisionWithdrawChoice:
    """GroupDecision.withdraw_choice が候補を外し、その人への票を投じた人に戻すことを保証する。"""

    def test_records_event_with_voters_whose_ballots_returned(self) -> None:
        """bob を外すと、決定の ID と bob と、bob に入れていた alice を持つ ChoiceWithdrawnEvent をためる。"""
        decision = _started()
        decision.cast(_ALICE, VoteFor(_BOB))
        decision.cast(_BOB, VoteFor(_CAROL))
        decision.clear_events()

        decision.withdraw_choice(_BOB)

        [event] = decision.get_events()
        assert isinstance(event, ChoiceWithdrawnEvent)
        assert (event.decision_id, event.choice, event.returned_to) == (_DECISION, _BOB, frozenset({_ALICE}))

    def test_returned_voter_can_cast_again(self) -> None:
        """候補から外した人に入っていた票は投じた人に戻り、その人は投じ直せる。"""
        decision = _started()
        decision.cast(_ALICE, VoteFor(_BOB))
        decision.cast(_BOB, VoteFor(_CAROL))

        decision.withdraw_choice(_BOB)
        decision.cast(_ALICE, VoteFor(_CAROL))
        decision.cast(_CAROL, VoteFor(_CAROL))

        event = _last_event(decision)
        assert isinstance(event, GroupDecisionReachedEvent)
        assert Ballot(_ALICE, VoteFor(_CAROL)) in event.ballots

    def test_withdrawn_choice_can_no_longer_be_voted_for(self) -> None:
        """外した候補への票は ChoiceNotInDecisionException で断る。"""
        decision = _started()

        decision.withdraw_choice(_BOB)

        with pytest.raises(ChoiceNotInDecisionException):
            decision.cast(_ALICE, VoteFor(_BOB))

    def test_withdrawing_unknown_choice_changes_nothing(self) -> None:
        """候補にいない人を外しても状態は変わらないので、断らず、イベントもためない。"""
        decision = _started()

        decision.withdraw_choice(_DAVE)

        assert decision.get_events() == []
        assert decision.is_open() is True

    def test_withdrawing_last_choice_keeps_decision_open_until_close(self) -> None:
        """最後の候補を外しても決定は開いたままで、棄権を受け、close で GroupDecisionUnresolvedEvent になる。"""
        decision = _started(frozenset({_ALICE, _BOB}), frozenset({_CAROL}))

        decision.withdraw_choice(_CAROL)
        decision.cast(_ALICE, Abstain())

        assert decision.is_open() is True
        decision.close()
        assert isinstance(_last_event(decision), GroupDecisionUnresolvedEvent)

    def test_withdrawing_choice_from_closed_decision_changes_nothing(self) -> None:
        """開いていない決定から候補を外しても、断らず、イベントもためない。"""
        decision = _decision()

        decision.withdraw_choice(_BOB)

        assert decision.get_events() == []


class TestGroupDecisionWithdrawVoter:
    """GroupDecision.withdraw_voter が投票する人を外し、その人の票を数えず、残りが投じ済みならその場で集計することを保証する。"""

    def test_records_voter_withdrawn_event(self) -> None:
        """alice を外すと、決定の ID と alice を持つ VoterWithdrawnEvent をためる。"""
        decision = _started()

        decision.withdraw_voter(_ALICE)

        [event] = decision.get_events()
        assert isinstance(event, VoterWithdrawnEvent)
        assert (event.decision_id, event.voter) == (_DECISION, _ALICE)

    def test_tallies_when_remaining_voters_have_all_cast(self) -> None:
        """alice の票を待っているときに alice を外すと、残りの票でその場で集計する。"""
        decision = _started()
        decision.cast(_BOB, VoteFor(_CAROL))
        decision.cast(_CAROL, VoteFor(_CAROL))

        decision.withdraw_voter(_ALICE)

        event = _last_event(decision)
        assert isinstance(event, GroupDecisionReachedEvent)
        assert event.chosen == _CAROL

    def test_ballot_of_withdrawn_voter_is_not_counted(self) -> None:
        """外した人が投じていた票は、集計の内訳にも数にも入らない。"""
        decision = _started()
        decision.cast(_ALICE, VoteFor(_BOB))
        decision.cast(_BOB, VoteFor(_CAROL))

        decision.withdraw_voter(_ALICE)
        decision.cast(_CAROL, VoteFor(_CAROL))

        event = _last_event(decision)
        assert isinstance(event, GroupDecisionReachedEvent)
        assert event.chosen == _CAROL
        assert event.ballots == frozenset({Ballot(_BOB, VoteFor(_CAROL)), Ballot(_CAROL, VoteFor(_CAROL))})

    def test_withdrawing_every_voter_is_unresolved_with_no_ballots(self) -> None:
        """投票する人を全員外すと、票の無い GroupDecisionUnresolvedEvent をためて閉じる。"""
        decision = _started(frozenset({_ALICE}))

        decision.withdraw_voter(_ALICE)

        event = _last_event(decision)
        assert isinstance(event, GroupDecisionUnresolvedEvent)
        assert event.ballots == frozenset()
        assert decision.is_open() is False

    def test_withdrawing_unknown_voter_changes_nothing(self) -> None:
        """投票する人にいない人を外しても状態は変わらないので、断らず、イベントもためず、集計もしない。"""
        decision = _started()

        decision.withdraw_voter(_DAVE)

        assert decision.get_events() == []
        assert decision.is_open() is True

    def test_withdrawing_voter_twice_changes_nothing_the_second_time(self) -> None:
        """倒れてから死んだ人のように同じ人を 2 回外しても、2 回目は断らず、イベントもためない。"""
        decision = _started()
        decision.withdraw_voter(_ALICE)
        decision.clear_events()

        decision.withdraw_voter(_ALICE)

        assert decision.get_events() == []

    def test_withdrawing_voter_from_closed_decision_changes_nothing(self) -> None:
        """開いていない決定から投票する人を外しても、断らず、イベントもためない。"""
        decision = _decision()

        decision.withdraw_voter(_ALICE)

        assert decision.get_events() == []


class TestGroupDecisionClose:
    """GroupDecision.close が、全員を待たずにそれまでの票で集計することを保証する。"""

    def test_close_tallies_ballots_cast_so_far(self) -> None:
        """3 人のうち alice だけが bob に入れたところで close すると、bob に決まって閉じる。"""
        decision = _started()
        decision.cast(_ALICE, VoteFor(_BOB))

        decision.close()

        event = _last_event(decision)
        assert isinstance(event, GroupDecisionReachedEvent)
        assert event.chosen == _BOB
        assert decision.is_open() is False

    def test_close_without_ballots_is_unresolved(self) -> None:
        """誰も投じないまま close すると GroupDecisionUnresolvedEvent になる。"""
        decision = _started()

        decision.close()

        assert isinstance(_last_event(decision), GroupDecisionUnresolvedEvent)

    def test_close_before_start_changes_nothing(self) -> None:
        """始まっていない決定の close は、断らず、イベントもためない。"""
        decision = _decision()

        decision.close()

        assert decision.get_events() == []
        assert decision.is_open() is False

    def test_close_after_automatic_tally_changes_nothing(self) -> None:
        """全員が投じて集計し終えた決定を、締める出来事がもう一度 close しても、断らず、集計のイベントを足さない。"""
        decision = _started(frozenset({_ALICE}))
        decision.cast(_ALICE, VoteFor(_BOB))
        events_after_tally = decision.get_events()

        decision.close()

        assert decision.get_events() == events_after_tally


class TestGroupDecisionIdentity:
    """GroupDecision が、集団の決定の宣言の ID を自分の ID として持つことを保証する。"""

    def test_keeps_decision_id_of_declaration(self) -> None:
        """宣言の decision_id を decision_id として持つ。"""
        assert _decision().decision_id == _DECISION


class TestGroupDecisionMemento:
    """GroupDecision を memento から作り直すと、開いているか・投票する人・候補・入った票が元と同じになることを保証する。"""

    def test_rebuilt_open_decision_continues_the_same_vote(self) -> None:
        """alice が bob に入れ、候補から carol が外れた決定を作り直すと、alice は入れ直せず、残りの bob と carol が入れると bob に決まる。"""
        decision = _started()
        decision.cast(_ALICE, VoteFor(_BOB))
        decision.withdraw_choice(_CAROL)
        design = _design_with(_declaration())

        rebuilt = rebuilt_from_memento(decision, design)

        assert rebuilt.memento() == decision.memento()
        assert rebuilt.is_open() is True
        with pytest.raises(BallotAlreadyCastException):
            rebuilt.cast(_ALICE, VoteFor(_ALICE))
        with pytest.raises(ChoiceNotInDecisionException):
            rebuilt.cast(_BOB, VoteFor(_CAROL))
        rebuilt.cast(_BOB, VoteFor(_BOB))
        rebuilt.cast(_CAROL, VoteFor(_ALICE))
        assert rebuilt.is_open() is False
        reached = _last_event(rebuilt)
        assert isinstance(reached, GroupDecisionReachedEvent) and reached.chosen == _BOB

    def test_rebuilt_decision_keeps_whether_abstaining_is_allowed_from_the_declaration(self) -> None:
        """棄権を許さない宣言から作り直した決定は、棄権を AbstainNotAllowedException で断る。"""
        decision = _started(abstain_allowed=False)
        design = _design_with(_declaration(abstain_allowed=False))

        rebuilt = rebuilt_from_memento(decision, design)

        with pytest.raises(AbstainNotAllowedException):
            rebuilt.cast(_ALICE, Abstain())

    def test_rebuilding_records_no_event(self) -> None:
        """票が入ったあとの memento から作り直しても、作り直したものはイベントをためていない。"""
        decision = _started()
        decision.cast(_ALICE, VoteFor(_BOB))
        design = _design_with(_declaration())

        assert rebuilt_from_memento(decision, design).get_events() == []

    def test_memento_of_an_undeclared_decision_is_rejected(self) -> None:
        """宣言に無い集団の決定の memento から作り直すと UndeclaredNounException を投げる。"""
        with pytest.raises(UndeclaredNounException):
            GroupDecision.from_memento(_started().memento(), compose_world())

    def test_memento_with_two_ballots_of_one_voter_is_rejected(self) -> None:
        """alice の票が bob への票と棄権の 2 つある memento は、作るときに RepeatedMementoKeyException を投げる。"""
        with pytest.raises(RepeatedMementoKeyException):
            GroupDecisionMemento(
                decision_id=_DECISION,
                open=True,
                voters=frozenset({_ALICE, _BOB}),
                choices=frozenset({_BOB}),
                ballots=frozenset({Ballot(_ALICE, VoteFor(_BOB)), Ballot(_ALICE, Abstain())}),
            )


def _memento(
    *,
    open: bool = True,
    voters: frozenset[PersonId] = frozenset({_ALICE, _BOB}),
    choices: frozenset[PersonId] = frozenset({_ALICE, _BOB}),
    ballots: frozenset[Ballot] = frozenset(),
) -> GroupDecisionMemento:
    return GroupDecisionMemento(decision_id=_DECISION, open=open, voters=voters, choices=choices, ballots=ballots)


class TestGroupDecisionRebuiltOnlyIntoStatesOperationsReach:
    """GroupDecision を memento から作り直すとき、投票の操作では作れない状態を、操作が断るときと同じ例外で断ることを保証する。"""

    def test_ballot_of_someone_who_is_not_a_voter_is_rejected(self) -> None:
        """投票する人が alice と bob の決定に、dave の票が入った memento から作り直すと VoterNotInDecisionException を投げる。"""
        memento = _memento(ballots=frozenset({Ballot(_DAVE, VoteFor(_ALICE))}))

        with pytest.raises(VoterNotInDecisionException):
            GroupDecision.from_memento(memento, _design_with(_declaration()))

    def test_vote_for_someone_who_is_not_a_choice_is_rejected(self) -> None:
        """候補が alice と bob の決定に、carol への票が入った memento から作り直すと ChoiceNotInDecisionException を投げる。"""
        memento = _memento(ballots=frozenset({Ballot(_ALICE, VoteFor(_CAROL))}))

        with pytest.raises(ChoiceNotInDecisionException):
            GroupDecision.from_memento(memento, _design_with(_declaration()))

    def test_abstention_where_the_declaration_forbids_it_is_rejected(self) -> None:
        """棄権を許さない宣言で、alice の棄権が入った memento から作り直すと AbstainNotAllowedException を投げる。"""
        memento = _memento(ballots=frozenset({Ballot(_ALICE, Abstain())}))

        with pytest.raises(AbstainNotAllowedException):
            GroupDecision.from_memento(memento, _design_with(_declaration(abstain_allowed=False)))

    def test_open_decision_without_voters_is_rejected(self) -> None:
        """投票する人がいないのに開いている memento から作り直すと NoVotersGivenException を投げる。"""
        memento = _memento(voters=frozenset())

        with pytest.raises(NoVotersGivenException):
            GroupDecision.from_memento(memento, _design_with(_declaration()))

    def test_open_decision_where_every_voter_has_cast_is_rejected(self) -> None:
        """alice と bob の 2 人とも票を入れたのに開いている memento から作り直すと GroupDecisionLeftOpenAfterEveryoneCastException を投げる。"""
        memento = _memento(ballots=frozenset({Ballot(_ALICE, VoteFor(_BOB)), Ballot(_BOB, VoteFor(_BOB))}))

        with pytest.raises(GroupDecisionLeftOpenAfterEveryoneCastException):
            GroupDecision.from_memento(memento, _design_with(_declaration()))

    def test_closed_decision_where_every_voter_has_cast_is_rebuilt(self) -> None:
        """alice と bob の 2 人とも票を入れて閉じた memento は作り直せ、閉じたままになる。"""
        memento = _memento(open=False, ballots=frozenset({Ballot(_ALICE, VoteFor(_BOB)), Ballot(_BOB, VoteFor(_BOB))}))

        rebuilt = GroupDecision.from_memento(memento, _design_with(_declaration()))

        assert rebuilt.memento() == memento
        assert rebuilt.is_open() is False
