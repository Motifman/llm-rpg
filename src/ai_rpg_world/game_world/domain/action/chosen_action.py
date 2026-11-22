from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeVar, final

from ai_rpg_world.being.contract import AgentMove, JsonValue
from ai_rpg_world.game_world.domain.action.action_arguments import TextArgumentValue
from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.action.action_entrances import ActionEntrances
from ai_rpg_world.game_world.domain.action.available_actions import AvailableActions
from ai_rpg_world.game_world.domain.action.built_in_attempts import SpeechAttempt
from ai_rpg_world.game_world.domain.action.choice_wording import ChoiceWording
from ai_rpg_world.game_world.domain.action.offered_action import (
    SAY_INLINE,
    ActionChoiceKind,
    OfferedAction,
    OfferedFreeText,
    OfferedInput,
    OfferedStep,
)
from ai_rpg_world.game_world.domain.action.speech import OrdinaryVoice, SpeechContent
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import PersonRef
from ai_rpg_world.game_world.domain.value_object import PersonId

_Reply = TypeVar("_Reply")
_ChosenValue = TextArgumentValue | ItemInstanceId


@final
@dataclass(frozen=True)
class ChosenActionAttempts:
    main: ActionAttempt
    inline_speech: tuple[SpeechAttempt, ...] = ()

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        reply = self.main.entered_through(entrances)
        # 一言は主の行為が断られても届ける (D2231)。一言が断られた理由は観測で届くので、返事は主の行為のものだけにする。
        for speech in self.inline_speech:
            speech.entered_through(entrances)
        return reply


@final
@dataclass(frozen=True)
class MisfitChosenAction:
    text: str

    def entered_through(self, entrances: ActionEntrances[_Reply]) -> _Reply:
        return entrances.misfit(self.text)


@final
class ChosenActionReading:
    def __init__(self, actor: PersonId, offers: tuple[tuple[ActionAttempt, OfferedAction], ...]) -> None:
        self._actor = actor
        self._offers = offers

    @classmethod
    def of(cls, actor: PersonId, available: AvailableActions, wording: ChoiceWording) -> ChosenActionReading:
        return cls(actor, tuple((action.attempt, action.attempt.offered_as(wording)) for action in available.actions))

    def attempts_for(self, move: AgentMove) -> ChosenActionAttempts | MisfitChosenAction:
        kind = next((kind for kind in ActionChoiceKind if kind.choice_name == move.tool_name), None)
        if kind is None:
            return MisfitChosenAction(f"「{move.tool_name}」という行動は無い。")
        arguments = move.arguments
        inline_speech = self._inline_speech(kind, arguments.get(SAY_INLINE.name))
        if isinstance(inline_speech, MisfitChosenAction):
            return inline_speech
        offers = [(attempt, offered) for attempt, offered in self._offers if offered.kind is kind]
        if not offers:
            return MisfitChosenAction(f"いまは「{kind.label}」で選べるものが無い。")
        # 同じ名前の品物は 1 つの候補なので、世界が並べた順で先のもの (古いもの) を使う (D2226)。
        chosen = next(
            ((attempt, offered) for attempt, offered in offers if _picks_every_step(offered.steps, arguments)), None
        )
        if chosen is None:
            return MisfitChosenAction(_unpicked(kind, offers, arguments))
        attempt, offered = chosen
        # 読まない引数を黙って捨てると、エージェントは伝えたつもりのことが起きなかったと気づけない。
        read = {SAY_INLINE.name, *(step.value.name for step in offered.steps), *(i.value.name for i in offered.inputs)}
        unread = sorted(name for name in arguments if name not in read)
        if unread:
            return MisfitChosenAction(f"「{kind.label}」では「{unread[0]}」を選べない。")
        values: dict[str, _ChosenValue] = {}
        for offered_input in offered.inputs:
            value = _chosen_input(offered_input, arguments.get(offered_input.value.name))
            if isinstance(value, MisfitChosenAction):
                return value
            values[offered_input.value.name] = value
        return ChosenActionAttempts(attempt.chosen_with(values), inline_speech)

    def _inline_speech(self, kind: ActionChoiceKind, said: JsonValue) -> tuple[SpeechAttempt, ...] | MisfitChosenAction:
        if said is None or (isinstance(said, str) and not said.strip()):
            return ()
        if not kind.takes_inline_speech:
            return MisfitChosenAction(f"「{kind.label}」には一言を添えられない。")
        if not isinstance(said, str):
            return MisfitChosenAction("添える一言は文字で書く。")
        return (SpeechAttempt(self._actor, OrdinaryVoice(), SpeechContent(said)),)


def _picks_every_step(steps: tuple[OfferedStep, ...], arguments: Mapping[str, JsonValue]) -> bool:
    return _picked_steps(steps, arguments) == len(steps)


def _picked_steps(steps: tuple[OfferedStep, ...], arguments: Mapping[str, JsonValue]) -> int:
    picked = 0
    for step in steps:
        if not _picks(step, arguments.get(step.value.name)):
            break
        picked += 1
    return picked


def _picks(step: OfferedStep, given: JsonValue) -> bool:
    if isinstance(step.candidate, PersonRef):
        return isinstance(given, Mapping) and given.get("person") == step.candidate.handle.value
    return given == step.candidate.text


def _unpicked(
    kind: ActionChoiceKind, offers: list[tuple[ActionAttempt, OfferedAction]], arguments: Mapping[str, JsonValue]
) -> str:
    _, nearest = max(offers, key=lambda offer: _picked_steps(offer[1].steps, arguments))
    step = nearest.steps[_picked_steps(nearest.steps, arguments)]
    given = arguments.get(step.value.name)
    if given is None:
        return f"「{kind.label}」の「{step.value.label}」を選んでいない。"
    # 人の印は内部の番号なので、選び間違えた値を文に戻さない。
    if isinstance(given, str) and not isinstance(step.candidate, PersonRef):
        return f"「{kind.label}」の「{step.value.label}」に「{given}」は選べない。"
    return f"「{kind.label}」の「{step.value.label}」に選んだものは、いま選べない。"


def _chosen_input(offered: OfferedInput, given: JsonValue) -> _ChosenValue | MisfitChosenAction:
    if isinstance(offered, OfferedFreeText):
        if not isinstance(given, str) or not given.strip():
            return MisfitChosenAction(f"「{offered.value.label}」に書く文字が無い。")
        return TextArgumentValue(given)
    item = next(
        (step.item for step in offered.items if _picks(step, given) and isinstance(step.item, ItemInstanceId)), None
    )
    if item is None:
        if isinstance(given, str):
            return MisfitChosenAction(f"「{offered.value.label}」に「{given}」は選べない。")
        return MisfitChosenAction(f"「{offered.value.label}」の品物を名前で選んでいない。")
    return item
