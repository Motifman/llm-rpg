"""無いツール名から、出したツールのうち近い名前を 1 つ選ぶ。"""

from __future__ import annotations

from collections.abc import Iterable
from difflib import SequenceMatcher

# 0.5 は speech_speech → speech_speak の末尾の類似度 0.545 を通し、harvest → travel_to の 0.5 を落とす境目。
_SUFFIX_RATIO_CUTOFF = 0.5
_SHORTENED_NAME_SCORE = 0.95
# 廃止した spot_graph_ を付けて呼ぶ癖が残るので、外した名前でも比べる。
_LEGACY_TOOL_PREFIXES: tuple[str, ...] = ("spot_graph_",)


def suggest_closest_tool_name(requested: str, valid_tools: Iterable[str]) -> str | None:
    """先頭の語が 1 つも共通しない名前 (gather、harvest) は救わない。"""
    if not isinstance(requested, str) or not requested:
        return None
    valid_list = [v for v in valid_tools if isinstance(v, str) and v]
    if not valid_list:
        return None
    variants = [requested]
    for legacy in _LEGACY_TOOL_PREFIXES:
        if requested.startswith(legacy) and len(requested) > len(legacy):
            variants.append(requested[len(legacy) :])
            break
    best: str | None = None
    best_score = 0.0
    for variant in variants:
        variant_best, variant_score = _closest(variant, valid_list)
        if variant_score > best_score:
            best, best_score = variant_best, variant_score
    return best if best_score > _SUFFIX_RATIO_CUTOFF else None


def _closest(requested: str, valid_list: list[str]) -> tuple[str | None, float]:
    req_parts = requested.split("_")
    best: str | None = None
    best_score = 0.0
    for candidate in valid_list:
        cand_parts = candidate.split("_")
        common = 0
        for r, c in zip(req_parts, cand_parts):
            if r != c:
                break
            common += 1
        if common == 0:
            continue
        req_suffix = "_".join(req_parts[common:])
        cand_suffix = "_".join(cand_parts[common:])
        if not req_suffix and cand_suffix:
            score = _SHORTENED_NAME_SCORE
        elif not cand_suffix and req_suffix:
            # 候補のほうが短いときは、末尾を付けた名前を呼びたかったと推すには弱い。
            score = 0.0
        elif not req_suffix and not cand_suffix:
            score = 1.0
        else:
            score = SequenceMatcher(None, req_suffix, cand_suffix).ratio()
        if score > best_score:
            best, best_score = candidate, score
    return best, best_score


__all__ = ["suggest_closest_tool_name"]
