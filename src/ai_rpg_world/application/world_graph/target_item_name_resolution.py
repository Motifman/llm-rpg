"""書かれた品名を、相手の所持品のどれに当てるかを決める (design_decisions D1641)。

完全一致 → 部分一致 → 意味の判断の順に試す。判断は、名前の重なりで決まらない
ときだけ問う。当てはまりそうな物が複数あるときは、どれも選ばない。
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


@dataclass(frozen=True)
class HeldItem:
    spec_id: ItemSpecId
    name: str
    description: str


class ItemNameOutcome(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    ABSENT = "absent"
    UNRECOGNIZED = "unrecognized"


@dataclass(frozen=True)
class ItemNameRescueAnswer:
    """意味の判断の答え。``chosen`` は候補の名前、None は「どれでもない」。"""

    chosen: str | None
    accepted: bool
    confident_no_match: bool
    payload: Mapping[str, Any]


class ItemNameRescuer(Protocol):
    def rescue(self, written: str, *, candidates: Mapping[str, str], action_name: str) -> ItemNameRescueAnswer: ...


@dataclass(frozen=True)
class TargetItemNameResolution:
    written: str
    outcome: ItemNameOutcome
    method: str | None = None
    spec_id: ItemSpecId | None = None
    resolved_name: str | None = None
    matched_names: tuple[str, ...] = ()
    rescue_wired: bool = False
    judgment: Mapping[str, Any] | None = None

    @property
    def renamed(self) -> bool:
        return self.outcome is ItemNameOutcome.RESOLVED and self.method != "exact"

    def trace_payload(self) -> dict[str, Any] | None:
        """正式な名前どおりに当たったときは None。読み替えではないので残さない。"""
        if self.method == "exact" and self.outcome is ItemNameOutcome.RESOLVED:
            return None
        return {
            "written": self.written,
            "outcome": self.outcome.value,
            "method": self.method,
            "resolved_name": self.resolved_name,
            "matched_names": list(self.matched_names),
            "rescue_wired": self.rescue_wired,
            "judgment": dict(self.judgment) if self.judgment is not None else None,
        }


def resolve_target_item_name(
    written: str,
    held: Sequence[HeldItem],
    *,
    rescue: ItemNameRescuer | None,
    action_name: str,
    world_item_names: frozenset[str] = frozenset(),
) -> TargetItemNameResolution:
    wired = rescue is not None
    key = _normalized(written)
    exact = _distinct([h for h in held if _normalized(h.name) == key])
    if not exact and key in {_normalized(n) for n in world_item_names}:
        # 正式な名前が書かれたなら、その品を指している。「カンテラ」で
        # 「カンテラの油」を奪うと、本人の意図と違う物を動かす。
        return TargetItemNameResolution(
            written,
            ItemNameOutcome.ABSENT,
            "official_name_of_other_item",
            rescue_wired=wired,
        )
    partial = exact or _distinct(
        [h for h in held if key and _normalized(h.name) and (key in _normalized(h.name) or _normalized(h.name) in key)]
    )
    method = "exact" if exact else "partial"
    if len(partial) == 1:
        return TargetItemNameResolution(
            written,
            ItemNameOutcome.RESOLVED,
            method,
            partial[0].spec_id,
            partial[0].name,
            matched_names=(partial[0].name,),
            rescue_wired=wired,
        )
    if len(partial) > 1:
        return TargetItemNameResolution(
            written,
            ItemNameOutcome.AMBIGUOUS,
            method,
            matched_names=tuple(h.name for h in partial),
            rescue_wired=wired,
        )
    candidates = {h.name: h.description for h in _distinct(list(held))}
    if not candidates:
        return TargetItemNameResolution(written, ItemNameOutcome.ABSENT, "nothing_held", rescue_wired=wired)
    if rescue is None:
        return TargetItemNameResolution(written, ItemNameOutcome.ABSENT, "no_judge", rescue_wired=False)
    answer = rescue.rescue(written, candidates=candidates, action_name=action_name)
    chosen_items = _distinct([h for h in held if answer.accepted and h.name == answer.chosen])
    if len(chosen_items) > 1:
        return TargetItemNameResolution(
            written,
            ItemNameOutcome.AMBIGUOUS,
            "judgment",
            matched_names=tuple(h.name for h in chosen_items),
            rescue_wired=True,
            judgment=answer.payload,
        )
    if chosen_items:
        chosen = chosen_items[0]
        return TargetItemNameResolution(
            written,
            ItemNameOutcome.RESOLVED,
            "judgment",
            chosen.spec_id,
            chosen.name,
            matched_names=(chosen.name,),
            rescue_wired=True,
            judgment=answer.payload,
        )
    # 確信をもって「どれでもない」と言えたときだけ、持っていないと言い切る。
    # 判断が得られなかったときに言い切ると、持っている相手を嘘つきにする。
    outcome = (
        ItemNameOutcome.ABSENT if answer.chosen is None and answer.confident_no_match else ItemNameOutcome.UNRECOGNIZED
    )
    return TargetItemNameResolution(
        written,
        outcome,
        "judgment",
        rescue_wired=True,
        judgment=answer.payload,
    )


def _normalized(name: str) -> str:
    return "".join(unicodedata.normalize("NFKC", name or "").split())


def _distinct(items: list[HeldItem]) -> list[HeldItem]:
    seen: dict[ItemSpecId, HeldItem] = {}
    for h in items:
        seen.setdefault(h.spec_id, h)
    return list(seen.values())
