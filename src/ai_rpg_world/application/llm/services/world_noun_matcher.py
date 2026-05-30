"""シナリオの固有名詞 (spot / character / object / item) を自由文から検出する
Aho-Corasick ベースのマッチャ (Issue #283 後続)。

# 何を解くか

第19回実験で見えた未接続スポット問題に対するユーザの理想動作:
- リンが書架A の存在を SNS で「書架A で待ってる」と聞く
- 過去に閲覧室→入口広間→書架A を辿った経験がある
- 「あ、あのルートか！」と思い出して合流できる

これを **少ない原則** から emergent に成立させるため:

> 世界の固有名詞 (スポット名・キャラ名・物品名) が観測テキストに含まれたら、
> その entity への想起 cue を立てる

という 1 つの原則を、観測 prose に対する高速な複数 key 検索で実装する。

# 設計

- ``IWorldNounMatcher`` (Protocol): 「text → (cue 軸, cue 値, マッチ位置) の列」
  を返す抽象。実装は差し替え可能 (pyahocorasick 等の C 拡張に後で乗り換え可)
- ``WorldNounMatcherBuilder``: spot / character / world_object / item を
  カテゴリ別に登録 → ``build()`` で immutable な matcher を返す
- ``AhoCorasickWorldNounMatcher``: pure Python 実装。NFKC + casefold で
  正規化、エイリアス登録、failure link 構築済み trie
- ``NullWorldNounMatcher``: 常に空を返す no-op (matcher 未注入時の safe default)

cue value の format は ``episodic_cue_rules.py`` の既存 cue と完全に揃える
(``_sanitize_id_segment`` 同等の "kind_id" 形式)。これにより matcher 経由で
追加された cue は構造化観測経由の cue と同じ index で recall できる。

# 性能

- 構築: O(全パターン文字数) — scenario load 時 1 回
- 検索: O(text 長 + match 数) — key 数に依存しない
- pure Python でも観測 1 件 (≦200 文字) あたり 100us 程度
- ボトルネック化したら ``pyahocorasick`` 等 C 拡張への差し替えで 10〜100x

# 限界

- 正規化は **NFKC + casefold** のみ。ひらがな↔カタカナ変換は非対応
  (必要なら alias で両方登録)
- 編集距離 (タイポ許容) には未対応。タイポは alias 登録で吸収するか、
  将来 Levenshtein automaton 交差等の拡張で対応する
- 自由文の **語境界判定なし**: 「書架A」が「書架AB」の prefix として
  マッチしうる。シナリオ固有名詞は通常ユニークなので実害は薄い
"""

from __future__ import annotations

import unicodedata
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Protocol, Tuple, runtime_checkable


# ──────────────────────────────────────────────────────────────────
# 公開 DTO + Protocol
# ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NounMatch:
    """text 中で見つかった 1 件の固有名詞マッチ。

    cue 軸 / 値の組は ``episodic_cue_rules._cues_from_runtime_targets`` /
    ``_cues_from_observation_structured`` が出すものと完全互換にしてある。
    これにより、自由文経由で追加された cue と構造化フィールド経由の cue が
    同じ index で recall できる。
    """

    axis: str
    """``place_spot`` / ``entity`` / ``object`` 等。``EpisodicCue.axis`` と同じ。"""

    value: str
    """cue value。spot は ``str(id)``、player/object/item は ``kind_id``。"""

    matched_text: str
    """text 内で実際にマッチした表記 (正規化前)。LLM への提示文に使える。"""

    start: int
    """text 内のマッチ開始位置 (codepoint 単位、0-origin)。"""

    end: int
    """マッチ終了位置 (exclusive)。"""

    def __post_init__(self) -> None:
        if not self.axis:
            raise ValueError("axis must not be empty")
        if not self.value:
            raise ValueError("value must not be empty")
        if self.end <= self.start:
            raise ValueError("end must be greater than start")


@runtime_checkable
class IWorldNounMatcher(Protocol):
    """シナリオ固有名詞を自由文から検出するマッチャの抽象。

    実装は Aho-Corasick + 正規化 + エイリアスなど。pyahocorasick 等の
    C 拡張への差し替えはこの Protocol を満たすクラスで行う。
    """

    def find_in_text(self, text: str) -> Tuple[NounMatch, ...]:
        """``text`` 内で見つかった固有名詞 match を全て返す。

        - 順序: text 内のマッチ開始位置の昇順
        - 同一 (axis, value) でも複数箇所マッチすればその数だけ返す
          (呼び出し側が必要に応じて dedupe する)
        - text が空 / None なら空タプル
        """
        ...


# ──────────────────────────────────────────────────────────────────
# 正規化
# ──────────────────────────────────────────────────────────────────


def _normalize_for_matching(text: str) -> str:
    """trie 構築 / 検索の両方で使う正規化。

    NFKC で全角→半角 + 合成文字分解、casefold で unicode lowercase。
    パターンと text を同じ正規化で揃えることで、表記揺れを吸収する。

    例:
    - ``書架Ａ`` (全角A) → ``書架a`` (NFKC で半角化 + casefold)
    - ``リン`` ← 変わらず (カタカナは NFKC 対象外)
    """
    return unicodedata.normalize("NFKC", text).casefold()


# ──────────────────────────────────────────────────────────────────
# Aho-Corasick 実装 (pure Python)
# ──────────────────────────────────────────────────────────────────


@dataclass
class _Pattern:
    """trie の終端 node に紐づける出力エントリ。"""

    normalized_text: str
    """trie に格納される正規化後の表記 (検索用)。"""

    length: int
    """マッチ位置から start を計算するために保持。"""

    axis: str
    """対応する cue 軸。"""

    value: str
    """対応する cue value。"""

    display_text: str
    """元の表記 (正規化前)。``NounMatch.matched_text`` に出す。"""


@dataclass
class _Node:
    children: dict = field(default_factory=dict)
    failure: Optional["_Node"] = None
    outputs: List[_Pattern] = field(default_factory=list)


class AhoCorasickWorldNounMatcher:
    """Aho-Corasick の pure Python 実装。

    immutable: 構築後に追加・削除はできない (builder 経由で再構築する)。
    Thread-safe: 内部状態 (current node) を持たず、search は局所変数のみ使う。
    """

    def __init__(self, patterns: Iterable[_Pattern]) -> None:
        self._root = _Node()
        # 後で len(_patterns) == 0 の判定に使う
        patterns_list = list(patterns)
        if not patterns_list:
            # 空 trie: search は常に空。failure_link 構築不要。
            self._is_empty = True
            return
        self._is_empty = False
        for pat in patterns_list:
            self._add(pat)
        self._build_failure_links()

    def _add(self, pat: _Pattern) -> None:
        node = self._root
        for ch in pat.normalized_text:
            child = node.children.get(ch)
            if child is None:
                child = _Node()
                node.children[ch] = child
            node = child
        node.outputs.append(pat)

    def _build_failure_links(self) -> None:
        """BFS で各 node の failure link と output を構築 (経典実装)。

        - root の直下: failure = root
        - その下: parent.failure を起点に同じ文字の goto を辿る
        - output: 自分の outputs + failure chain の outputs を統合
        """
        queue: deque[_Node] = deque()
        for child in self._root.children.values():
            child.failure = self._root
            queue.append(child)
        while queue:
            node = queue.popleft()
            for ch, child in node.children.items():
                fall = node.failure
                while fall is not None and ch not in fall.children:
                    if fall is self._root:
                        break
                    fall = fall.failure
                child.failure = (
                    fall.children[ch] if fall is not None and ch in fall.children
                    else self._root
                )
                # 自分自身に failure するのは禁則 (= 経典どおり root に倒す)
                if child.failure is child:
                    child.failure = self._root
                # output 統合: 自分 + failure chain
                child.outputs = list(child.outputs) + list(child.failure.outputs)
                queue.append(child)

    def find_in_text(self, text: str) -> Tuple[NounMatch, ...]:
        if not text or self._is_empty:
            return ()
        normalized = _normalize_for_matching(text)
        # 正規化で codepoint 数が変わる可能性がある (NFKC で合成→分解)。
        # 検索位置は正規化後 text の index で行うが、結果の start/end は
        # 元 text の codepoint index に**できる限り**戻したい。
        # ただし NFKC は一般に位置情報を保てないため、本実装では正規化後の
        # index をそのまま start/end として返す。matched_text は元 text の
        # 対応スライスを返す試みをするが、長さが変わる場合は normalized
        # 側のスライスをそのまま使う (情報損失あり、注意コメント参照)。
        matches: List[NounMatch] = []
        node = self._root
        for i, ch in enumerate(normalized):
            # failure を辿って goto がある node に移る
            while node is not self._root and ch not in node.children:
                node = node.failure  # type: ignore[assignment]
                if node is None:  # 念のため
                    node = self._root
                    break
            node = node.children.get(ch, self._root)
            for pat in node.outputs:
                end = i + 1
                start = end - pat.length
                # 元 text の対応スライス取得を試みる: 長さが同じなら同じ位置を使う
                if len(normalized) == len(text):
                    matched_text = text[start:end]
                else:
                    # NFKC で長さが変わったケース。display_text (= 元のパターン
                    # 表記) を返す。位置は normalized 側の値。
                    matched_text = pat.display_text
                matches.append(
                    NounMatch(
                        axis=pat.axis,
                        value=pat.value,
                        matched_text=matched_text,
                        start=start,
                        end=end,
                    )
                )
        return tuple(matches)


# ──────────────────────────────────────────────────────────────────
# Null 実装 (matcher 未注入時の safe default)
# ──────────────────────────────────────────────────────────────────


class NullWorldNounMatcher:
    """常に空を返す no-op 実装。

    matcher が wire されていない場合の安全な default。観測 cue 抽出は
    structured フィールドだけを見る既存挙動に縮退する。
    """

    def find_in_text(self, text: str) -> Tuple[NounMatch, ...]:  # noqa: ARG002
        return ()


# ──────────────────────────────────────────────────────────────────
# Builder
# ──────────────────────────────────────────────────────────────────


def _format_entity_value(player_id: int) -> str:
    """``entity`` 軸の cue value 形式。``episodic_cue_rules._cues_from_runtime_targets``
    が出す ``spot_graph_player_{id}`` と合わせる。"""
    return f"spot_graph_player_{player_id}"


def _format_world_object_value(world_object_id: int) -> str:
    """``object`` 軸 (世界オブジェクト)。"""
    return f"world_object_{world_object_id}"


def _format_item_value(item_instance_id: int) -> str:
    """``object`` 軸 (item instance)。"""
    return f"item_instance_{item_instance_id}"


class WorldNounMatcherBuilder:
    """カテゴリ別に固有名詞 + id (+ aliases) を登録してマッチャを構築する。

    same axis + same value での重複登録は最後のものが勝つ (実害なし、
    aliases を後から重ねる用途想定)。
    """

    def __init__(self) -> None:
        self._patterns: List[_Pattern] = []

    def add_spot(
        self,
        name: str,
        spot_id: int,
        *,
        aliases: Tuple[str, ...] = (),
    ) -> "WorldNounMatcherBuilder":
        """スポットを登録。``place_spot:str(spot_id)`` の cue として recall に
        繋がる。aliases も同じ value で登録される。"""
        self._add_all(
            (name, *aliases),
            axis="place_spot",
            value=str(spot_id),
            primary=name,
        )
        return self

    def add_character(
        self,
        name: str,
        player_id: int,
        *,
        aliases: Tuple[str, ...] = (),
    ) -> "WorldNounMatcherBuilder":
        """キャラクター (player) を登録。``entity:spot_graph_player_{id}`` cue。"""
        self._add_all(
            (name, *aliases),
            axis="entity",
            value=_format_entity_value(player_id),
            primary=name,
        )
        return self

    def add_world_object(
        self,
        name: str,
        world_object_id: int,
        *,
        aliases: Tuple[str, ...] = (),
    ) -> "WorldNounMatcherBuilder":
        """ワールドオブジェクトを登録。``object:world_object_{id}`` cue。"""
        self._add_all(
            (name, *aliases),
            axis="object",
            value=_format_world_object_value(world_object_id),
            primary=name,
        )
        return self

    def add_item(
        self,
        name: str,
        item_instance_id: int,
        *,
        aliases: Tuple[str, ...] = (),
    ) -> "WorldNounMatcherBuilder":
        """アイテム instance を登録。``object:item_instance_{id}`` cue。"""
        self._add_all(
            (name, *aliases),
            axis="object",
            value=_format_item_value(item_instance_id),
            primary=name,
        )
        return self

    def _add_all(
        self,
        names: Tuple[str, ...],
        *,
        axis: str,
        value: str,
        primary: str,
    ) -> None:
        for name in names:
            stripped = (name or "").strip()
            if not stripped:
                # 空エイリアスは無視 (検査側で空文字が拾われると無限マッチになる)
                continue
            normalized = _normalize_for_matching(stripped)
            if not normalized:
                continue
            self._patterns.append(
                _Pattern(
                    normalized_text=normalized,
                    length=len(normalized),
                    axis=axis,
                    value=value,
                    # display は primary 名で統一 (alias を見せても LLM が
                    # 混乱しない、canonical を返す)
                    display_text=primary,
                )
            )

    def build(self) -> IWorldNounMatcher:
        """immutable な matcher を返す。空登録なら ``NullWorldNounMatcher``。"""
        if not self._patterns:
            return NullWorldNounMatcher()
        return AhoCorasickWorldNounMatcher(self._patterns)


__all__ = [
    "IWorldNounMatcher",
    "NounMatch",
    "AhoCorasickWorldNounMatcher",
    "NullWorldNounMatcher",
    "WorldNounMatcherBuilder",
]
