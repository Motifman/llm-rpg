from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from ai_rpg_world.game_world.domain.condition.condition import FailureReason, HiddenFailure, NoText
from ai_rpg_world.game_world.domain.condition.condition_path import ConditionPath
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.exception.condition_exception import UnknownPersonPlaceholderException
from ai_rpg_world.game_world.domain.people import TextAboutPeople, TextWithUnassignedPeople

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger

_SUBJECT_OF_PLACEHOLDER = {
    "actor": SubjectKind.ACTOR,
    "target": SubjectKind.TARGET,
    "chosen_by_group": SubjectKind.CHOSEN_BY_GROUP,
    "each_person": SubjectKind.EACH_PERSON,
}


def _subject_of(placeholder: str, failure_text: TextWithUnassignedPeople) -> SubjectKind:
    if placeholder not in _SUBJECT_OF_PLACEHOLDER:
        raise UnknownPersonPlaceholderException(
            f"{{{placeholder}}} in {failure_text.template!r} is none of {sorted(_SUBJECT_OF_PLACEHOLDER)}"
        )
    return _SUBJECT_OF_PLACEHOLDER[placeholder]


def text_about_people(failure_text: TextWithUnassignedPeople | NoText, trigger: Trigger) -> TextAboutPeople | NoText:
    if isinstance(failure_text, NoText):
        return NoText()
    return failure_text.about(
        {
            placeholder: trigger.person_as(_subject_of(placeholder, failure_text))
            for placeholder in failure_text.placeholders()
        }
    )


def placeholder_requirements(failure_text: TextWithUnassignedPeople | NoText) -> Requirements:
    if isinstance(failure_text, NoText):
        return Requirements.nothing()
    return replace(
        Requirements.nothing(),
        subjects=frozenset(_subject_of(placeholder, failure_text) for placeholder in failure_text.placeholders()),
    )


def own_failure(failure_text: TextWithUnassignedPeople | NoText, trigger: Trigger) -> FailureReason:
    return FailureReason(failed_part=ConditionPath.root(), text=text_about_people(failure_text, trigger))


def failure_of_child(
    reason: FailureReason | HiddenFailure,
    position: int,
    failure_text: TextWithUnassignedPeople | NoText,
    trigger: Trigger,
) -> FailureReason | HiddenFailure:
    failed_part = reason.failed_part.under(position)
    if isinstance(reason, HiddenFailure):
        return HiddenFailure(failed_part=failed_part)
    if isinstance(reason.text, NoText):
        return FailureReason(failed_part=failed_part, text=text_about_people(failure_text, trigger))
    return FailureReason(failed_part=failed_part, text=reason.text)


def failure_of_all_children(
    reasons: list[FailureReason | HiddenFailure],
    failure_text: TextWithUnassignedPeople | NoText,
    trigger: Trigger,
) -> FailureReason | HiddenFailure:
    # どの子のせいかは 1 つに決まらないので自分の文を使うが、子が 1 つでも伏せていれば、偽であること自体が所属を漏らす。
    if any(isinstance(reason, HiddenFailure) for reason in reasons):
        return HiddenFailure(failed_part=ConditionPath.root())
    return own_failure(failure_text, trigger)
