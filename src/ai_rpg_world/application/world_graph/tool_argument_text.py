"""tool にそのまま渡せる文字列のプロンプト表記を揃える。"""

from __future__ import annotations

import json


def quote_tool_argument(value: str) -> str:
    """文字列引数を、JSON と同じ引用符・エスケープ規則で表示する。"""
    return json.dumps(str(value), ensure_ascii=False)
