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
    MemoryRecallByHandleAvailabilityResolver,
    MemoryRecallEpisodesAvailabilityResolver,
    MemorySearchSemanticAvailabilityResolver,
    TodoAddAvailabilityResolver,
    TodoCompleteAvailabilityResolver,
    TodoListAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMO_ADD,
    TOOL_NAME_MEMO_DONE,
    TOOL_NAME_MEMO_LIST,
    TOOL_NAME_MEMORY_EXPLORE_RELATED,
    TOOL_NAME_MEMORY_RECALL_BY_HANDLE,
    TOOL_NAME_MEMORY_RECALL_EPISODES,
    TOOL_NAME_MEMORY_SEARCH_SEMANTIC,
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
    "- 自分の発話・行動の流れの整理 (例: 「リンに『鍵は南扉』と伝えた。『暗号の数字』はまだ確かめていない」)\n"
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
    "memo_id は memo_add / memo_list が表示する短縮形 (例: 'a3b9f1') でも、"
    "full UUID でも受け付けます (git の commit hash と同じ prefix 一致)。"
    "短縮形が複数の memo に一致する場合は曖昧エラーになるので、その場合だけ"
    "より長い prefix または full UUID を指定してください。"
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


MEMORY_SEARCH_SEMANTIC_PARAMETERS = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "検索したい単語・名前・キーワード (例: 「タカシ」「毒キノコ」「北の洞窟」)。"
                "1 語または短いフレーズを推奨。tags と本文の双方を見る。"
            ),
        },
        "top_k": {
            "type": "integer",
            "description": "返す学び (semantic 記憶) の最大件数 (既定 5、最大 32)。",
        },
    },
    "required": ["query"],
}

MEMORY_SEARCH_SEMANTIC_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_MEMORY_SEARCH_SEMANTIC,
    description=(
        "あなた自身の「学び (semantic 記憶)」を能動的に検索します。"
        "passive な想起では出てこない遠い記憶を、固有名詞や概念キーワードで"
        "引き寄せたい時に使ってください。結果は次ターンの観測として現れる"
        "JSON で、世界状態は変えません。"
    ),
    parameters=MEMORY_SEARCH_SEMANTIC_PARAMETERS,
    category=ToolCategory.META_COGNITIVE,
)


# Issue #526 後続: episodic memory の能動 recall (= "思い出そう" と意志する)
MEMORY_RECALL_EPISODES_DESCRIPTION = (
    "過去の自分の経験を能動的に取り出すツール。"
    "受動想起 (= prompt の「関連する記憶」 section) は状況に連想で結びついた"
    "ものだけが自動で並ぶため、それ以外の過去を確認したいときに使う。"
    "\n\n"
    "# 使えるタイミング (例)\n"
    "- 自分の過去の経験を語る前に、想像で埋めず実際の記憶を取り出したいとき\n"
    "- 過去の似た状況を参照したいとき\n"
    "- 過去にした約束や判断を確認したいとき\n"
    "- 「昨日どうだった」「あの場所で何があった」のように時間や場所の問いに答えるとき\n"
    "\n"
    "# 引数\n"
    "- about: 思い出したい内容の自由文 (具体的な人物名・場所名・物の名前が"
    "含まれているとマッチしやすい)。\n"
    "- time_range: 時間範囲の絞り込み (任意)。\"recent\" / \"today\" / "
    "\"yesterday\" / \"this_week\" / \"any\" (既定)。\n"
    "\n"
    "# 結果\n"
    "過去の出来事 (複数件のことあり)。何も思い出せなかったときは"
    "「思い出そうとしたが何も浮かばなかった」と返る。\n"
    "\n"
    "# 注意\n"
    "うろ覚え・誤想起はあり得る。世界状態は変えない。"
)

MEMORY_RECALL_EPISODES_PARAMETERS = {
    "type": "object",
    "properties": {
        "about": {
            "type": "string",
            "description": (
                "思い出したい内容の自由文。具体的な人物名・場所名・物の名前が"
                "含まれているとマッチしやすい (例: 「カイトと閲覧室で話した内容」)。"
                "固有名詞が無いときは time_range と組み合わせる。"
            ),
        },
        "time_range": {
            "type": "string",
            "enum": ["recent", "today", "yesterday", "this_week", "any"],
            "description": (
                "時間範囲の絞り込み。"
                "recent=直近数時間 / today=今日 / yesterday=昨日 / "
                "this_week=今週 / any=絞らない (既定)。"
            ),
        },
    },
    "required": ["about"],
}

MEMORY_RECALL_EPISODES_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_MEMORY_RECALL_EPISODES,
    description=MEMORY_RECALL_EPISODES_DESCRIPTION,
    parameters=MEMORY_RECALL_EPISODES_PARAMETERS,
    category=ToolCategory.META_COGNITIVE,
)


# Issue #526 後続 PR-D: afterglow index (= prompt の「さっき思い出した記憶の
# 見出し」section) から、handle (``ep_<6 文字>``) を指定して本文を引き戻すツール。
# memory_recall_episodes が自由文検索なのに対し、これは prompt 上の handle を
# 直接受け取って「今ぼんやり覚えてる中のこれを詳しく」と取り出す経路。
# 取り出した episode は slot に再注入されるため、しばらく鮮明に浮かぶ状態が続く。
MEMORY_RECALL_BY_HANDLE_DESCRIPTION = (
    "prompt の「【さっき思い出した記憶の見出し】」section に並んでいる handle "
    "(例: ``ep_3f2a7b``) を指定して、その出来事の本文 (recall_text) を引き戻すツール。"
    "\n\n"
    "# 使えるタイミング (例)\n"
    "- 「さっき思い出した記憶の見出し」に気になる項目があり、詳しく思い出したいとき\n"
    "- 過去の出来事を語る前に、見出しからその本文を引き出して確認したいとき\n"
    "\n"
    "# 引数\n"
    "- handle: prompt 上に表示された ``ep_`` で始まる handle 文字列。\n"
    "\n"
    "# 結果\n"
    "該当する episode の本文 (recall_text) を 1 件返す。引き戻した episode は "
    "しばらく「鮮明な記憶」として手元に残る (= slot に再注入される)。\n"
    "該当する見出しが既に消えていた場合は「もう忘れました」と返る。\n"
    "\n"
    "# 注意\n"
    "- 自由文での検索は ``memory_recall_episodes`` を使う。本ツールは prompt 上に "
    "見えている handle 専用。\n"
    "- 世界状態は変えない (= 思い出すだけ)。"
)

MEMORY_RECALL_BY_HANDLE_PARAMETERS = {
    "type": "object",
    "properties": {
        "handle": {
            "type": "string",
            "description": (
                "prompt 上の「【さっき思い出した記憶の見出し】」に並んでいる "
                "``ep_`` で始まる handle 文字列をそのまま渡す (例: ``ep_3f2a7b``)。"
            ),
        },
    },
    "required": ["handle"],
}

MEMORY_RECALL_BY_HANDLE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_MEMORY_RECALL_BY_HANDLE,
    description=MEMORY_RECALL_BY_HANDLE_DESCRIPTION,
    parameters=MEMORY_RECALL_BY_HANDLE_PARAMETERS,
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
    semantic_search_enabled: bool = False,
    memo_enabled: Optional[bool] = None,
    episodic_recall_enabled: bool = False,
    recall_by_handle_enabled: bool = False,
) -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """memo および任意で memory_explore_related / memory_search_semantic /
    memory_recall_episodes を返す。

    ``todo_enabled`` は後方互換のための旧名引数。``memo_enabled`` を渡せば
    そちらが優先される。両方未指定は False (= memo を expose しない)。

    ``semantic_search_enabled`` は Phase 1d。LLM が semantic memory を能動検索
    したい時に使う ``memory_search_semantic`` を expose する。default False。

    ``episodic_recall_enabled`` は Issue #526 後続。LLM が過去 episode を
    「思い出そう」と能動的に呼び戻す ``memory_recall_episodes`` を expose
    する。default False (= 検証フェーズで明示的に ON にする)。
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
    if semantic_search_enabled:
        specs.append(
            (MEMORY_SEARCH_SEMANTIC_DEFINITION, MemorySearchSemanticAvailabilityResolver())
        )
    if episodic_recall_enabled:
        specs.append(
            (MEMORY_RECALL_EPISODES_DEFINITION, MemoryRecallEpisodesAvailabilityResolver())
        )
    if recall_by_handle_enabled:
        specs.append(
            (
                MEMORY_RECALL_BY_HANDLE_DEFINITION,
                MemoryRecallByHandleAvailabilityResolver(),
            )
        )
    return specs


__all__ = [
    "MEMORY_SEARCH_SEMANTIC_DEFINITION",
    "MEMORY_RECALL_EPISODES_DEFINITION",
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
