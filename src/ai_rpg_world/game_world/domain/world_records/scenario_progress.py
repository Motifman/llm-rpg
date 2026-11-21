from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.eventing import AggregateRoot, DomainEvent, new_event_stamp
from ai_rpg_world.game_world.domain.action.refusal_code import NoRefusal, RefusalCode
from ai_rpg_world.game_world.domain.exception.game_world_exception import require_distinct_memento_keys
from ai_rpg_world.game_world.domain.exception.world_records_exception import (
    JointActionNotSettlingException,
    JointActionUnsettledException,
)
from ai_rpg_world.game_world.domain.perception.people_present import PeopleWhoWereThere
from ai_rpg_world.game_world.domain.value_object import InteractionId, ObjectId, PersonId, Ticks, WorldId, WorldTick
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.joint_action_id import JointActionId
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId
from ai_rpg_world.game_world.domain.world_records.joint_action_progress import (
    JointActionCompletedEvent,
    JointActionProgress,
    JointActionSettlement,
    JointActionTimedOutEvent,
)

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
    from ai_rpg_world.game_world.domain.declaration.verb.happening_declaration import HappeningDeclaration
    from ai_rpg_world.game_world.domain.declaration.verb.joint_action_declaration import JointActionDeclaration
    from ai_rpg_world.game_world.domain.declaration.verb.reaction_declaration import ReactionDeclaration


@final
@dataclass(frozen=True)
class NeverFired:
    def has_passed(self, ticks: Ticks, now: WorldTick) -> bool:
        return False


@final
@dataclass(frozen=True)
class HappeningLastFiredAt:
    happening: HappeningId
    at: WorldTick


@final
@dataclass(frozen=True)
class ReactionLastTruth:
    reaction: ReactionId
    truth: bool


@final
@dataclass(frozen=True)
class HappeningFiredEvent(DomainEvent):
    world_id: WorldId
    happening_id: HappeningId
    at: WorldTick
    audience: frozenset[PersonId]
    present: PeopleWhoWereThere
    refusal: RefusalCode | NoRefusal


@final
@dataclass(frozen=True)
class ReactionFiredEvent(DomainEvent):
    world_id: WorldId
    reaction_id: ReactionId
    became: bool
    at: WorldTick
    refusal: RefusalCode | NoRefusal


ScenarioProgressEvent = HappeningFiredEvent | ReactionFiredEvent | JointActionCompletedEvent | JointActionTimedOutEvent


@final
@dataclass(frozen=True)
class ScenarioProgressMemento:
    world_id: WorldId
    last_fired: frozenset[HappeningLastFiredAt]
    reaction_truths: frozenset[ReactionLastTruth]
    joint_actions: frozenset[JointActionProgress]

    def __post_init__(self) -> None:
        require_distinct_memento_keys(
            [fired.happening for fired in self.last_fired],
            f"world {self.world_id.value} has a happening last fired at two ticks",
        )
        require_distinct_memento_keys(
            [noted.reaction for noted in self.reaction_truths],
            f"world {self.world_id.value} has a reaction with two truths",
        )
        require_distinct_memento_keys(
            [held.joint for held in self.joint_actions],
            f"world {self.world_id.value} has a joint action in progress twice",
        )


class ScenarioProgress(AggregateRoot[ScenarioProgressEvent]):
    def __init__(
        self,
        world_id: WorldId,
        last_fired: Mapping[HappeningId, WorldTick],
        reaction_truths: Mapping[ReactionId, bool],
        joint_actions: Mapping[JointActionId, JointActionProgress],
    ) -> None:
        super().__init__()
        self._world_id = world_id
        self._last_fired = dict(last_fired)
        self._reaction_truths = dict(reaction_truths)
        self._joint_actions = dict(joint_actions)

    @classmethod
    def start(cls, world_id: WorldId) -> ScenarioProgress:
        return cls(world_id, {}, {}, {})

    @classmethod
    def from_memento(cls, memento: ScenarioProgressMemento) -> ScenarioProgress:
        return cls(
            memento.world_id,
            {fired.happening: fired.at for fired in memento.last_fired},
            {noted.reaction: noted.truth for noted in memento.reaction_truths},
            {held.joint: held for held in memento.joint_actions},
        )

    @property
    def world_id(self) -> WorldId:
        return self._world_id

    def memento(self) -> ScenarioProgressMemento:
        return ScenarioProgressMemento(
            world_id=self._world_id,
            last_fired=frozenset(HappeningLastFiredAt(happening, at) for happening, at in self._last_fired.items()),
            reaction_truths=frozenset(
                ReactionLastTruth(reaction, truth) for reaction, truth in self._reaction_truths.items()
            ),
            joint_actions=frozenset(self._joint_actions.values()),
        )

    def note_happening_fired(
        self,
        happening: HappeningDeclaration,
        now: WorldTick,
        audience: frozenset[PersonId],
        present: PeopleWhoWereThere,
        refusal: RefusalCode | NoRefusal,
    ) -> None:
        self._last_fired[happening.happening_id] = now
        self.add_event(
            HappeningFiredEvent(
                **new_event_stamp(),
                world_id=self._world_id,
                happening_id=happening.happening_id,
                at=now,
                audience=_notified(audience, refusal),
                present=_present(present, refusal),
                refusal=refusal,
            )
        )

    def note_reaction_fired(
        self, reaction: ReactionDeclaration, truth: bool, now: WorldTick, refusal: RefusalCode | NoRefusal
    ) -> None:
        self._reaction_truths[reaction.reaction_id] = truth
        self.add_event(
            ReactionFiredEvent(
                **new_event_stamp(),
                world_id=self._world_id,
                reaction_id=reaction.reaction_id,
                became=truth,
                at=now,
                refusal=refusal,
            )
        )

    def note_reaction_truth(self, reaction: ReactionDeclaration, truth: bool) -> None:
        self._reaction_truths[reaction.reaction_id] = truth

    def may_fire(self, happening: HappeningDeclaration, now: WorldTick) -> bool:
        last_fired = self._last_fired.get(happening.happening_id)
        if last_fired is None:
            return True
        return not happening.once and last_fired != now

    def reaction_changed(self, reaction: ReactionDeclaration, truth: bool) -> bool:
        noted = self._reaction_truths.get(reaction.reaction_id)
        return noted is not None and noted != truth

    def last_fired_at(self, happening: HappeningId) -> WorldTick | NeverFired:
        return self._last_fired.get(happening, NeverFired())

    def note_joint_action_part_done(
        self, attempt: ActionAttempt, joints: Iterable[JointActionDeclaration], now: WorldTick
    ) -> None:
        parts_done = [(joint, part) for joint in joints for part in joint.required if attempt.operates(*part)]
        for joint, _ in parts_done:
            # 揃いか時間切れを落ち着かせる前に書くと、効果を当てないまま次の試みに混ざる
            if self.joint_action_settlement(joint, now).settles():
                raise JointActionUnsettledException(
                    f"{joint.joint_id.value} has to be settled before another part is done at tick {now.value}"
                )
        for joint, part in parts_done:
            self._note_part_done(joint, part, attempt.actor, now)

    def _note_part_done(
        self, joint: JointActionDeclaration, part: tuple[ObjectId, InteractionId], by: PersonId, now: WorldTick
    ) -> None:
        held = self._joint_actions.get(joint.joint_id)
        if held is None:
            self._joint_actions[joint.joint_id] = JointActionProgress.begin(joint.joint_id, part, by, now)
            return
        self._joint_actions[joint.joint_id] = held.with_part_done(part, by)

    def joint_action_settlement(self, joint: JointActionDeclaration, now: WorldTick) -> JointActionSettlement:
        held = self._joint_actions.get(joint.joint_id)
        if held is None:
            return JointActionSettlement.UNDECIDED
        return held.settlement(joint, now)

    def note_joint_action_settled(
        self,
        joint: JointActionDeclaration,
        now: WorldTick,
        audience: frozenset[PersonId],
        present: PeopleWhoWereThere,
        refusal: RefusalCode | NoRefusal,
    ) -> None:
        settlement = self.joint_action_settlement(joint, now)
        if not settlement.settles():
            raise JointActionNotSettlingException(f"{joint.joint_id.value} is not settling at tick {now.value}")
        held = self._joint_actions.pop(joint.joint_id)
        settled = (
            JointActionCompletedEvent if settlement is JointActionSettlement.COMPLETED else JointActionTimedOutEvent
        )
        self.add_event(
            settled(
                **new_event_stamp(),
                world_id=self._world_id,
                joint_id=joint.joint_id,
                at=now,
                parts_done=held.parts_done,
                audience=_notified(audience, refusal),
                present=_present(present, refusal),
                refusal=refusal,
            )
        )


def _notified(audience: frozenset[PersonId], refusal: RefusalCode | NoRefusal) -> frozenset[PersonId]:
    # 断られた発火は何も変えていないので、知らせると起きていないことを伝えてしまう
    return audience if isinstance(refusal, NoRefusal) else frozenset()


def _present(present: PeopleWhoWereThere, refusal: RefusalCode | NoRefusal) -> PeopleWhoWereThere:
    return present if isinstance(refusal, NoRefusal) else PeopleWhoWereThere()
