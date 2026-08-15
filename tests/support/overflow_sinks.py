"""テストが付与ヘルパーへ渡す、溢れの行き先。

本番の行き先は 2 つ (足元へ落とす / 呼ばれたら落ちる) だが、テストの下ごしらえ
では**わざと所持品を満杯にする**ことがある (満杯の挙動そのものを試すとき)。
そこで落ちると、試したい振る舞いに辿り着く前に止まる。

`IGNORE_OVERFLOW` は「このテストは溢れを見ていない」という宣言である。溢れを
見たいテストは `CollectingOverflowSink` を使って、何が溢れたかを確かめること。
"""

from __future__ import annotations

from typing import List, Tuple


def IGNORE_OVERFLOW(player_id, spec_ids) -> None:  # noqa: N802
    """溢れを見ないテスト用。**本番では使わない。**"""
    return None


class CollectingOverflowSink:
    """何が溢れたかを覚えておく行き先 (溢れを見たいテスト用)。"""

    def __init__(self) -> None:
        self.calls: List[Tuple[object, Tuple[object, ...]]] = []

    def __call__(self, player_id, spec_ids) -> None:
        self.calls.append((player_id, tuple(spec_ids)))

    @property
    def overflowed(self) -> Tuple[object, ...]:
        return tuple(spec for _pid, specs in self.calls for spec in specs)
