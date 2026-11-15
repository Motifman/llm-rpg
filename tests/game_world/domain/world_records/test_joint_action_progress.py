from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.action.built_in_attempts import WaitAttempt
from ai_rpg_world.game_world.domain.action.interaction_attempts import ObjectInteractionAttempt
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.action.refusal_code import NoRefusal, RefusalCode
from ai_rpg_world.game_world.domain.action.wait_reason import WaitReason
from ai_rpg_world.game_world.domain.declaration.verb.happening_notice import NoNotice
from ai_rpg_world.game_world.domain.declaration.verb.joint_action_declaration import JointActionDeclaration
from ai_rpg_world.game_world.domain.effect.combined_effects import NoEffect
from ai_rpg_world.game_world.domain.exception.game_world_exception import RepeatedMementoKeyException
from ai_rpg_world.game_world.domain.exception.world_records_exception import (
    JointActionNotSettlingException,
    JointActionUnsettledException,
)
from ai_rpg_world.game_world.domain.value_object import InteractionId, ObjectId, PersonId, Ticks, WorldId, WorldTick
from ai_rpg_world.game_world.domain.value_object.joint_action_id import JointActionId
from ai_rpg_world.game_world.domain.world_records import (
    JointActionCompletedEvent,
    JointActionPartDoneBy,
    JointActionProgress,
    JointActionSettlement,
    JointActionTimedOutEvent,
    ScenarioProgress,
    ScenarioProgressMemento,
)
from tests.game_world.domain.whereabouts._builders import thing
from tests.game_world.support.declarations_for_tests import InteractionForTests
from tests.game_world.support.memento_for_tests import rebuilt_from_memento

_WORLD = WorldId("mine")
_HARU = PersonId("haru")
_NATSU = PersonId("natsu")
_PUSH = InteractionId("push")
_LEFT = ObjectId("left_lever")
_RIGHT = ObjectId("right_lever")
_PACK_FULL = RefusalCode("PERSON_INVENTORY.PACK_FULL")


def _levers(*, distinct_people: bool = True, joint_id: str = "levers") -> JointActionDeclaration:
    return JointActionDeclaration(
        joint_id=JointActionId(joint_id),
        required=((_LEFT, _PUSH), (_RIGHT, _PUSH)),
        window=Ticks(2),
        distinct_people=distinct_people,
        on_complete=NoEffect(),
        on_timeout=NoEffect(),
        complete_notice=NoNotice(),
        timeout_notice=NoNotice(),
    )


_LEVERS = _levers()


def _push(who: PersonId, lever: ObjectId) -> ObjectInteractionAttempt:
    return ObjectInteractionAttempt(
        actor=who,
        obj=thing(lever.value, "shaft"),
        interaction=InteractionForTests(_PUSH),
        arguments={},
        manner=Openly(),
    )


def _pushed(progress: ScenarioProgress, *pushes: tuple[int, PersonId, ObjectId]) -> None:
    for at, who, lever in pushes:
        attempt: ActionAttempt = _push(who, lever)
        progress.note_joint_action_part_done(attempt, (_LEVERS,), WorldTick(at))


class TestJointActionWindow:
    """最初の一押しの tick から窓の中で全部の部分が埋まれば揃い、窓を過ぎれば時間切れになり、どちらでも帳簿が空に戻ることを保証する。"""

    def test_nothing_settles_before_anyone_pushes(self) -> None:
        """誰も梃子を押していないとき、どの tick でも揃いも時間切れも起きない。"""
        progress = ScenarioProgress.start(_WORLD)

        assert progress.joint_action_settlement(_LEVERS, WorldTick(100)) is JointActionSettlement.UNDECIDED

    def test_one_lever_alone_does_not_complete(self) -> None:
        """ハルが tick 5 に左だけを押したとき、tick 5 から窓の終わりの tick 7 までは揃いも時間切れも起きない。"""
        progress = ScenarioProgress.start(_WORLD)

        _pushed(progress, (5, _HARU, _LEFT))

        assert progress.joint_action_settlement(_LEVERS, WorldTick(5)) is JointActionSettlement.UNDECIDED
        assert progress.joint_action_settlement(_LEVERS, WorldTick(7)) is JointActionSettlement.UNDECIDED

    def test_both_levers_within_the_window_complete(self) -> None:
        """ハルが tick 5 に左、ナツが tick 7 に右を押すと、tick 7 に揃う。"""
        progress = ScenarioProgress.start(_WORLD)

        _pushed(progress, (5, _HARU, _LEFT), (7, _NATSU, _RIGHT))

        assert progress.joint_action_settlement(_LEVERS, WorldTick(7)) is JointActionSettlement.COMPLETED

    def test_completion_within_the_window_stays_completed_after_it(self) -> None:
        """ハル tick 5 左・ナツ tick 7 右で揃ったまま落ち着かせずに tick 8 に問われても、時間切れではなく揃いを返す。部分は窓の中でしか書けないため。"""
        progress = ScenarioProgress.start(_WORLD)

        _pushed(progress, (5, _HARU, _LEFT), (7, _NATSU, _RIGHT))

        assert progress.joint_action_settlement(_LEVERS, WorldTick(8)) is JointActionSettlement.COMPLETED

    def test_one_lever_times_out_after_the_window(self) -> None:
        """ハルが tick 5 に左だけを押したとき、窓を過ぎた tick 8 に時間切れになる。"""
        progress = ScenarioProgress.start(_WORLD)

        _pushed(progress, (5, _HARU, _LEFT))

        assert progress.joint_action_settlement(_LEVERS, WorldTick(8)) is JointActionSettlement.TIMED_OUT

    def test_push_after_timeout_starts_a_new_try(self) -> None:
        """tick 8 の時間切れを落ち着かせてからナツが tick 8 に右を押すと、それが新しい試みの 1 つ目になり、tick 10 までは何も起きず、tick 11 に時間切れになる。"""
        progress = ScenarioProgress.start(_WORLD)
        _pushed(progress, (5, _HARU, _LEFT))
        progress.note_joint_action_settled(_LEVERS, WorldTick(8), frozenset(), NoRefusal())

        _pushed(progress, (8, _NATSU, _RIGHT))

        assert progress.joint_action_settlement(_LEVERS, WorldTick(8)) is JointActionSettlement.UNDECIDED
        assert progress.joint_action_settlement(_LEVERS, WorldTick(10)) is JointActionSettlement.UNDECIDED
        assert progress.joint_action_settlement(_LEVERS, WorldTick(11)) is JointActionSettlement.TIMED_OUT

    def test_push_before_the_timeout_is_settled_is_refused(self) -> None:
        """ハルの tick 5 の左が tick 8 に時間切れになったのに落ち着かせないまま、ナツの右を書こうとすると JointActionUnsettledException を投げ、帳簿は時間切れのまま残る。"""
        progress = ScenarioProgress.start(_WORLD)
        _pushed(progress, (5, _HARU, _LEFT))

        with pytest.raises(JointActionUnsettledException):
            _pushed(progress, (8, _NATSU, _RIGHT))

        assert progress.joint_action_settlement(_LEVERS, WorldTick(8)) is JointActionSettlement.TIMED_OUT

    def test_pushing_again_does_not_extend_the_window(self) -> None:
        """ハルが tick 5 と tick 7 に左を押し直しても、窓の起点は tick 5 のままで、tick 8 に時間切れになる。"""
        progress = ScenarioProgress.start(_WORLD)

        _pushed(progress, (5, _HARU, _LEFT), (7, _HARU, _LEFT))

        assert progress.joint_action_settlement(_LEVERS, WorldTick(8)) is JointActionSettlement.TIMED_OUT


class TestJointActionDistinctPeople:
    """部分ごとに最後に行った人を覚え、distinct_people なら覚えている人が全員違うときだけ揃うことを保証する。"""

    def test_one_person_on_both_levers_does_not_complete(self) -> None:
        """ハルが左、続けてハルが右を押すと、左ハル・右ハルで揃わない。"""
        progress = ScenarioProgress.start(_WORLD)

        _pushed(progress, (5, _HARU, _LEFT), (6, _HARU, _RIGHT))

        assert progress.joint_action_settlement(_LEVERS, WorldTick(6)) is JointActionSettlement.UNDECIDED

    def test_another_person_on_the_right_replaces_and_completes(self) -> None:
        """左ハル・右ハルのあとナツが右を押すと、右がナツに替わり、揃う。"""
        progress = ScenarioProgress.start(_WORLD)

        _pushed(progress, (5, _HARU, _LEFT), (6, _HARU, _RIGHT), (7, _NATSU, _RIGHT))

        assert progress.joint_action_settlement(_LEVERS, WorldTick(7)) is JointActionSettlement.COMPLETED

    def test_another_person_on_the_left_replaces_and_completes(self) -> None:
        """左ハル・右ハルのあとナツが左を押すと、左がナツに替わり、揃う。"""
        progress = ScenarioProgress.start(_WORLD)

        _pushed(progress, (5, _HARU, _LEFT), (6, _HARU, _RIGHT), (7, _NATSU, _LEFT))

        assert progress.joint_action_settlement(_LEVERS, WorldTick(7)) is JointActionSettlement.COMPLETED

    def test_one_person_completes_when_people_need_not_differ(self) -> None:
        """distinct_people の無い梃子は、ハルが左と右を両方押せば揃う。"""
        progress = ScenarioProgress.start(_WORLD)
        alone = _levers(distinct_people=False)

        progress.note_joint_action_part_done(_push(_HARU, _LEFT), (alone,), WorldTick(5))
        progress.note_joint_action_part_done(_push(_HARU, _RIGHT), (alone,), WorldTick(6))

        assert progress.joint_action_settlement(alone, WorldTick(6)) is JointActionSettlement.COMPLETED


class TestJointActionPartsChosenByTheLedger:
    """部分を行ったことを書く口が試みを受け取り、どの宣言のどの部分に当たるかを帳簿が決めることを保証する。"""

    def test_attempt_on_no_part_is_not_written(self) -> None:
        """梃子でない物を押す試みと、待つ試みは、どの部分にも当たらず、帳簿に何も書かない。"""
        progress = ScenarioProgress.start(_WORLD)
        wait = WaitAttempt(actor=_HARU, reason=WaitReason("ひと休み"))

        progress.note_joint_action_part_done(_push(_HARU, ObjectId("door")), (_LEVERS,), WorldTick(5))
        progress.note_joint_action_part_done(wait, (_LEVERS,), WorldTick(5))

        assert progress.memento().joint_actions == frozenset()

    def test_attempt_is_written_to_every_declaration_with_that_part(self) -> None:
        """左の梃子を部分に持つ宣言が 2 つあれば、ハルの左の一押しは両方に書かれる。"""
        progress = ScenarioProgress.start(_WORLD)
        other = _levers(joint_id="other_levers")

        progress.note_joint_action_part_done(_push(_HARU, _LEFT), (_LEVERS, other), WorldTick(5))

        assert {held.joint for held in progress.memento().joint_actions} == {_LEVERS.joint_id, other.joint_id}

    def test_refused_push_writes_to_no_declaration(self) -> None:
        """左の梃子を部分に持つ宣言 2 つのうち、後ろの 1 つだけが時間切れのまま落ち着いていないとき、ナツの左の一押しは JointActionUnsettledException を投げ、前の宣言にも書かれない。"""
        progress = ScenarioProgress.start(_WORLD)
        other = _levers(joint_id="other_levers")
        progress.note_joint_action_part_done(_push(_HARU, _RIGHT), (other,), WorldTick(5))
        before = progress.memento()

        with pytest.raises(JointActionUnsettledException):
            progress.note_joint_action_part_done(_push(_NATSU, _LEFT), (_LEVERS, other), WorldTick(8))

        assert progress.memento() == before


class TestJointActionSettled:
    """揃い・時間切れを落ち着かせると、そのドメインイベントを出して帳簿を空に戻し、同じ操作が二度落ち着かないことを保証する。"""

    def test_settling_completion_raises_completed_event_and_empties(self) -> None:
        """ハル左・ナツ右で tick 7 に揃いを落ち着かせると、行った人を載せた JointActionCompletedEvent を出し、同じ tick にもう一度問うと UNDECIDED になる。"""
        progress = ScenarioProgress.start(_WORLD)
        _pushed(progress, (5, _HARU, _LEFT), (7, _NATSU, _RIGHT))

        progress.note_joint_action_settled(_LEVERS, WorldTick(7), frozenset({_HARU}), NoRefusal())

        (event,) = progress.get_events()
        assert isinstance(event, JointActionCompletedEvent)
        assert event.joint_id == _LEVERS.joint_id
        assert event.at == WorldTick(7)
        assert event.audience == frozenset({_HARU})
        assert event.parts_done == frozenset(
            {JointActionPartDoneBy(_LEFT, _PUSH, _HARU), JointActionPartDoneBy(_RIGHT, _PUSH, _NATSU)}
        )
        assert progress.joint_action_settlement(_LEVERS, WorldTick(7)) is JointActionSettlement.UNDECIDED

    def test_settling_timeout_raises_timed_out_event_and_empties(self) -> None:
        """ハルの左だけで tick 8 に時間切れを落ち着かせると JointActionTimedOutEvent を出し、そのあとは UNDECIDED になる。"""
        progress = ScenarioProgress.start(_WORLD)
        _pushed(progress, (5, _HARU, _LEFT))

        progress.note_joint_action_settled(_LEVERS, WorldTick(8), frozenset(), NoRefusal())

        (event,) = progress.get_events()
        assert isinstance(event, JointActionTimedOutEvent)
        assert event.parts_done == frozenset({JointActionPartDoneBy(_LEFT, _PUSH, _HARU)})
        assert progress.joint_action_settlement(_LEVERS, WorldTick(8)) is JointActionSettlement.UNDECIDED

    def test_refused_settlement_has_no_audience(self) -> None:
        """揃いの効果が断られたと記録すると、イベントに断った理由が載り、知らせの相手は空になる。"""
        progress = ScenarioProgress.start(_WORLD)
        _pushed(progress, (5, _HARU, _LEFT), (7, _NATSU, _RIGHT))

        progress.note_joint_action_settled(_LEVERS, WorldTick(7), frozenset({_HARU}), _PACK_FULL)

        (event,) = progress.get_events()
        assert isinstance(event, JointActionCompletedEvent)
        assert event.refusal == _PACK_FULL
        assert event.audience == frozenset()

    def test_settling_what_is_undecided_is_refused(self) -> None:
        """ハルの左だけの tick 6 に落ち着かせようとすると JointActionNotSettlingException を投げ、帳簿は残る。"""
        progress = ScenarioProgress.start(_WORLD)
        _pushed(progress, (5, _HARU, _LEFT))

        with pytest.raises(JointActionNotSettlingException):
            progress.note_joint_action_settled(_LEVERS, WorldTick(6), frozenset(), NoRefusal())

        assert progress.joint_action_settlement(_LEVERS, WorldTick(8)) is JointActionSettlement.TIMED_OUT

    def test_settlement_names_the_effect_to_apply(self) -> None:
        """揃いは on_complete、時間切れは on_timeout の効果を返す。"""
        completed = JointActionSettlement.COMPLETED.effect_in(_LEVERS)
        timed_out = JointActionSettlement.TIMED_OUT.effect_in(_LEVERS)

        assert completed is _LEVERS.on_complete
        assert timed_out is _LEVERS.on_timeout


class TestJointActionMemento:
    """二人で合わせる操作の帳簿を memento にして読み戻すと、部分を行った人と起点の tick が保たれることを保証する。"""

    def test_progress_survives_memento(self) -> None:
        """ハルが tick 5 に左を押した帳簿を読み戻すと、ナツが tick 7 に右を押して揃い、tick 8 なら時間切れになる。"""
        progress = ScenarioProgress.start(_WORLD)
        _pushed(progress, (5, _HARU, _LEFT))

        restored = rebuilt_from_memento(progress)

        assert restored.memento() == progress.memento()
        assert restored.joint_action_settlement(_LEVERS, WorldTick(8)) is JointActionSettlement.TIMED_OUT

    def test_memento_with_one_joint_twice_is_refused(self) -> None:
        """同じ二人で合わせる操作の帳簿が 2 つある memento は RepeatedMementoKeyException になる。"""
        first = JointActionProgress(_LEVERS.joint_id, WorldTick(5), frozenset())
        second = JointActionProgress(_LEVERS.joint_id, WorldTick(6), frozenset())

        with pytest.raises(RepeatedMementoKeyException):
            ScenarioProgressMemento(_WORLD, frozenset(), frozenset(), frozenset({first, second}))

    def test_progress_with_one_part_done_twice_is_refused(self) -> None:
        """同じ部分を行った人が 2 人いる帳簿は RepeatedMementoKeyException になる。"""
        parts = frozenset({JointActionPartDoneBy(_LEFT, _PUSH, _HARU), JointActionPartDoneBy(_LEFT, _PUSH, _NATSU)})

        with pytest.raises(RepeatedMementoKeyException):
            JointActionProgress(_LEVERS.joint_id, WorldTick(5), parts)
