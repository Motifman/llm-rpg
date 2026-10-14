"""Memo 系およびエピソード記憶メタツールの定義。

Issue #188 Phase 1a で TODO → memo にリネーム。LLM が context に固定したい
任意のテキスト (タスク / 目標 / 戦略メモ / 注意事項 / 観察など) を memo
として扱えるように tool description も刷新。

ツール名:
- 新: memo_add / memo_list / memo_done
- 旧: todo_add / todo_list / todo_complete は alias として残す (後方互換)
"""


from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.contracts.tool_category import ToolCategory
from ai_rpg_world.application.llm.services.availability_resolvers import (
    EpisodeRecallAvailabilityResolver,
    TodoAddAvailabilityResolver,
    TodoCompleteAvailabilityResolver,
    TodoListAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_EPISODE_RECALL,
    TOOL_NAME_EPISODE_REVISE_INDEX,
    TOOL_NAME_MEMO_ADD,
    TOOL_NAME_MEMO_DONE,
    TOOL_NAME_MEMO_LIST,
)
from ai_rpg_world.being.domain.episode import INDEX_TEXT_MAX_LENGTH

MEMO_ADD_DESCRIPTION = (
    "ターンを跨いで覚えておきたい情報 (目標 / 戦略 / 観察 / 約束など) を memo として記録します。"
    "書いた memo は memo_done で閉じるまで毎ターン表示されます。"
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
    "指定 ID 群の memo を完了として記録します。達成・撤回・無効化どれでも、もう参照"
    "不要になった memo は閉じてください。同じ目的を構成する複数 memo を一括で閉じる"
    "と context が軽くなります。"
    "\n\n"
    "**memo_done はメモを片付ける操作であり、目標達成にも世界の変化にも繋がりません**。"
    "目標達成には物理ツール (travel_to / interact / pickup_item / speech / "
    "use_item 等) を呼んでください。想起しただけで反射的に閉じないこと。"
    "\n\n"
    "memo_id は表示handle (例: 'memo_a3b9f1…')、裸の短縮形、full UUIDのいずれも可。"
    "短縮形が複数の memo に"
    "一致すると曖昧エラーになるので、その時だけより長い prefix を指定してください。"
    "1 件でも memo_ids=['<id>'] のように配列で渡す。存在しない ID は個別に not_found"
    "として報告され、残りは正常完了 (部分成功)。"
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


def episode_recall_definition(max_handles: int) -> ToolDefinitionDto:
    """上限 M は profile の値なので、定義もそこから作る (#1623)。"""
    return ToolDefinitionDto(
        name=TOOL_NAME_EPISODE_RECALL,
        description=(
            "【思い出せる出来事】に並ぶ自分の昔の出来事を、呼び名を指定して詳しく思い出す。"
            "目次の「思い出すとき」に今の場面が当てはまるとき、昔のことを人に話す前、"
            "似た場面で前にどうしたかを確かめたいときに使う。"
            f"1 回に {max_handles} 件まで、まとめて思い出せる。"
            "目次に無い呼び名は思い出せない。思い出すだけで、世界の出来事は起こさない。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "handles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": max_handles,
                    "description": (
                        "【思い出せる出来事】の行の先頭にある ep_ で始まる呼び名。"
                        '1 件でも配列で渡す (例: ["ep_3f2a7b"])。'
                    ),
                },
            },
            "required": ["handles"],
        },
        category=ToolCategory.META_COGNITIVE,
    )


EPISODE_REVISE_INDEX_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_EPISODE_REVISE_INDEX,
    description=(
        "【思い出せる出来事】の目次の一行 (どんな記憶か・どんな時に思い出すか) を書き直す。"
        "呼び出した本文が目次の書き方と合っていなかったとき、"
        "思い出すべき場面が目次に書いた場面と違ったときに使う。"
        "本文は変わらず、前の目次も消えずに残る。直すのに手番を 1 回使う。"
        f"about と recall_when はそれぞれ {INDEX_TEXT_MAX_LENGTH} 字まで。"
        "世界の出来事は起こさない。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "handle": {
                "type": "string",
                "description": "直したい記憶の、【思い出せる出来事】の行の先頭にある ep_ で始まる呼び名。",
            },
            "about": {
                "type": "string",
                "description": "どんな記憶か。",
            },
            "recall_when": {
                "type": "string",
                "description": "どんな時に思い出すとよいか。「金庫や鍵の話が出たとき」のように場面で書く。",
            },
        },
        "required": ["handle", "about", "recall_when"],
    },
    category=ToolCategory.META_COGNITIVE,
)


def get_memo_specs() -> list[tuple[ToolDefinitionDto, IAvailabilityResolver]]:
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
    memo_enabled: bool | None = None,
    episode_recall_max_handles: int | None = None,
    episode_index_revision_enabled: bool = False,
) -> list[tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """memo と、任意で目次つきのエピソードの道具を返す。

    ``todo_enabled`` は後方互換のための旧名引数。``memo_enabled`` を渡せば
    そちらが優先される。両方未指定は False (= memo を expose しない)。

    ``episode_recall_max_handles`` を渡すと、目次つきのエピソードの呼び出し
    ``episode_recall`` をその上限で出す (#1623)。None なら出さない。
    ``episode_index_revision_enabled`` は、その目次を直す ``episode_revise_index``。
    """
    if memo_enabled is None:
        memo_enabled = todo_enabled
    specs: list[tuple[ToolDefinitionDto, IAvailabilityResolver]] = []
    if memo_enabled:
        specs.extend(get_memo_specs())
    if episode_recall_max_handles is not None:
        specs.append(
            (
                episode_recall_definition(episode_recall_max_handles),
                EpisodeRecallAvailabilityResolver(),
            )
        )
    if episode_index_revision_enabled:
        specs.append((EPISODE_REVISE_INDEX_DEFINITION, EpisodeRecallAvailabilityResolver()))
    return specs


__all__ = [
    "MEMO_ADD_DEFINITION",
    "MEMO_LIST_DEFINITION",
    "MEMO_DONE_DEFINITION",
    # backward-compat
    "TODO_ADD_DEFINITION",
    "TODO_LIST_DEFINITION",
    "TODO_COMPLETE_DEFINITION",
    "EPISODE_REVISE_INDEX_DEFINITION",
    "episode_recall_definition",
    "get_memo_specs",
    "get_memory_specs",
    "get_todo_specs",
]
