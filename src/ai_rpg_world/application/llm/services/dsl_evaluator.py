"""メモリ変数用 DSL 評価器

eval/exec は使用しない。ast.parse でパースし、許容ノードのみ安全に評価する。
対応: take, drop, where, sort_by, select
補助関数: has_any, has_all, contains, eq, ge, le
"""

import ast
from typing import Any, Callable, Dict, List, Union

from ai_rpg_world.application.llm.exceptions import (
    DslEvaluationException,
    DslParseException,
)

_ALLOWED_METHODS = frozenset(
    {"take", "drop", "where", "sort_by", "select"}
)
_ALLOWED_PREDICATES = frozenset({"has_any", "has_all", "contains", "eq", "ge", "le"})


def eval_expr(expr: str, data: List[Dict[str, Any]]) -> Union[List[Dict[str, Any]], str]:
    """
    DSL 式を評価し、データを絞り込み・整形した結果を返す。

    Args:
        expr: DSL 式。例: "episodic.take(10)", "episodic.where(has_any(...)).take(20)"
        data: 変数解決済みのデータ（dict のリスト）

    Returns:
        評価結果。List[Dict]。
    """
    if not isinstance(expr, str):
        raise DslParseException("expr must be str", expr=str(expr))
    if not isinstance(data, list):
        raise DslEvaluationException("data must be list", expr=expr)
    expr = expr.strip()
    if not expr:
        raise DslParseException("expr must not be empty", expr=expr)

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise DslParseException(f"DSL parse error: {e}", expr=expr)

    result = _eval_node(tree.body, data)
    if isinstance(result, list):
        return result
    raise DslEvaluationException(
        f"DSL must return list, got {type(result).__name__}", expr=expr
    )


def _eval_node(
    node: ast.AST, data: List[Dict[str, Any]]
) -> Union[List[Dict[str, Any]], str]:
    if isinstance(node, ast.Name):
        return data
    if isinstance(node, ast.Call):
        return _eval_call(node, data)
    raise DslParseException(
        f"Unsupported AST node: {type(node).__name__}", expr=ast.dump(node)
    )


def _eval_call(
    node: ast.Call, data: List[Dict[str, Any]]
) -> Union[List[Dict[str, Any]], str]:
    func = node.func
    if not isinstance(func, ast.Attribute):
        raise DslParseException(
            "Expected chain like var.method(...)", expr=ast.dump(node)
        )
    method_name = func.attr
    if method_name not in _ALLOWED_METHODS:
        raise DslParseException(
            f"Unsupported method: {method_name!r}. "
            f"Allowed: {', '.join(sorted(_ALLOWED_METHODS))}",
            expr=ast.dump(node),
        )

    # Evaluate the left-hand side (value)
    if isinstance(func.value, ast.Name):
        left_data = data
    elif isinstance(func.value, ast.Call):
        left_result = _eval_call(func.value, data)
        if not isinstance(left_result, list):
            raise DslEvaluationException(
                f"Intermediate result must be list before .{method_name}",
                expr=ast.dump(node),
            )
        left_data = left_result
    else:
        raise DslParseException(
            f"Unsupported chain structure: {type(func.value).__name__}",
            expr=ast.dump(node),
        )

    return _apply_method(method_name, node.args, left_data)


def _apply_method(
    method_name: str,
    args: List[ast.AST],
    data: List[Dict[str, Any]],
) -> Union[List[Dict[str, Any]], str]:
    if method_name == "take":
        return _apply_take(args, data)
    if method_name == "drop":
        return _apply_drop(args, data)
    if method_name == "where":
        return _apply_where(args, data)
    if method_name == "sort_by":
        return _apply_sort_by(args, data)
    if method_name == "select":
        return _apply_select(args, data)
    raise DslParseException(
        f"Method {method_name!r} not yet implemented", expr=method_name
    )


def _eval_arg_to_python(arg: ast.AST) -> Any:
    """AST 引数を Python 値に変換する（定数・リスト・UnaryOp のみ許可）。"""
    if isinstance(arg, ast.Constant):
        return arg.value
    if isinstance(arg, ast.List):
        return [_eval_arg_to_python(el) for el in arg.elts]
    if isinstance(arg, ast.Tuple):
        return tuple(_eval_arg_to_python(el) for el in arg.elts)
    if isinstance(arg, ast.UnaryOp):
        if isinstance(arg.op, ast.USub):
            val = _eval_arg_to_python(arg.operand)
            if isinstance(val, (int, float)):
                return -val
        raise DslParseException(
            f"Unsupported unary op: {type(arg.op).__name__}", expr=ast.dump(arg)
        )
    if isinstance(arg, ast.Call):
        return _eval_predicate_call(arg)
    raise DslParseException(
        f"Unsupported argument type: {type(arg).__name__}", expr=ast.dump(arg)
    )


def _eval_predicate_call(node: ast.Call) -> Callable[[Dict[str, Any]], bool]:
    """述語 Call (has_any, contains, eq 等) を評価し、 predicate 関数を返す。"""
    func = node.func
    if isinstance(func, ast.Name):
        pred_name = func.id
    else:
        raise DslParseException(
            "Predicate must be function call: has_any, contains, eq, etc.",
            expr=ast.dump(node),
        )
    if pred_name not in _ALLOWED_PREDICATES:
        raise DslParseException(
            f"Unsupported predicate: {pred_name!r}. "
            f"Allowed: {', '.join(sorted(_ALLOWED_PREDICATES))}",
            expr=ast.dump(node),
        )

    args_py = [_eval_arg_to_python(a) for a in node.args]
    if pred_name == "has_any":
        if len(args_py) != 2:
            raise DslEvaluationException(
                "has_any(field, values) requires 2 arguments", expr=ast.dump(node)
            )
        field, values = args_py[0], args_py[1]
        if not isinstance(field, str):
            raise DslEvaluationException("has_any field must be str", expr=ast.dump(node))
        vals_set = set(values) if isinstance(values, (list, tuple)) else {values}

        def pred(item: Dict[str, Any]) -> bool:
            val = item.get(field)
            if val is None:
                return False
            if isinstance(val, (list, tuple)):
                return bool(set(val) & vals_set)
            return val in vals_set

        return pred
    if pred_name == "has_all":
        if len(args_py) != 2:
            raise DslEvaluationException(
                "has_all(field, values) requires 2 arguments", expr=ast.dump(node)
            )
        field, values = args_py[0], args_py[1]
        if not isinstance(field, str):
            raise DslEvaluationException("has_all field must be str", expr=ast.dump(node))
        vals_set = set(values) if isinstance(values, (list, tuple)) else {values}

        def pred(item: Dict[str, Any]) -> bool:
            val = item.get(field)
            if val is None:
                return False
            if isinstance(val, (list, tuple)):
                return vals_set <= set(val)
            return val in vals_set

        return pred
    if pred_name == "contains":
        if len(args_py) != 2:
            raise DslEvaluationException(
                "contains(field, text) requires 2 arguments", expr=ast.dump(node)
            )
        field, text = args_py[0], args_py[1]
        if not isinstance(field, str):
            raise DslEvaluationException("contains field must be str", expr=ast.dump(node))
        text_str = str(text) if text is not None else ""

        def pred(item: Dict[str, Any]) -> bool:
            val = item.get(field)
            if val is None:
                return False
            return text_str in str(val)

        return pred
    if pred_name == "eq":
        if len(args_py) != 2:
            raise DslEvaluationException(
                "eq(field, value) requires 2 arguments", expr=ast.dump(node)
            )
        field, target = args_py[0], args_py[1]
        if not isinstance(field, str):
            raise DslEvaluationException("eq field must be str", expr=ast.dump(node))

        def pred(item: Dict[str, Any]) -> bool:
            return item.get(field) == target

        return pred
    if pred_name == "ge":
        if len(args_py) != 2:
            raise DslEvaluationException(
                "ge(field, value) requires 2 arguments", expr=ast.dump(node)
            )
        field, target = args_py[0], args_py[1]

        def pred(item: Dict[str, Any]) -> bool:
            val = item.get(field)
            if val is None:
                return False
            try:
                return val >= target
            except TypeError:
                return False

        return pred
    if pred_name == "le":
        if len(args_py) != 2:
            raise DslEvaluationException(
                "le(field, value) requires 2 arguments", expr=ast.dump(node)
            )
        field, target = args_py[0], args_py[1]

        def pred(item: Dict[str, Any]) -> bool:
            val = item.get(field)
            if val is None:
                return False
            try:
                return val <= target
            except TypeError:
                return False

        return pred

    raise DslParseException(f"Unknown predicate: {pred_name}", expr=ast.dump(node))


def _apply_take(args: List[ast.AST], data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(args) != 1:
        raise DslEvaluationException("take(n) requires exactly 1 argument", expr="take")
    n = _eval_arg_to_python(args[0])
    if not isinstance(n, int):
        raise DslEvaluationException("take(n) requires n to be int", expr=str(n))
    if n < 0:
        raise DslEvaluationException("take(n) requires n >= 0", expr=str(n))
    return data[:n]


def _apply_drop(args: List[ast.AST], data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(args) != 1:
        raise DslEvaluationException("drop(n) requires exactly 1 argument", expr="drop")
    n = _eval_arg_to_python(args[0])
    if not isinstance(n, int):
        raise DslEvaluationException("drop(n) requires n to be int", expr=str(n))
    if n < 0:
        raise DslEvaluationException("drop(n) requires n >= 0", expr=str(n))
    return data[n:]


def _apply_where(args: List[ast.AST], data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(args) != 1:
        raise DslEvaluationException(
            "where(predicate) requires exactly 1 argument", expr="where"
        )
    pred = _eval_arg_to_python(args[0])
    if not callable(pred):
        raise DslEvaluationException(
            "where() argument must be predicate (has_any, contains, eq, etc.)",
            expr=ast.dump(args[0]),
        )
    return [item for item in data if pred(item)]


def _apply_sort_by(
    args: List[ast.AST], data: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    if len(args) != 1:
        raise DslEvaluationException(
            "sort_by(field) requires exactly 1 argument", expr="sort_by"
        )
    field = _eval_arg_to_python(args[0])
    if not isinstance(field, str):
        raise DslEvaluationException(
            "sort_by(field) requires field to be str", expr=str(field)
        )
    descending = field.startswith("-")
    key_field = field[1:].strip() if descending else field
    if not key_field:
        raise DslEvaluationException(
            "sort_by(field) requires non-empty field", expr=field
        )

    def key_fn(item: Dict[str, Any]) -> Any:
        val = item.get(key_field)
        return (val is None, val)

    result = sorted(data, key=key_fn)
    if descending:
        result.reverse()
    return result


def _apply_select(
    args: List[ast.AST], data: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    if not args:
        raise DslEvaluationException(
            "select(field1, field2, ...) requires at least 1 argument", expr="select"
        )
    fields = []
    for a in args:
        f = _eval_arg_to_python(a)
        if isinstance(f, str):
            fields.append(f)
        elif isinstance(f, (list, tuple)):
            fields.extend(str(x) for x in f)
        else:
            fields.append(str(f))
    if not fields:
        raise DslEvaluationException(
            "select() requires at least one field name", expr="select"
        )

    result = []
    for item in data:
        if isinstance(item, dict):
            result.append({k: item[k] for k in fields if k in item})
        else:
            result.append(item)
    return result
