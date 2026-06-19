"""ツール引数の安定した文字列化（連続失敗検知用）。"""

from __future__ import annotations

import json
from typing import Any, Dict, FrozenSet, Optional


# Issue #264 第16回実験で「loop_guard が wait spam を検知できない」原因を分析した結果、
# tool 引数に LLM の主観 narrative (inner_thought / reason 等) が含まれ、毎ターン
# 内容が変わるため fingerprint が常に異なってしまっていた。
#
# 「同じ tool を同じ outcome-affecting 引数で連打しているか」という判定には
# narrative は無関係なので、fingerprint からは除外する。
#
# このセットに含まれる field は LLM が「自分の心情・推論を記述する」フィールドで、
# 外界に対する効果 (どの object に / どの場所へ / どんな action を) には寄与しない。
NARRATIVE_ARG_FIELDS: FrozenSet[str] = frozenset({
    "inner_thought",      # 全 world-action tool 共通の subjective narrative
    "reason",             # spot_graph_wait など
    "intention",          # world-action tool の主観入力 (目的)
    "expected_result",    # world-action tool の主観入力 (行動前の予測)
    "emotion_hint",       # world-action tool の主観入力 (主要感情)
})


def build_argument_fingerprint(
    arguments: Optional[Dict[str, Any]],
    *,
    strip_narrative: bool = True,
) -> str:
    """
    同一引数か判定するためのフィンガープリント。

    Args:
        arguments: ツール引数 dict。None は空 dict 相当。
        strip_narrative: True (default) なら ``NARRATIVE_ARG_FIELDS`` に含まれる
            キーを除外してから JSON 化する。False なら全 key を含める
            (旧挙動、デバッグ・監査用)。

    キーはソートして JSON 化するため、引数順序は無視される。
    """
    if arguments is None:
        args: Dict[str, Any] = {}
    else:
        args = arguments
    if not isinstance(args, dict):
        return json.dumps(str(args), ensure_ascii=False)
    if strip_narrative:
        args = {k: v for k, v in args.items() if k not in NARRATIVE_ARG_FIELDS}
    return json.dumps(args, ensure_ascii=False, sort_keys=True)
