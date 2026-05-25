"""Memo 系およびエピソード記憶メタツールの定義。

Issue #188 Phase 1a で TODO → memo にリネーム。LLM が context に固定したい
任意のテキスト (タスク / 目標 / 戦略メモ / 注意事項 / 観察など) を memo
として扱えるように tool description も刷新。

ツール名:
- 新: memo_add / memo_list / memo_done
- 旧: todo_add / todo_list / todo_complete は alias として残す (後方互換)
"""

from typing import List, Optional, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.contracts.tool_category import ToolCategory
from ai_rpg_world.application.llm.services.availability_resolvers import (
    MemoryExploreRelatedAvailabilityResolver,
    TodoAddAvailabilityResolver,
    TodoCompleteAvailabilityResolver,
    TodoListAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMO_ADD,
    TOOL_NAME_MEMO_DONE,
    TOOL_NAME_MEMO_LIST,
    TOOL_NAME_MEMORY_EXPLORE_RELATED,
)


MEMO_ADD_DESCRIPTION = (
    "context に固定したい情報を memo として pin します。"
    "LLM が自分の判断で「ターンを跨いで覚えておきたい」と思う任意のテキストを書き込めます。"
    "\n\n"
    "書いてよい内容の例:\n"
    "- 当面の目標 (例: 「金庫室で扉固定スイッチを押す」)\n"
    "- 戦略メモ (例: 「カイトは慎重派なので合図を待つ」)\n"
    "- 注意事項 (例: 「制御室を離れると電源が切れる仕組み」)\n"
    "- 重要な観察 (例: 「リンは tick=8 に latch を押した」)\n"
    "- 過去の決定 / 約束 (例: 「我々の作戦は二段階突入で合意した」)\n"
    "\n"
    "書き込んだ memo は完了 (memo_done) するまで毎ターンプロンプトに表示されます。"
    "達成・撤回どちらでも、もう参照する必要がないと判断したら memo_done で完了させてください。"
    "**完了タイミングを逃すと達成根拠が context から消えて後で振り返れなくなるため、"
    "達成したと思った時点で速やかに完了させること。**"
)

MEMO_ADD_PARAMETERS = {
    "type": "object",
    "properties": {
        "content": {
            "type": "string",
            "description": "memo の内容。自由なテキスト (目標 / 戦略 / 注意 / 観察 / 約束など)。",
        },
    },
    "required": ["content"],
}
MEMO_ADD_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_MEMO_ADD,
    description=MEMO_ADD_DESCRIPTION,
    parameters=MEMO_ADD_PARAMETERS,
    category=ToolCategory.AUXILIARY,
)


MEMO_LIST_DESCRIPTION = (
    "アクティブな (未完了の) memo 一覧を返します。"
    "memo は常時プロンプトの「進行中のメモ」セクションにも表示されますが、"
    "明示的に確認したい時に使えます。"
)
MEMO_LIST_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_MEMO_LIST,
    description=MEMO_LIST_DESCRIPTION,
    parameters={"type": "object", "properties": {}, "required": []},
    category=ToolCategory.AUXILIARY,
)


MEMO_DONE_DESCRIPTION = (
    "指定 ID 群の memo をまとめて完了として記録します。"
    "達成・撤回・無効化どれでも、もう参照する必要がない memo は速やかに完了させてください。"
    "**同じ目的を構成する複数の memo を一気に閉じると context が軽くなります。** "
    "1 件だけ完了する場合も memo_ids=['<id>'] のように単一要素配列で渡してください。"
    "\n\n"
    "完了時点で直近の観測 / 行動結果が memo ごとに自動 snapshot され、"
    "後で類似状況に直面したときに過去経験として recall される可能性があります。"
    "**達成根拠が context に残っているうちに完了させると snapshot の質が上がります。**"
    "\n\n"
    "存在しない memo_id は個別に not_found として報告され、残りは正常に完了します (部分成功)。"
)
MEMO_DONE_PARAMETERS = {
    "type": "object",
    "properties": {
        "memo_ids": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 10,
            "description": (
                "完了する memo の ID 配列。1 件でも配列で渡す (例: ['abc'])。"
                "同じ目的を構成する複数の memo を一括完了する場合は複数 ID を含める。"
            ),
        },
    },
    "required": ["memo_ids"],
}
MEMO_DONE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_MEMO_DONE,
    description=MEMO_DONE_DESCRIPTION,
    parameters=MEMO_DONE_PARAMETERS,
    category=ToolCategory.AUXILIARY,
)


# 後方互換: 旧 TODO 名の DEFINITION エイリアス
TODO_ADD_DEFINITION = MEMO_ADD_DEFINITION
TODO_LIST_DEFINITION = MEMO_LIST_DEFINITION
TODO_COMPLETE_DEFINITION = MEMO_DONE_DEFINITION


MEMORY_EXPLORE_RELATED_PARAMETERS = {
    "type": "object",
    "properties": {
        "episode_id": {
            "type": "string",
            "description": "起点となる主観エピソード ID",
        },
        "top_k": {
            "type": "integer",
            "description": "返す隣接エピソードの最大件数（既定 5、最大 64）",
        },
    },
    "required": ["episode_id"],
}

MEMORY_EXPLORE_RELATED_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_MEMORY_EXPLORE_RELATED,
    description=(
        "リンクされた関連エピソード記憶を列挙します。"
        "結果はプロンプト文脈向けの JSON であり、世界状態は変えません。"
    ),
    parameters=MEMORY_EXPLORE_RELATED_PARAMETERS,
    category=ToolCategory.META_COGNITIVE,
)


def get_memo_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """memo 系ツールの (definition, resolver) 一覧を返す。"""
    return [
        (MEMO_ADD_DEFINITION, TodoAddAvailabilityResolver()),
        (MEMO_LIST_DEFINITION, TodoListAvailabilityResolver()),
        (MEMO_DONE_DEFINITION, TodoCompleteAvailabilityResolver()),
    ]


# 後方互換: 旧名 ``get_todo_specs`` は ``get_memo_specs`` のエイリアス。
get_todo_specs = get_memo_specs


def get_memory_specs(
    *,
    todo_enabled: bool = False,
    episodic_explore_related_enabled: bool = False,
    memo_enabled: Optional[bool] = None,
) -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """memo および任意で memory_explore_related を返す。

    ``todo_enabled`` は後方互換のための旧名引数。``memo_enabled`` を渡せば
    そちらが優先される。両方未指定は False (= memo を expose しない)。
    """
    if memo_enabled is None:
        memo_enabled = todo_enabled
    specs: List[Tuple[ToolDefinitionDto, IAvailabilityResolver]] = []
    if memo_enabled:
        specs.extend(get_memo_specs())
    if episodic_explore_related_enabled:
        specs.append(
            (MEMORY_EXPLORE_RELATED_DEFINITION, MemoryExploreRelatedAvailabilityResolver())
        )
    return specs


__all__ = [
    "MEMO_ADD_DEFINITION",
    "MEMO_LIST_DEFINITION",
    "MEMO_DONE_DEFINITION",
    "MEMORY_EXPLORE_RELATED_DEFINITION",
    # backward-compat
    "TODO_ADD_DEFINITION",
    "TODO_LIST_DEFINITION",
    "TODO_COMPLETE_DEFINITION",
    "get_memo_specs",
    "get_memory_specs",
    "get_todo_specs",
]
