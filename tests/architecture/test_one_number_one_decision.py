"""設計判断集の見出し番号が、判断 1 件につき 1 つであることを見張る。

## なぜこの試験が要るか

`docs/design_decisions.md` は本文のあちこちから **番号で** 参照される
(「`docs/design_decisions.md` の #27 を参照」)。番号が重複すると、その参照は
**どちらの判断を指しているか決まらない**。読み手は間違ったほうを読んで、
関係のない規律に従うことになる。

これは並行 PR で起きる。**それぞれが「次の番号」を自分で数えて末尾に足す**ので、
同時に開いていた 2 本が同じ番号を取る。実際に main で 7 組が重複していた
(#77 #78 #109 #122 #123 #125 #131)。どれも人が読んで気づいたものではなく、
別の作業のついでに見つかっている。

## 何を見ないか

**並びの単調さは見ない。** 節の並べ替えは意味のある編集で、番号順に並んでいる
必要は無い。壊れるのは重複だけである。
"""

from __future__ import annotations

import collections
import re
from pathlib import Path

_DECISIONS = Path(__file__).resolve().parents[2] / "docs" / "design_decisions.md"
_HEADING = re.compile(r"^## (\d+)\. (.+)$")


def _numbered_headings() -> list[tuple[int, str]]:
    return [
        (int(m.group(1)), m.group(2))
        for line in _DECISIONS.read_text(encoding="utf-8").splitlines()
        if (m := _HEADING.match(line))
    ]


class TestOneNumberMeansOneDecision:
    """番号から判断が一意に決まる。"""

    def test_no_number_is_used_twice(self) -> None:
        """同じ番号の見出しが 2 つ以上ない。

        重複すると、本文からの「#27 を参照」がどちらを指すか決まらない。
        """
        counts = collections.Counter(n for n, _ in _numbered_headings())
        duplicated = {
            n: [t for m, t in _numbered_headings() if m == n]
            for n, c in counts.items()
            if c > 1
        }

        assert duplicated == {}, (
            "設計判断集で番号が重複しています。**末尾の最大番号 + 1** を使って"
            f"ください: {duplicated}"
        )

    def test_the_headings_are_actually_being_read(self) -> None:
        """番号つきの見出しが実際に読めている (**正の対照**)。

        これが無いと、上の検査は見出しの書式が変わって **1 件も拾えなく
        なった**ときにも緑になる。

        件数だけでなく、**本文から番号で参照されている判断が実際に拾えて
        いる**ことまで見る。#27 は per-Being store を足すときの手順として
        `CLAUDE.md` から参照されている。
        """
        headings = _numbered_headings()

        assert len(headings) > 100
        assert 27 in {n for n, _ in headings}
