from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import final

from ai_rpg_world.game_world.domain.exception.verb_declaration_exception import (
    ActionTextMissingException,
    UnfilledNameInActionTextException,
)
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople


class ActionTextKey(Enum):
    """``done_by_author`` の行は、成功の文を作者が行為ごとに書くので、ここには要約だけを置く。"""

    TRAVEL = ("travel", ("destination",), False, False)
    WHISPER = ("whisper", ("speech",), True, False)
    SPEAK = ("speak", ("speech",), False, False)
    SHOUT = ("shout", ("speech",), False, False)
    LISTEN = ("listen", (), False, False)
    WAIT = ("wait", (), False, False)
    TEND = ("tend", (), True, False)
    HAND_OVER = ("hand_over", ("item",), True, False)
    PICK_UP = ("pick_up", ("item",), False, False)
    DROP = ("drop", ("item",), False, False)
    SEARCH = ("search", (), False, False)
    USE_ITEM = ("use_item", ("item",), False, False)
    HOLD = ("hold", ("item",), False, False)
    PUT_AWAY = ("put_away", ("item",), False, False)
    CAST_BALLOT = ("cast_ballot", (), False, False)
    VOTE_FOR = ("vote_for", (), True, False)
    ENTER_SECTION = ("enter_section", ("section",), False, True)
    LEAVE_SECTION = ("leave_section", ("section",), False, True)
    INTERACT_WITH_OBJECT = ("interact_with_object", ("object", "how"), False, True)
    INTERACT_WITH_CARRIED_ITEM = ("interact_with_carried_item", ("item", "how"), False, True)
    INTERACT_WITH_PERSON = ("interact_with_person", ("how",), True, True)
    INTERACT_WITH_SOMEONE_IN_THE_DARK = ("interact_with_someone_in_the_dark", ("how",), False, True)

    def __init__(
        self, written_as: str, names_of_things: tuple[str, ...], has_target: bool, done_by_author: bool
    ) -> None:
        self.written_as = written_as
        self.nameable = frozenset({*names_of_things, "actor", *(("target",) if has_target else ())})
        self.done_by_author = done_by_author


@final
@dataclass(frozen=True)
class ActionTexts:
    summaries: Mapping[ActionTextKey, TextWithUnassignedPeople]
    done: Mapping[ActionTextKey, TextWithUnassignedPeople]

    def __post_init__(self) -> None:
        missing = sorted(key.written_as for key in ActionTextKey if key not in self.summaries)
        missing += sorted(
            f"{key.written_as}.done" for key in ActionTextKey if not key.done_by_author and key not in self.done
        )
        written_by_author = sorted(f"{key.written_as}.done" for key in self.done if key.done_by_author)
        if missing or written_by_author:
            raise ActionTextMissingException(
                f"action texts lack {missing} and must leave {written_by_author} to the author"
            )
        for key, text in (*self.summaries.items(), *self.done.items()):
            unfilled = sorted(text.placeholders() - key.nameable)
            if unfilled:
                raise UnfilledNameInActionTextException(
                    f"the {key.written_as} text can name only {sorted(key.nameable)}, but names {unfilled}"
                )
        object.__setattr__(self, "summaries", MappingProxyType(dict(self.summaries)))
        object.__setattr__(self, "done", MappingProxyType(dict(self.done)))

    def summary_of(self, key: ActionTextKey) -> TextWithUnassignedPeople:
        return self.summaries[key]

    def done_of(self, key: ActionTextKey) -> TextWithUnassignedPeople:
        return self.done[key]
