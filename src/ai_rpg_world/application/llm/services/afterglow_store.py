"""Afterglow index — 「ぼんやり覚えてる」見出し一覧 (#526 段階 3 後続 PR-C)。

# 何のため

想起スロット (PR #580 / #583) は「鮮明な記憶」を扱う希少資源 (N=4)。
そこから押し出された記憶や、想起候補にはなったが score 閾値で slot に
入れなかった弱い hit を、1 行見出しとして並べて保持する layered な
記憶階層の下層がここ。

人間で言う「鮮明には浮かばないが、ヒントを与えれば思い出せる」状態を
構造で再現することで:

1. 想起の連続性 — 一度想起された記憶が一気に忘却されない
2. 弱い signal の救済 — score 閾値で slot から弾かれても見出しは残る
3. prefix cache 親和性 — 見出しは安定した順序で並ぶ
4. 能動想起の入口 — 別 PR で追加するツールで本文を引き戻せる素地

を提供する。

# 設計判断

- ``AfterglowEntry`` は frozen dataclass。再投入時は新しい entry に
  置き換える (immutable な更新)
- ``apply_afterglow_policy`` は pure function。境界値を testable に保つ
- store は in-memory sidecar。experiment run の単位で破棄される
- handle は ``ep_<episode_id 先頭 6 文字>``。同じ episode に同じ handle を
  保つことで、過去の prompt 履歴に残った handle が指す対象がずれない
  (= 過去事例: spot ラベルが tick ごとに変わって LLM が混乱した問題への
  構造的対策)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Protocol, runtime_checkable

from ai_rpg_world.domain.being.value_object.being_id import BeingId


class AfterglowSource(str, Enum):
    """afterglow に降りてきた経路。trace 分析のためにタグとして残す。"""

    SLOT_EVICTED = "slot_evicted"
    """slot から滞在期間 L 超過で退去してきた (= 「もう鮮明には浮かばないけど直前まで覚えていた」)。"""

    WEAK_RECALL = "weak_recall"
    """想起候補に上がったが slot の score 閾値を満たさず入れなかった弱い hit。"""


@dataclass(frozen=True)
class AfterglowEntry:
    """1 つの「ぼんやり覚えてる」見出し。

    heading は PR-B で SubjectiveEpisode に追加した 1 行サマリを参照する。
    """

    episode_id: str
    heading: str
    entered_tick: int
    source: AfterglowSource

    def __post_init__(self) -> None:
        if not isinstance(self.episode_id, str) or not self.episode_id.strip():
            raise ValueError("episode_id must be non-empty str")
        if not isinstance(self.heading, str) or not self.heading.strip():
            raise ValueError("heading must be non-empty str")
        if not isinstance(self.entered_tick, int) or isinstance(self.entered_tick, bool):
            raise TypeError("entered_tick must be int")
        if self.entered_tick < 0:
            raise ValueError("entered_tick must be 0 or greater")
        if not isinstance(self.source, AfterglowSource):
            raise TypeError("source must be AfterglowSource")


def apply_afterglow_policy(
    *,
    prev_index: Sequence[AfterglowEntry],
    incoming: Sequence[AfterglowEntry],
    current_tick: int,
    capacity: int,
    max_residence: int,
) -> tuple[AfterglowEntry, ...]:
    """前 tick の index + 新規追加から、次の index を決める純関数。

    アルゴリズム:

    1. ``prev_index`` のうち滞在期間 ``max_residence`` を超えたものを退去
       (= ``current_tick - entered_tick >= max_residence`` のとき消す)
    2. ``incoming`` の各エントリについて:
       - 同 episode_id が既に居れば置き換え (= リハーサルで entered_tick 更新)
       - 居なければ追加
    3. 全件数が ``capacity`` を超えていれば、``entered_tick`` の古い順で
       超過分を退去 (FIFO)

    順序は ``entered_tick`` 昇順 → 同値は ``episode_id`` 昇順で安定させ、
    prompt section に並ぶ順を prefix cache フレンドリに保つ。

    新規が来なくても (= ``incoming`` が空) 経過 tick で退去が起きうるため、
    呼び出し側は毎 tick 実行することを想定。
    """
    if not isinstance(current_tick, int) or isinstance(current_tick, bool):
        raise TypeError("current_tick must be int")
    if current_tick < 0:
        raise ValueError("current_tick must be 0 or greater")
    if capacity < 0:
        raise ValueError("capacity must be 0 or greater")
    if max_residence < 0:
        raise ValueError("max_residence must be 0 or greater")

    # 1. M_L 超過で退去 + 2. リハーサル / 新規追加を 1 つの dict で表現
    by_id: Dict[str, AfterglowEntry] = {}
    for e in prev_index:
        age = current_tick - e.entered_tick
        if age < 0 or age >= max_residence:
            continue
        by_id[e.episode_id] = e
    for e in incoming:
        # 既存があれば置き換え (= 新しい entered_tick / source で上書き)
        by_id[e.episode_id] = e

    # 3. capacity 超過は entered_tick の古い順から落とす
    ordered = sorted(by_id.values(), key=lambda e: (e.entered_tick, e.episode_id))
    if len(ordered) > capacity:
        ordered = ordered[len(ordered) - capacity :]
    return tuple(ordered)


_HANDLE_PREFIX_LEN = 6


def make_afterglow_handle(episode_id: str) -> str:
    """episode_id を「ep_<先頭 6 文字>」形式の安定 handle に縮める。

    同じ episode_id からは常に同じ handle が返るため、過去の prompt に
    残った handle 表記と現在の意味がずれない。LLM の能動想起ツール
    (PR-D で追加予定) ではこの handle を引数として受け取る。

    6 文字未満の id でもそのまま使える形にする (= 先頭 N 文字を取るだけで
    crash させない)。
    """
    if not isinstance(episode_id, str):
        raise TypeError("episode_id must be str")
    s = episode_id.strip()
    if not s:
        raise ValueError("episode_id must be non-empty")
    return f"ep_{s[:_HANDLE_PREFIX_LEN]}"


@runtime_checkable
class IAfterglowStore(Protocol):
    """being ごとに「ぼんやり覚えてる」index を保持する sidecar。"""

    def get_index(self, being_id: BeingId) -> tuple[AfterglowEntry, ...]:
        """現在の index を返す。未記録なら空 tuple。"""
        ...

    def apply_decision(
        self,
        being_id: BeingId,
        new_index: Sequence[AfterglowEntry],
    ) -> None:
        """``apply_afterglow_policy`` の結果を反映する。"""
        ...


class InMemoryAfterglowStore(IAfterglowStore):
    """プロセスメモリ常駐の sidecar 実装。experiment run の単位で破棄。

    being 同士は外側の dict で分離 (相互干渉なし)。
    """

    def __init__(self) -> None:
        self._by_being: Dict[BeingId, tuple[AfterglowEntry, ...]] = {}

    def get_index(self, being_id: BeingId) -> tuple[AfterglowEntry, ...]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        return self._by_being.get(being_id, ())

    def apply_decision(
        self,
        being_id: BeingId,
        new_index: Sequence[AfterglowEntry],
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        self._by_being[being_id] = tuple(new_index)


__all__ = [
    "AfterglowSource",
    "AfterglowEntry",
    "apply_afterglow_policy",
    "make_afterglow_handle",
    "IAfterglowStore",
    "InMemoryAfterglowStore",
]
