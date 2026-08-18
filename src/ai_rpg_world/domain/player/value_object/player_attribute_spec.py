"""人が持つ属性の宣言と、条件を満たせるかの分類。

## なぜ要るか

`PlayerStatusAggregate.state` は自由 dict で、`trade: baker` (生業) も
`role: werewolf` (役割) も `disguised: true` (変装) も engine から見て同じだった。
そのため **満たせない条件が「いま無理」か「永久に無理」か**を、世界の側が答えられ
なかった。

物体には答えがある。#380 で、シナリオの宣言 (`reactive_bindings`) と突き合わせて
「時間で戻る」「もう変わらない」を区別できるようにした。**人の側には、その仕組みが
無い。** 今回はその非対称を埋める。

## 埋めないと何が起きるか

実 run (v3.2 t24–t33) で、焼き手が摘み手に**窯の使い方を教える取引**を持ちかけ、
摘み手はそれを受けて待った。生業は変えられないので**永久に焼けない**。

engine は「足りない前提を先に満たすこと」と助言していた。この既定は物体には
無害だが、**変えられない属性についてはいちばん有害**である。**10 手番が消えた。**

## ここでは言葉を持たない

返すのは「世界の規則として可能か」だけで、**何と言うかは知らない**。文面は
プロンプトを組む側 (application) の責務で、そこには既に助言の一覧がある。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional, Tuple

from ai_rpg_world.domain.player.exception.player_exceptions import (
    PlayerAttributeSpecValidationException,
)


class AttributeVisibility(Enum):
    """その属性を、本人以外が知っていてよいか。

    **二択で始める。** 「誰から見て」を分ける必要が出たら、そのとき広げる。
    """

    #: 全員が知っている (生業・見た目など)。理由として口に出してよい。
    PUBLIC = "public"
    #: 本人だけが知っている (役割・変装など)。**存在も伏せる。**
    SECRET = "secret"


class ConditionSatisfiability(Enum):
    """その行為者が、その条件を満たせるか。

    **満たしているかではなく、満たせるか。** 満たしていない理由が
    「まだ」なのか「永久に」なのかで、次に取るべき手が正反対になる。
    """

    #: いま満たしている。
    SATISFIED = "satisfied"
    #: いまは満たしていないが、変えられる。
    NOT_YET = "not_yet"
    #: この行為者には永久に満たせない。
    NEVER = "never"


@dataclass(frozen=True)
class PlayerAttributeSpec:
    """人が持つ属性 1 つの宣言。"""

    name: str
    display_name: str
    visibility: AttributeVisibility
    mutable: bool
    #: 取りうる値。**任意** — 数値や時刻の属性には列挙が無い。
    values: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise PlayerAttributeSpecValidationException("属性名は空にできません")
        if not str(self.display_name).strip():
            raise PlayerAttributeSpecValidationException(
                f"属性 {self.name} の表示名は空にできません"
            )
        if not isinstance(self.visibility, AttributeVisibility):
            raise PlayerAttributeSpecValidationException(
                f"属性 {self.name} の visibility が不正です: {self.visibility!r}"
            )
        if not isinstance(self.mutable, bool):
            raise PlayerAttributeSpecValidationException(
                f"属性 {self.name} の mutable は真偽値で指定してください: "
                f"{self.mutable!r}"
            )

    def allows(self, value: Any) -> bool:
        """その値を取りうるか。列挙が無ければ何でも取りうる。"""
        return not self.values or str(value) in self.values


@dataclass(frozen=True)
class PlayerAttributeSpecs:
    """シナリオが宣言した属性の一覧。

    **宣言の無い属性は、従来どおり扱う** (変えられる前提)。既存シナリオが
    1 ビットも変わらないことを、この既定が保証する。
    """

    by_name: Mapping[str, PlayerAttributeSpec]

    @classmethod
    def empty(cls) -> "PlayerAttributeSpecs":
        return cls(by_name={})

    def spec_of(self, name: str) -> Optional[PlayerAttributeSpec]:
        return self.by_name.get(name)

    def satisfiability(
        self,
        required_state: Mapping[str, Any],
        actor_state: Optional[Mapping[str, Any]],
    ) -> ConditionSatisfiability:
        """その行為者が、要求された状態を満たせるか。

        **行為者の状態が読めないときは `NOT_YET`。** 分からないことを
        「永久に無理」と断定しない。断定すると、成立しうる行動を諦めさせる。

        **1 つでも「変えられない値が食い違っている」なら `NEVER`。** 残りが
        変えられても、全体としては永久に満たせない。
        """
        if not required_state:
            return ConditionSatisfiability.SATISFIED
        if actor_state is None:
            return ConditionSatisfiability.NOT_YET

        unmet = {
            key: wanted
            for key, wanted in required_state.items()
            if actor_state.get(key) != wanted
        }
        if not unmet:
            return ConditionSatisfiability.SATISFIED
        for key in unmet:
            spec = self.by_name.get(key)
            if spec is not None and not spec.mutable:
                return ConditionSatisfiability.NEVER
        return ConditionSatisfiability.NOT_YET


__all__ = [
    "AttributeVisibility",
    "ConditionSatisfiability",
    "PlayerAttributeSpec",
    "PlayerAttributeSpecs",
]
