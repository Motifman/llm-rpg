"""ツール引数の安定した文字列化（連続失敗検知用）。"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


def build_argument_fingerprint(arguments: Optional[Dict[str, Any]]) -> str:
    """
    同一引数か判定するためのフィンガープリント。

    None は空 dict 相当。キーはソートして JSON 化する。
    """
    if arguments is None:
        args: Dict[str, Any] = {}
    else:
        args = arguments
    if not isinstance(args, dict):
        return json.dumps(str(args), ensure_ascii=False)
    return json.dumps(args, ensure_ascii=False, sort_keys=True)
