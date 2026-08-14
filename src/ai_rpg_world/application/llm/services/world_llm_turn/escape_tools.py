"""脱出ランタイム向け tool 露出フィルタと handler 整合性検証。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION

class ToolHandlerConsistencyError(RuntimeError):
    """tool spec が expose する tool 名集合と、_tool_handlers の dispatch SSOT
    キー集合の間に欠落があるときに投げられる。

    過去 PR #589 / #590 で「LLM に tool spec を見せているのに dispatch 側に
    handler が無く UNSUPPORTED_TOOL に化ける」silent failure が発生したため、
    本例外で起動時に fail-fast させる。"""


# PR-A (Issue #621 後続): 脱出ランタイムでは恒久的に未対応な tool。
# ``_handle_set_sub_location`` が常に ``UNSUPPORTED_TOOL`` を返すため LLM に
# 見せる意味が無い。Y_after_issue621 trace で実際に 3 回叩かれて全部失敗した
# ので、tools_payload の構築時にここで定義された名前を弾く。handler 自体は
# 防御として残し、何らかの経路で呼ばれても安全に UNSUPPORTED_TOOL を返す。
#
# 別ランタイム (= 通常 SpotGraph) で set_sub_location が必要になった場合は
# このフィルタを呼ばないことで通せる (= ToolDefinitionDto 側に変更不要)。
ESCAPE_RUNTIME_LLM_EXCLUDED_TOOLS: frozenset[str] = frozenset({
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
})


def filter_definitions_for_escape_llm(definitions):
    """``ESCAPE_RUNTIME_LLM_EXCLUDED_TOOLS`` に含まれる tool definition を除外する。

    入力順を保ったまま、name 属性が除外対象に該当するものだけを取り除く。
    """
    return [d for d in definitions if d.name not in ESCAPE_RUNTIME_LLM_EXCLUDED_TOOLS]


def tool_names_from_payload(tools_payload: Iterable[Any]) -> frozenset[str]:
    """実際に送った OpenAI tools payload から関数名だけを取り出す。"""
    names: set[str] = set()
    for tool in tools_payload:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if isinstance(name, str) and name:
            names.add(name)
    return frozenset(names)


def validate_tool_handler_consistency(
    exposed_tool_names: Iterable[str],
    handler_keys: Iterable[str],
) -> None:
    """tool spec の集合が dispatch handler の集合に含まれていることを保証する。

    spec に出ているのに handler が無い tool を見つけたら
    ``ToolHandlerConsistencyError`` を投げる。handler だけ存在し spec に居ない
    ケース (= feature flag OFF や aux executor 常駐) は許容する。
    """
    exposed = set(exposed_tool_names)
    registered = set(handler_keys)
    missing = exposed - registered
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ToolHandlerConsistencyError(
            "Tool spec exposes tools without dispatch handlers: "
            f"[{missing_list}]. "
            "_tool_handlers (= dispatch SSOT) にエントリを追加してください。"
        )
