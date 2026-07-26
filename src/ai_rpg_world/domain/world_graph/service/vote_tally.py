"""会議の投票を集計する (純粋関数)。

本家 Among Us に合わせて **単純多数 (plurality)・同点は追放なし・棄権あり**
(docs/memory_system/meeting_and_voting_design.md §2.3)。

## 棄権も 1 票として数える

棄権を「投票していない」と同じに扱うと、全員が保留を選んだときに「まだ
投票が終わっていない」と区別が付かない。棄権は**保留するという意思表示**
であって票の不在ではない。棄権が最多なら誰も追放されない。

## 同点で追放しない

誰も追放されないことも結果であり、「誰も確信を持てなかった」という情報に
なる。同点をどちらかに倒すと、その情報が消える。

## 過半数ではなく単純多数

設計 doc の文例には「過半数に届かず」とあるが、本家は最多票で決まる
(過半数は要らない)。ユーザが「本家っぽさを優先」と決めたので単純多数を採る。
文例のほうを実装に合わせて直した。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Dict, Mapping, Optional

from ai_rpg_world.domain.player.value_object.player_id import PlayerId

#: 棄権を表す投票先。
SKIP: None = None


@dataclass(frozen=True)
class VoteResult:
    """集計の結果。

    追放の有無にかかわらず、**全員に配れるだけの情報を持つ**
    (設計 doc §6.4)。配らないと「誰も追放されなかった」のか「誰かが追放
    されたが自分は見ていなかった」のかを区別できない。
    """

    #: 追放される player。同点や棄権最多なら None。
    ejected_player_id: Optional[PlayerId]
    #: 指名された player ごとの得票数 (棄権は含まない)。
    counts: Dict[PlayerId, int]
    #: 棄権の数。
    skip_count: int
    #: 誰が誰に入れたか。投票行動そのものが次の会議の材料になる。
    ballots: Dict[PlayerId, Optional[PlayerId]]


def resolve_vote(
    ballots: Mapping[PlayerId, Optional[PlayerId]]
) -> VoteResult:
    """投じられた票から追放先を決める。

    Args:
        ballots: 投票者 -> 投票先。投票先 ``None`` は棄権。
    """
    counts: Counter = Counter()
    skip_count = 0
    for target in ballots.values():
        if target is None:
            skip_count += 1
            continue
        counts[target] += 1

    ejected: Optional[PlayerId] = None
    if counts:
        top = max(counts.values())
        leaders = [pid for pid, n in counts.items() if n == top]
        # 棄権が最多 (または同数) なら誰も追放されない。棄権は票なので、
        # 名指しと並んだ時点で「決まらなかった」になる。
        if len(leaders) == 1 and top > skip_count:
            ejected = leaders[0]

    return VoteResult(
        ejected_player_id=ejected,
        counts=dict(counts),
        skip_count=skip_count,
        ballots=dict(ballots),
    )


__all__ = ["SKIP", "VoteResult", "resolve_vote"]
