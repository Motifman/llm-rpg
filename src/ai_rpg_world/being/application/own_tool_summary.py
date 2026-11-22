"""Being 自身が受け持つ 1 手 (思い出すツール、出していないツールの名前) の、【直近の出来事】に出す行動の要約。"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping


def own_tool_summary(tool_name: str, arguments: Mapping[str, object], *, hidden: Collection[str | None]) -> str:
    """古い run の、表に無いツールの要約と同じ文にする。``hidden`` の引数 (独白・メモ) は別の行や欄に出るので出さない。"""
    visible = {name: value for name, value in arguments.items() if name not in hidden}
    if not visible:
        return f"{tool_name} を実行しました。"
    return f"{tool_name}({json.dumps(visible, ensure_ascii=False)}) を実行しました。"
