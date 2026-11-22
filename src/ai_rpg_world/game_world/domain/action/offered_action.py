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
SAY_INLINE = OfferedValue("say_inline", "この行動をしながら、同じ場所の人にかける一言 (任意)")


_NAME_LIMIT = 64
_NAMES_TAKEN_BY_THE_CHOICE = frozenset({TARGET.name, HOW.name, SAY_INLINE.name})


def offered_value_name_problems(name: str) -> tuple[str, ...]:
    # 引数の名前は、Being が選択肢を LLM のツールにするとき引数の名前になり、操作の道筋 (target → how) と
    # 行動しながらの一言と同じ段に並ぶ。
    if not (name.isascii() and name.isidentifier() and len(name) <= _NAME_LIMIT):
        return (f"argument {name!r} must be an ASCII identifier of up to {_NAME_LIMIT} characters",)
    if name in _NAMES_TAKEN_BY_THE_CHOICE:
        return (f"argument {name!r} is already used by the interact choice",)
    return ()


class ActionChoiceKind(Enum):
    TRAVEL_TO = ("travel_to", "行く", (DESTINATION, SAY_INLINE))
    SET_SUB_LOCATION = ("set_sub_location", "区画に出入りする", (SECTION_MOVE,))
    EXPLORE = ("explore", "探す", (SAY_INLINE,))
    INTERACT = ("interact", "操作する", (TARGET, HOW, SAY_INLINE), True)
    WAIT = ("wait", "待つ", (SAY_INLINE,))
    LISTEN = ("listen", "耳を澄ます", ())
    SPEAK = ("speak", "話す", (REACH, LISTENER, CONTENT))
    USE_ITEM = ("use_item", "使う", (ITEM, SAY_INLINE))
    DROP_ITEM = ("drop_item", "置く", (ITEM, SAY_INLINE))
    PICKUP_ITEM = ("pickup_item", "拾う", (ITEM, SAY_INLINE))
    GIVE_ITEM = ("give_item", "渡す", (RECIPIENT, ITEM, SAY_INLINE))
    TEND_TO_PLAYER = ("tend_to_player", "介抱する", (TARGET, SAY_INLINE))
    VOTE = ("vote", "投票する", (DECISION, BALLOT))
    HOLD_ITEM = ("hold_item", "手に持つ", (ITEM,))
    PUT_AWAY_ITEM = ("put_away_item", "しまう", (ITEM,))

    def __init__(
        self, choice_name: str, label: str, outline: tuple[OfferedValue, ...], takes_details: bool = False
    ) -> None:
        self.choice_name = choice_name
        self.label = label
        self.outline = outline
        self.takes_details = takes_details
        self.first_value = next((value for value in outline if value is not SAY_INLINE), None)

    @property
    def takes_inline_speech(self) -> bool:
        return SAY_INLINE in self.outline


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
