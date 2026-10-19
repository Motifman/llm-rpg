"""ツール引数の安定した文字列化（連続失敗検知用）。"""

from __future__ import annotations

import json
from typing import Any

from ai_rpg_world.application.llm.contracts.action_argument_classification import (
    ACTION_ARGUMENT_CLASSIFICATIONS,
    ActionArgumentDisplayKind,
)
from ai_rpg_world.application.llm.services.action_summary_format import (
    ACTION_HISTORY_PROJECTION_KEY,
)

# Issue #264 第16回実験で「loop_guard が wait spam を検知できない」原因を分析した結果、
# tool 引数に LLM の主観 narrative (inner_thought / reason 等) が含まれ、毎ターン
# 内容が変わるため fingerprint が常に異なってしまっていた。
#
# 「同じ tool を同じ outcome-affecting 引数で連打しているか」という判定には
# narrative は無関係なので、fingerprint からは除外する。
#
# このセットに含まれる field は LLM が「自分の心情・推論を記述する」フィールドで、
# 外界に対する効果 (どの object に / どの場所へ / どんな action を) には寄与しない。
NARRATIVE_ARG_FIELDS: frozenset[str] = frozenset({
    "inner_thought",      # 全 world-action tool 共通の subjective narrative
    "reason",             # spot_graph_wait など
    "intention",          # world-action tool の主観入力 (目的)
    "memo",               # 環境の tool に添えるメモ帳への書き込み (#1628)
    "emotion_hint",       # world-action tool の主観入力 (主要感情)
})

# 行動に添える発言。周りに届くので主観ではないが、同じ操作を言葉を変えて試すと
# 毎回違う値になり、繰り返しが数えられなくなる (#1594)。speak の content は
# 発言そのものが行動なので、ここには入れない。
ACCOMPANYING_SPEECH_FIELDS: frozenset[str] = frozenset({"say_inline"})


def _symmetric_quotes_stripped(value: str) -> str:
    s = value.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1].strip() or s
    return value


def _with_resolved_identifiers(args: dict[str, Any]) -> dict[str, Any]:
    """識別値を実行側が解決した形にそろえ、運搬用の内部キーを外す。

    dispatch は解決済みの識別値を ``ACTION_HISTORY_PROJECTION_KEY`` に載せて引数へ
    足す。解決済みの値を報告しない resolver では生値のまま載るので、どちらの
    値からも両端の引用符を剥がす。
    自由文は引用符も中身のうちなので触らない。
    """
    projection = args.get(ACTION_HISTORY_PROJECTION_KEY)
    resolved: dict[str, Any] = {}
    if isinstance(projection, (tuple, list)) and projection and isinstance(projection[0], dict):
        resolved = projection[0]
    out: dict[str, Any] = {}
    for key, value in args.items():
        if key == ACTION_HISTORY_PROJECTION_KEY:
            continue
        is_identifier = (
            ACTION_ARGUMENT_CLASSIFICATIONS.get(key) is ActionArgumentDisplayKind.IDENTIFIER_STRING
        )
        if is_identifier and isinstance(value, str):
            canonical = resolved.get(key)
            value = _symmetric_quotes_stripped(canonical if isinstance(canonical, str) else value)
        out[key] = value
    return out


def build_argument_fingerprint(
    arguments: dict[str, Any] | None,
    *,
    strip_narrative: bool = True,
) -> str:
    """
    同一引数か判定するためのフィンガープリント。

    Args:
        arguments: ツール引数 dict。None は空 dict 相当。
        strip_narrative: True (default) なら ``NARRATIVE_ARG_FIELDS`` と
            ``ACCOMPANYING_SPEECH_FIELDS`` のキーを除外し、識別値を解決済みの
            形にそろえてから JSON 化する。False なら全 key をそのまま含める
            (旧挙動、デバッグ・監査用)。

    キーはソートして JSON 化するため、引数順序は無視される。
    """
    if arguments is None:
        args: dict[str, Any] = {}
    else:
        args = arguments
    if not isinstance(args, dict):
        return json.dumps(str(args), ensure_ascii=False)
    if strip_narrative:
        args = {
            k: v
            for k, v in _with_resolved_identifiers(args).items()
            if k not in NARRATIVE_ARG_FIELDS and k not in ACCOMPANYING_SPEECH_FIELDS
        }
    return json.dumps(args, ensure_ascii=False, sort_keys=True)
