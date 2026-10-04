"""観測の契約とエージェントの持ち物から、状況の 6 つの項目を組み立てる (#1414)。

環境から受け取るのは観測の契約 (design_decisions D1463) だけにする。世界状態への照会、
ゲームの ID、tags、cue は使わない。

清算待ちの予期は未解決の項目にだけ入れ、やろうとしていることには入れない。2 つの項目に
同じ文が入ると、項目を選んでも同じ信念が引けてしまい、項目を分けた意味が薄れる。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ai_rpg_world.application.being.recall.situation import Situation
from ai_rpg_world.being.contract import (
    UNKNOWN,
    Observation,
    OwnBodyState,
    ToldOrWritten,
)

# 直前の数手ぶんだけを見る。古い出来事まで入れると、いまの状況が問い合わせ文の中で薄まる。
HAPPENING_LIMIT = 3
COUNTERPART_LIMIT = 3
OWN_STATE_LIMIT = 2
UNRESOLVED_LIMIT = 3


@dataclass(frozen=True)
class AgentHoldings:
    """項目の材料のうち、観測ではなくエージェント自身が持っているもの。"""

    goal: str | None = None
    inner_thought: str | None = None
    #: 古い順。新しいものから ``UNRESOLVED_LIMIT`` 件を項目に入れる。
    open_expectations: tuple[str, ...] = ()


def assemble_situation(
    observations: Sequence[Observation], holdings: AgentHoldings
) -> Situation:
    """``observations`` は新しい順に渡す。"""
    places = [o.place for o in observations if o.place is not UNKNOWN]
    counterparts: list[str] = []
    for o in observations:
        if not o.subject_is_self and o.subject_name is not UNKNOWN:
            counterparts.append(o.subject_name)
        if (
            isinstance(o.route, ToldOrWritten)
            and not o.subject_is_self
            and o.source is not UNKNOWN
        ):
            counterparts.append(o.source)
    return Situation(
        place=tuple(places[:1]),
        counterpart=_unique(counterparts)[:COUNTERPART_LIMIT],
        own_state=tuple(
            o.body for o in observations if isinstance(o.route, OwnBodyState)
        )[:OWN_STATE_LIMIT],
        intent=_present(holdings.goal, holdings.inner_thought),
        happening=tuple(
            o.body for o in observations if not isinstance(o.route, OwnBodyState)
        )[:HAPPENING_LIMIT],
        unresolved=_present(*reversed(holdings.open_expectations))[:UNRESOLVED_LIMIT],
    )


def _unique(texts: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(texts))


def _present(*texts: str | None) -> tuple[str, ...]:
    return tuple(t for t in texts if t is not None and t.strip())


__all__ = ["AgentHoldings", "assemble_situation"]
