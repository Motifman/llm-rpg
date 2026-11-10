from __future__ import annotations

from ai_rpg_world.game_world.domain.action.action_arguments import TextArgumentValue
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.exception.trigger_exception import (
    ArgumentNotInTriggerException,
    ItemNotInTriggerException,
    SubjectNotInTriggerException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName


class AnswersNothingByDefault:
    def person_as(self, kind: SubjectKind) -> PersonId:
        raise SubjectNotInTriggerException(f"{self!r} does not answer {kind.name}")

    def this_item(self) -> ItemInstanceId:
        raise ItemNotInTriggerException(f"{self!r} does not answer the item")

    def argument(self, name: ArgumentName) -> TextArgumentValue | ItemInstanceId:
        raise ArgumentNotInTriggerException(f"{self!r} does not answer the argument {name.value!r}")
