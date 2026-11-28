from __future__ import annotations

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.domain.action.action_refusal import WorldStateRefusal
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.exception.world_progress_exception import (
    BallotAlreadyCastException,
    GroupDecisionNotOpenException,
)
from ai_rpg_world.game_world.domain.people import TextAboutPeople, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.world_progress import Abstain, BallotCastEvent, VoteFor
from ai_rpg_world.game_world.domain.world_records import ActionAttemptFailedEvent
from tests.game_world.application.action.world_for_speech_and_ballot_tests import (
    HARU,
    NATSU,
    WorldForSpeechAndBallots,
)


class TestCastBallot:
    """CastBallot が、開いている投票にだけ票を入れることを保証する。"""

    def test_ballot_in_open_vote_is_cast(self) -> None:
        """開いている投票に投じると ActionDone が返り、投じた票の BallotCastEvent が残る。"""
        world = WorldForSpeechAndBallots()
        world.open_exile_vote()

        reply = world.vote(HARU, VoteFor(NATSU))

        assert isinstance(reply, ActionDone)
        [cast] = [event for event in world.events() if isinstance(event, BallotCastEvent)]
        assert (cast.voter, cast.choice) == (HARU, VoteFor(NATSU))

    def test_ballot_for_a_person_names_them_in_the_summary(self) -> None:
        """ハルがナツに投票すると、返事の要約は、投票先の {target} にナツを当てた文になる。"""
        world = WorldForSpeechAndBallots()
        world.open_exile_vote()

        reply = world.vote(HARU, VoteFor(NATSU))

        assert isinstance(reply, ActionDone)
        assert reply.outcome.summary == TextAboutPeople(
            TextWithUnassignedPeople("vote_forした {target}"), {"target": NATSU}
        )

    def test_ballot_in_vote_not_open_is_refused(self) -> None:
        """開いていない投票に投じると GROUP_DECISION_NOT_OPEN で断られ、失敗の記録だけが残る。"""
        world = WorldForSpeechAndBallots()

        reply = world.vote(HARU, VoteFor(NATSU))

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == WorldStateRefusal(RefusalCode(GroupDecisionNotOpenException.error_code))
        assert [type(event) for event in world.events()] == [ActionAttemptFailedEvent]

    def test_second_ballot_is_refused_and_keeps_the_first(self) -> None:
        """投じた人が、投票の行っているあいだが過ぎてからもう一度投じると BALLOT_ALREADY_CAST で断られ、BallotCastEvent は最初の票の 1 つだけ。"""
        world = WorldForSpeechAndBallots()
        world.open_exile_vote()
        world.vote(HARU, VoteFor(NATSU))
        world.pass_ticks_of(ActionKind.CAST_BALLOT)

        reply = world.vote(HARU, Abstain())

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == WorldStateRefusal(RefusalCode(BallotAlreadyCastException.error_code))
        casts = [event for event in world.events() if isinstance(event, BallotCastEvent)]
        assert [(cast.voter, cast.choice) for cast in casts] == [(HARU, VoteFor(NATSU))]
