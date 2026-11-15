from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.trigger import HappeningFired, ReactionFired, WorldConditionsSettling
from ai_rpg_world.game_world.domain.condition.settling_occasion import SettlingOccasion
from ai_rpg_world.game_world.domain.declaration.verb.happening_declaration import HappeningDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.joint_action_declaration import JointActionDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.reaction_declaration import ReactionDeclaration
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.value_object import WorldTick
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId


class WorldConditionsDidNotSettleError(RuntimeError):
    pass


@final
@dataclass(frozen=True)
class SettleWorldConditionsCommand:
    occasion: SettlingOccasion


@final
class SettleWorldConditions:
    def __init__(self, scope: CommandScope, design: WorldDesign) -> None:
        self._scope = scope
        self._design = design

    def __call__(self, command: SettleWorldConditionsCommand) -> None:
        self._scope.run(lambda session: _Settling(session, self._design, command.occasion).settle())


@final
class _Settling:
    def __init__(self, session: WorldSession, design: WorldDesign, occasion: SettlingOccasion) -> None:
        self._session = session
        self._design = design
        self._occasion = occasion
        # 反応には 1 tick に 1 回の帳簿が無いので、自分の条件を崩す反応で回り続けないよう、1 回の落ち着かせに 1 回までにする
        self._fired_reactions: set[ReactionId] = set()

    def settle(self) -> None:
        # 出来事は 1 tick に 1 回、反応と二人で合わせる操作は 1 回の落ち着かせに 1 回までなので、発火のある回は宣言の数を超えない。
        # 超えたら帳簿か発火の記録の誤りで、上限が無いとイベントをためながら回り続ける
        round_limit = (
            len(self._design.happenings()) + len(self._design.reactions()) + len(self._design.joint_actions()) + 1
        )
        for _ in range(round_limit):
            if not self._fire_what_holds():
                self._end_if_over()
                return
        raise WorldConditionsDidNotSettleError(f"world conditions did not settle within {round_limit} rounds")

    def _fire_what_holds(self) -> bool:
        now = self._session.clock().now()
        happenings = self._happenings_that_hold(now)
        reactions = self._reactions_that_changed()
        joints = self._joint_actions_settling(now)
        for happening in happenings:
            self._fire_happening(happening, now)
        for reaction, truth in reactions:
            self._fire_reaction(reaction, truth, now)
        for joint in joints:
            self._settle_joint_action(joint, now)
        return bool(happenings or reactions or joints)

    def _happenings_that_hold(self, now: WorldTick) -> list[HappeningDeclaration]:
        facts = self._session.facts()
        progress = self._session.scenario_progress()
        return [
            happening
            for happening in self._design.happenings()
            if self._occasion.checks(happening.condition)
            and progress.may_fire(happening, now)
            and happening.condition.holds(facts, HappeningFired(happening))
        ]

    def _reactions_that_changed(self) -> list[tuple[ReactionDeclaration, bool]]:
        facts = self._session.facts()
        progress = self._session.scenario_progress()
        changed: list[tuple[ReactionDeclaration, bool]] = []
        for reaction in self._design.reactions():
            if reaction.reaction_id in self._fired_reactions or not self._occasion.checks(reaction.condition):
                continue
            truth = reaction.condition.holds(facts, ReactionFired(reaction))
            if progress.reaction_changed(reaction, truth):
                changed.append((reaction, truth))
            else:
                progress.note_reaction_truth(reaction, truth)
        return changed

    def _joint_actions_settling(self, now: WorldTick) -> list[JointActionDeclaration]:
        progress = self._session.scenario_progress()
        return [
            joint for joint in self._design.joint_actions() if progress.joint_action_settlement(joint, now).settles()
        ]

    def _fire_happening(self, happening: HappeningDeclaration, now: WorldTick) -> None:
        trigger = HappeningFired(happening)
        audience = happening.notice.addressees(self._session.facts(), trigger)
        refusal = self._session.attempt_apart(
            lambda: happening.effect.apply(self._session.facts(), self._session.aggregates(), trigger)
        )
        self._session.scenario_progress().note_happening_fired(happening, now, audience, refusal)

    def _fire_reaction(self, reaction: ReactionDeclaration, truth: bool, now: WorldTick) -> None:
        trigger = ReactionFired(reaction)
        refusal = self._session.attempt_apart(
            lambda: reaction.effect_when(truth).apply(self._session.facts(), self._session.aggregates(), trigger)
        )
        self._session.scenario_progress().note_reaction_fired(reaction, truth, now, refusal)
        self._fired_reactions.add(reaction.reaction_id)

    def _settle_joint_action(self, joint: JointActionDeclaration, now: WorldTick) -> None:
        settlement = self._session.scenario_progress().joint_action_settlement(joint, now)
        trigger = settlement.trigger_for(joint)
        audience = settlement.notice_in(joint).addressees(self._session.facts(), trigger)
        refusal = self._session.attempt_apart(
            lambda: settlement.effect_in(joint).apply(self._session.facts(), self._session.aggregates(), trigger)
        )
        self._session.scenario_progress().note_joint_action_settled(joint, now, audience, refusal)

    def _end_if_over(self) -> None:
        ending = self._session.ending()
        ends_when = self._design.ending.ends_when
        if ending.has_ended() or not self._occasion.checks(ends_when):
            return
        now = self._session.clock().now()
        if ends_when.holds(self._session.facts(), WorldConditionsSettling(now)):
            ending.end(now)
