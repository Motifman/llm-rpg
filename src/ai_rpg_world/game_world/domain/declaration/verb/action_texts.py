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
    """``done_by_author`` の行は、成功の文を作者が行為ごとに書くので、ここには要約だけを置く。
    着いた (arrival) は行為ではなく移動の終わりなので、していることの文 (ongoing) を持たない。
    """

    TRAVEL = ("travel", ("origin", "destination"), False, False)
    ARRIVAL = ("arrival", ("destination",), False, False)
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
        self.has_ongoing = written_as != "arrival"


@final
@dataclass(frozen=True)
class ActionTexts:
    summaries: Mapping[ActionTextKey, TextWithUnassignedPeople]
    done: Mapping[ActionTextKey, TextWithUnassignedPeople]
    ongoing: Mapping[ActionTextKey, TextWithUnassignedPeople]

    def __post_init__(self) -> None:
        missing = sorted(key.written_as for key in ActionTextKey if key not in self.summaries)
        missing += sorted(
            f"{key.written_as}.done" for key in ActionTextKey if not key.done_by_author and key not in self.done
        )
        missing += sorted(
            f"{key.written_as}.ongoing" for key in ActionTextKey if key.has_ongoing and key not in self.ongoing
        )
        written_by_author = sorted(f"{key.written_as}.done" for key in self.done if key.done_by_author)
        never_ongoing = sorted(f"{key.written_as}.ongoing" for key in self.ongoing if not key.has_ongoing)
        if missing or written_by_author or never_ongoing:
            raise ActionTextMissingException(
                f"action texts lack {missing}, must leave {written_by_author} to the author"
                f" and must not write {never_ongoing}"
            )
        for key, text in (*self.summaries.items(), *self.done.items(), *self.ongoing.items()):
            unfilled = sorted(text.placeholders() - key.nameable)
            if unfilled:
                raise UnfilledNameInActionTextException(
                    f"the {key.written_as} text can name only {sorted(key.nameable)}, but names {unfilled}"
                )
        object.__setattr__(self, "summaries", MappingProxyType(dict(self.summaries)))
        object.__setattr__(self, "done", MappingProxyType(dict(self.done)))
        object.__setattr__(self, "ongoing", MappingProxyType(dict(self.ongoing)))

    def summary_of(self, key: ActionTextKey) -> TextWithUnassignedPeople:
        return self.summaries[key]

    def done_of(self, key: ActionTextKey) -> TextWithUnassignedPeople:
        return self.done[key]

    def ongoing_of(self, key: ActionTextKey) -> TextWithUnassignedPeople:
        return self.ongoing[key]
