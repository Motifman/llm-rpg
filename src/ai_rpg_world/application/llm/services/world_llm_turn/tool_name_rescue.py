"""LLM tool 名 typo の救済ヘルパ。"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Iterable, Optional

_SUFFIX_RATIO_CUTOFF: float = 0.5
_SHORTENED_NAME_SCORE: float = 0.95

# PR-CC (Y_after_pr639_640 後続): 旧 ``spot_graph_`` prefix を廃止した後も、
# LLM は数 tick / 数 turn の間は「習慣」で ``spot_graph_pickup`` のような旧
# prefix 付き名を投げてくる可能性が高い。fuzzy match は「共通 prefix segment
# が 1 つ以上」を要求するため、旧 prefix 付き入力は valid (= bare 名) に対して
# 一切マッチしない。この差を吸収するため、requested の先頭が旧 prefix なら
# 剥がしたバージョンでも比較を試みる。
_LEGACY_TOOL_PREFIXES: tuple[str, ...] = ("spot_graph_",)


def suggest_closest_tool_name(
    requested: str, valid_tools: Iterable[str]
) -> Optional[str]:
    """typo っぽい tool 名から、最も近い valid tool 名 1 件を返す。

    共通 prefix segment が 1 つも無い候補は除外し、残った候補のうち suffix の
    類似度 (cutoff = ``_SUFFIX_RATIO_CUTOFF`` = 0.5) が最も高いものを返す。
    短縮形 (= requested の suffix が空) は ``_SHORTENED_NAME_SCORE`` 固定で
    常に救う。

    cutoff 0.5 は ``speech_speech → speech_speak`` の suffix 比較 ratio が
    0.545 になる事実から決定した境界値。これ未満にすると想像由来 typo
    (= ``gather`` / ``harvest``) の false positive が増える。

    候補が無ければ ``None``。「想像由来」(= ``gather`` / ``harvest`` のような
    独立した語) は本関数では救わず、``valid_tools`` 一覧の併記で agent に
    再選択させる設計。
    """
    if not isinstance(requested, str) or not requested:
        return None
    valid_list = [v for v in valid_tools if isinstance(v, str) and v]
    if not valid_list:
        return None

    # PR-CC 追加: 旧 prefix 剥がしを試す (bare 名との fuzzy 比較を可能にする)。
    # 「spot_graph_pickup → pickup_item」のような救済経路。
    # 元の requested と剥がした版の両方を候補にして、スコアが高い方を選ぶ。
    candidates_to_try: list[str] = [requested]
    for legacy in _LEGACY_TOOL_PREFIXES:
        if requested.startswith(legacy) and len(requested) > len(legacy):
            candidates_to_try.append(requested[len(legacy):])
            break

    best: Optional[str] = None
    best_score: float = 0.0
    for req_variant in candidates_to_try:
        variant_best, variant_score = _fuzzy_score_variant(req_variant, valid_list, SequenceMatcher)
        if variant_score > best_score:
            best_score = variant_score
            best = variant_best

    # strict `>` を使う: `harvest` vs `travel_to` が ratio=0.5 で false positive
    # にならないように、cutoff と等しい match は救わない。`speech_speak`
    # (= ratio 0.545) は通る。
    if best_score > _SUFFIX_RATIO_CUTOFF:
        return best
    return None


def _fuzzy_score_variant(
    requested: str, valid_list: list[str], SequenceMatcher
) -> tuple[Optional[str], float]:
    """1 つの ``requested`` variant について、valid 側から最高スコアを持つ
    候補を返す。``suggest_closest_tool_name`` の内部ヘルパー。"""
    req_parts = requested.split("_")
    best: Optional[str] = None
    best_score: float = 0.0
    for cand in valid_list:
        cand_parts = cand.split("_")
        common = 0
        for r, c in zip(req_parts, cand_parts):
            if r == c:
                common += 1
            else:
                break
        if common == 0:
            continue  # 全く異なるカテゴリ
        req_suffix = "_".join(req_parts[common:])
        cand_suffix = "_".join(cand_parts[common:])
        if not req_suffix and cand_suffix:
            # 短縮形 (e.g. spot_graph_pickup → spot_graph_pickup_item)
            score = _SHORTENED_NAME_SCORE
        elif not cand_suffix and req_suffix:
            # 逆短縮 (= candidate がより短い)。これは LLM が「サフィックス付
            # きの方を呼びたかった」と推定するには弱いので 0.0 扱い
            score = 0.0
        elif not req_suffix and not cand_suffix:
            # 完全一致 (= requested == cand。この経路は handler が見つかって
            # いるはずなので来ない、念のため)
            score = 1.0
        else:
            score = SequenceMatcher(None, req_suffix, cand_suffix).ratio()
        if score > best_score:
            best_score = score
            best = cand
    return best, best_score


def build_unsupported_tool_message(
    *, requested: str, valid_tools: Iterable[str]
) -> str:
    """UNSUPPORTED_TOOL 用のエラーメッセージを組み立てる。

    含む情報:
    1. typoed name (= LLM が何を呼ぼうとしたか)
    2. fuzzy suggestion (= 「もしかして 'X' ですか?」、近い候補がある時のみ)
    3. valid tool 一覧 (= 想像由来 typo を救うため常時併記)
    """
    valid_sorted = sorted(v for v in valid_tools if isinstance(v, str) and v)
    suggestion = suggest_closest_tool_name(requested, valid_sorted)

    head = f"未対応のツールです: {requested}"
    if suggestion:
        head += f"。もしかして '{suggestion}' ですか?"
    else:
        head += "。"
    tail = f" 現在使える tool: [{', '.join(valid_sorted)}]"
    return head + tail
