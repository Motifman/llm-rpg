"""メモリ変数用 DSL 評価器（最小版）

eval/exec は使用しない。許容トークンのみパースして安全に評価する。
初期対応: var.take(n) のみ。
"""

import re
from typing import Any, Dict, List

from ai_rpg_world.application.llm.exceptions import (
    DslEvaluationException,
    DslParseException,
)


def eval_expr(expr: str, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    DSL 式を評価し、データを絞り込んだ結果を返す。

    Args:
        expr: DSL 式。例: "episodic.take(10)", "facts.take(5)"
              変数名は呼び出し側で解決済み。この関数は data に対して操作を適用する。
        data: 変数解決済みのデータ（dict のリスト）

    Returns:
        評価結果（dict のリスト）

    Raises:
        DslParseException: パースに失敗した場合
        DslEvaluationException: 評価に失敗した場合
    """
    if not isinstance(expr, str):
        raise DslParseException(
            "expr must be str",
            expr=str(expr),
        )
    if not isinstance(data, list):
        raise DslEvaluationException(
            "data must be list",
            expr=expr,
        )
    expr = expr.strip()
    if not expr:
        raise DslParseException(
            "expr must not be empty",
            expr=expr,
        )

    # 初期対応: var.take(n) 形式のみ
    # 正規表現: 識別子.take(整数)
    match = re.match(
        r"^([a-zA-Z_][a-zA-Z0-9_]*)\.take\s*\(\s*(\d+)\s*\)\s*$",
        expr,
    )
    if not match:
        raise DslParseException(
            "Unsupported DSL form. Use var.take(n), e.g. episodic.take(10)",
            expr=expr,
        )

    var_name = match.group(1)
    n_str = match.group(2)
    n = int(n_str)
    if n < 0:
        raise DslEvaluationException(
            "take(n) requires n >= 0",
            expr=expr,
        )

    return data[:n]
