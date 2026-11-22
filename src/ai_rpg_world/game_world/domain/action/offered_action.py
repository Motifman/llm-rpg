from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import final

from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import PersonRef
from ai_rpg_world.game_world.domain.value_object import DisplayName


@final
@dataclass(frozen=True)
class OfferedValue:
    name: str
    label: str


DESTINATION = OfferedValue("destination", "行き先")
SECTION_MOVE = OfferedValue("move", "出入り")
TARGET = OfferedValue("target", "相手")
HOW = OfferedValue("how", "操作")
REACH = OfferedValue("reach", "届け方")
LISTENER = OfferedValue("to", "相手")
CONTENT = OfferedValue("content", "中身")
ITEM = OfferedValue("item", "品物")
RECIPIENT = OfferedValue("to", "渡す相手")
DECISION = OfferedValue("decision", "決めごと")
BALLOT = OfferedValue("choice", "選び先")
INLINE_SPEECH = "say_inline"


_NAME_LIMIT = 64
_NAMES_TAKEN_BY_THE_CHOICE = frozenset({TARGET.name, HOW.name, INLINE_SPEECH})


def offered_value_name_problems(name: str) -> tuple[str, ...]:
    # 引数の名前は、Being が選択肢を LLM のツールにするとき引数の名前になり、操作の道筋 (target → how) と
    # 行動しながらの一言と同じ段に並ぶ。
    if not (name.isascii() and name.isidentifier() and len(name) <= _NAME_LIMIT):
        return (f"argument {name!r} must be an ASCII identifier of up to {_NAME_LIMIT} characters",)
    if name in _NAMES_TAKEN_BY_THE_CHOICE:
        return (f"argument {name!r} is already used by the interact choice",)
    return ()


class ActionChoiceKind(Enum):
    # 行動しながらの一言を添えられるかは、古い run のツールに合わせる (D2231)。
    TRAVEL_TO = ("travel_to", "行く", DESTINATION, True)
    SET_SUB_LOCATION = ("set_sub_location", "区画に出入りする", SECTION_MOVE, True)
    EXPLORE = ("explore", "探す", None, True)
    INTERACT = ("interact", "操作する", TARGET, True)
    WAIT = ("wait", "待つ", None, True)
    LISTEN = ("listen", "耳を澄ます", None, False)
    SPEAK = ("speak", "話す", REACH, False)
    USE_ITEM = ("use_item", "使う", ITEM, True)
    DROP_ITEM = ("drop_item", "置く", ITEM, True)
    PICKUP_ITEM = ("pickup_item", "拾う", ITEM, True)
    GIVE_ITEM = ("give_item", "渡す", RECIPIENT, True)
    TEND_TO_PLAYER = ("tend_to_player", "介抱する", TARGET, True)
    VOTE = ("vote", "投票する", DECISION, False)
    HOLD_ITEM = ("hold_item", "手に持つ", ITEM, True)
    PUT_AWAY_ITEM = ("put_away_item", "しまう", ITEM, True)

    def __init__(
        self, choice_name: str, label: str, first_value: OfferedValue | None, takes_inline_speech: bool
    ) -> None:
        self.choice_name = choice_name
        self.label = label
        self.first_value = first_value
        self.takes_inline_speech = takes_inline_speech


@final
@dataclass(frozen=True)
class NotAnItem:
    pass


@final
@dataclass(frozen=True)
class OfferedStep:
    value: OfferedValue
    candidate: DisplayName | PersonRef
    item: ItemInstanceId | NotAnItem = NotAnItem()


@final
@dataclass(frozen=True)
class OfferedItemPick:
    value: OfferedValue
    items: tuple[OfferedStep, ...]


@final
@dataclass(frozen=True)
class OfferedFreeText:
    value: OfferedValue


OfferedInput = OfferedFreeText | OfferedItemPick


@final
@dataclass(frozen=True)
class OfferedAction:
    kind: ActionChoiceKind
    steps: tuple[OfferedStep, ...] = ()
    inputs: tuple[OfferedInput, ...] = ()
