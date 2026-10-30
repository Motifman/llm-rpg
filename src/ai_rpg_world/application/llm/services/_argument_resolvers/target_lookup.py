"""書かれた名前から、いま指せる対象を引く索引。

1 ターンぶんの ``runtime_context.targets`` は、物・人・敵・行き先・区画・所持品・
足元の品を 1 つの辞書に持つ。以前は受け付ける種別ごとに辞書を全走査していたので、
「その名前は在るが、このツールの対象ではない」を見分けるには走査を増やす必要が
あった。表示名で 1 回索引を作れば、名前 1 つにつき参照 1 回で 4 つの結果が同時に
出る。

- ``Found``: 受け付ける種別に 1 件だけ当たった
- ``Ambiguous``: 受け付ける種別に同名が複数ある
- ``WrongKind``: 別の種別に在る。「無い」ではなく「種類が違う」と伝え、使うツールを添える
- ``NotFound``: どこにも無い。候補一覧を添えて失敗させるか、意味で選び直す

## 内部ラベル (O1 / P2) は最後の逃げ道としてだけ引く

プロンプトは名前直書きで、内部ラベルを出していない (design_decisions #3)。ただし
物とプレイヤーが同じ表示名を持つときは名前では指せず、``Ambiguous`` の文面で内部
ラベルを案内するのが唯一の出口になる。そのため表示名で当たらなかったときに限り、
内部ラベルでも引く。
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeTargetDto
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_ATTACK,
    TOOL_NAME_SPOT_GRAPH_BUY_ITEM,
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_SELL_ITEM,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
)

KIND_LABEL: Mapping[str, str] = {
    "spot_graph_object": "この場所の物",
    "spot_graph_player": "この場所にいる人",
    "spot_graph_monster": "この場所の敵",
    "spot_graph_destination": "隣の場所",
    "spot_graph_sub_location": "この場所の区画",
    "inventory_item": "手持ちの品",
    "ground_item": "足元の品",
    "merchant": "商人",
}

#: 種別ごとに「その名前に対して取れる手」と、それに使うツール。ツール名は
#: 露出判断を通してから文面に載せる (CLAUDE.md「プロンプト本文にツール名を
#: 書くときは、必ず露出判断を通す」)。無効化されたツールを勧めると、当人は
#: 存在しないツールを呼ぶ。
_KIND_MOVES: Mapping[str, tuple[tuple[str, str], ...]] = {
    "spot_graph_object": ((TOOL_NAME_SPOT_GRAPH_INTERACT, "調べる・使うなら"),),
    "spot_graph_player": (
        (TOOL_NAME_SPOT_GRAPH_INTERACT, "関わるなら"),
        (TOOL_NAME_SPOT_GRAPH_GIVE_ITEM, "渡すなら"),
    ),
    "spot_graph_monster": ((TOOL_NAME_SPOT_GRAPH_ATTACK, "戦うなら"),),
    "spot_graph_destination": ((TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, "そこへ行くなら"),),
    "spot_graph_sub_location": ((TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION, "そこへ移るなら"),),
    "inventory_item": (
        (TOOL_NAME_SPOT_GRAPH_USE_ITEM, "使うなら"),
        (TOOL_NAME_SPOT_GRAPH_GIVE_ITEM, "渡すなら"),
    ),
    "ground_item": ((TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM, "拾うなら"),),
    "merchant": (
        (TOOL_NAME_SPOT_GRAPH_BUY_ITEM, "買うなら"),
        (TOOL_NAME_SPOT_GRAPH_SELL_ITEM, "売るなら"),
    ),
}
_KIND_PREFACE: Mapping[str, str] = {"inventory_item": "すでに持っている。"}

ToolIsExposed = Callable[[str], bool]


def advice_for(kind: str, tool_is_exposed: ToolIsExposed | None) -> str:
    """その種別の名前に対して取れる手を、この世界に在るツールだけで言う。"""
    parts: list[str] = []
    preface = _KIND_PREFACE.get(kind)
    if preface:
        parts.append(preface)
    moves = [
        f"{lead} {tool}" for tool, lead in _KIND_MOVES.get(kind, ()) if tool_is_exposed is None or tool_is_exposed(tool)
    ]
    if moves:
        parts.append("、".join(moves) + " を使う。")
    return " ".join(parts)


_LEADING_LABEL_RE = re.compile(r"^(S\d+|SL\d+|OBJ\d+|P\d+|I\d+|M\d+)\b")
_PAREN_RE = re.compile(r"[(（]([^()（）]+)[)）]")
_TRAILING_PAREN_RE = re.compile(r"\s*[(（][^()（）]*[)）]\s*$")


def strip_symmetric_quotes(text: str) -> str | None:
    """対称な ``"..."`` / ``'...'`` を剥がす。剥がせなければ None。"""
    s = text.strip()
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        inner = s[1:-1].strip()
        return inner or None
    return None


def label_forms(written: str) -> list[str]:
    """書かれた文字列から、照合を試す形を出現順に返す。同じ形は 1 度だけ。

    プロンプト行の丸写し (``S2: 禁書扉 → 館長書斎``)、括弧つき (``S2 (館長書斎)``)、
    引用符つき (``"拠点"``) を分解する。表示に無い名前の発明は救わない。
    """
    s = written.strip()
    if not s:
        return []
    out: list[str] = [s]
    unquoted = strip_symmetric_quotes(s)
    if unquoted:
        out.append(unquoted)
    if "→" in s:
        tail = s.rsplit("→", 1)[1].strip()
        tail_unquoted = strip_symmetric_quotes(tail) if tail else None
        if tail_unquoted:
            out.append(tail_unquoted)
    m = _LEADING_LABEL_RE.match(s)
    if m:
        out.append(m.group(1))
    m2 = _PAREN_RE.search(s)
    if m2:
        out.append(m2.group(1).strip())
    if "→" in s:
        right = _TRAILING_PAREN_RE.sub("", s.split("→")[-1].strip()).strip()
        if right:
            out.append(right)
    if ":" in s or "：" in s:
        parts = re.split(r"[:：]", s, maxsplit=1)
        if len(parts) == 2:
            after = _TRAILING_PAREN_RE.sub("", parts[1].strip()).strip()
            if after and after != s:
                out.append(after)
                if "→" in after:
                    left = after.split("→")[0].strip()
                    if left:
                        out.append(left)
    seen: set[str] = set()
    unique: list[str] = []
    for c in out:
        c = c.strip()
        if c and c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


@dataclass(frozen=True)
class Found:
    target: ToolRuntimeTargetDto


@dataclass(frozen=True)
class Ambiguous:
    targets: tuple[ToolRuntimeTargetDto, ...]


@dataclass(frozen=True)
class WrongKind:
    target: ToolRuntimeTargetDto
    candidates: tuple[ToolRuntimeTargetDto, ...]


@dataclass(frozen=True)
class NotFound:
    candidates: tuple[ToolRuntimeTargetDto, ...]


Lookup = Found | Ambiguous | WrongKind | NotFound


class TargetIndex:
    """1 ターンぶんの targets を、表示名で引ける形にしたもの。"""

    def __init__(self, targets: Mapping[str, ToolRuntimeTargetDto]) -> None:
        self._by_key = dict(targets)
        self._all: tuple[ToolRuntimeTargetDto, ...] = tuple(targets.values())
        by_name: dict[str, list[ToolRuntimeTargetDto]] = defaultdict(list)
        for t in self._all:
            name = (t.display_name or "").strip()
            if name:
                by_name[name].append(t)
        self._by_name: Mapping[str, list[ToolRuntimeTargetDto]] = by_name

    @classmethod
    def from_context(cls, runtime_context: Any) -> TargetIndex:
        return cls(getattr(runtime_context, "targets", {}) or {})

    def of_kinds(self, kinds: Iterable[str]) -> tuple[ToolRuntimeTargetDto, ...]:
        """受け付ける種別の対象を、プロンプトに出た順で返す。"""
        accepted = frozenset(kinds)
        return tuple(t for t in self._all if t.kind in accepted)

    def lookup(self, written: str, *, accept_kinds: Sequence[str]) -> Lookup:
        accepted = frozenset(accept_kinds)
        for form in label_forms(written):
            hits = self._by_name.get(form)
            if hits is None:
                key_hit = self._by_key.get(form)
                if key_hit is None:
                    continue
                hits = [key_hit]
            matched = [t for t in hits if t.kind in accepted]
            if len(matched) == 1:
                return Found(matched[0])
            if matched:
                return Ambiguous(tuple(matched))
            return WrongKind(hits[0], self.of_kinds(accepted))
        return NotFound(self.of_kinds(accepted))


def candidate_names(targets: Iterable[ToolRuntimeTargetDto]) -> list[str]:
    """失敗文に載せる表示名。同名は 1 度だけ、順序は保つ。"""
    names: list[str] = []
    seen: set[str] = set()
    for t in targets:
        name = (t.display_name or "").strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def format_candidates(candidates_label: str, names: Sequence[str]) -> str:
    if not names:
        return f"有効な{candidates_label}: ありません"
    return f"有効な{candidates_label}: {' / '.join(names)}"


def require(
    lookup: Lookup,
    *,
    written: str,
    label_name: str,
    candidates_label: str | None = None,
    invalid_label_code: str = "INVALID_TARGET_LABEL",
    invalid_kind_code: str = "INVALID_TARGET_KIND",
    tool_is_exposed: ToolIsExposed | None = None,
) -> ToolRuntimeTargetDto:
    """引いた結果から対象を取り出す。取り出せない形はそれぞれの理由で失敗させる。

    失敗の文面は当人が次の一手を直すために読む。どの形でも「では何が書けるのか」
    を失わないよう、受け付ける種別の候補一覧を必ず添える。
    """
    candidates_label = candidates_label or label_name
    if isinstance(lookup, Found):
        return lookup.target
    if isinstance(lookup, Ambiguous):
        labels = "、".join(t.label for t in lookup.targets)
        raise ToolArgumentResolutionException(
            f"{label_name}「{written}」は複数の対象と一致します。表示されている名前を番号まで写すか、"
            f"短縮ラベル ({labels}) のいずれかで指定し直してください。",
            "AMBIGUOUS_TARGET_LABEL",
        )
    if isinstance(lookup, WrongKind):
        other = lookup.target
        kind_label = KIND_LABEL.get(other.kind, other.kind)
        parts = [f"「{written}」は{kind_label}で、{label_name}には使えません。"]
        advice = advice_for(other.kind, tool_is_exposed)
        if advice:
            parts.append(advice)
        parts.append(format_candidates(candidates_label, candidate_names(lookup.candidates)))
        raise ToolArgumentResolutionException(" ".join(parts), invalid_kind_code)
    raise ToolArgumentResolutionException(
        f"指定された{label_name}は現在の候補にありません: {written} → "
        f"{format_candidates(candidates_label, candidate_names(lookup.candidates))}",
        invalid_label_code,
    )


__all__ = [
    "KIND_LABEL",
    "Ambiguous",
    "Found",
    "Lookup",
    "NotFound",
    "TargetIndex",
    "ToolIsExposed",
    "WrongKind",
    "advice_for",
    "candidate_names",
    "format_candidates",
    "label_forms",
    "require",
    "strip_symmetric_quotes",
]
