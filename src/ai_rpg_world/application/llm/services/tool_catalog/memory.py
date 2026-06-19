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
    "過去に自分が経験した出来事を能動的に思い出そうとします。"
    "passive な想起 (= prompt に自動で並ぶ「関連する記憶」) では拾えなかった "
    "場面 (= 場所違いの過去 / 古い episode / 質問への返答) のための経路です。"
    "\n\n"
    "# いつ使うか\n"
    "- 「昨日何してた?」「先週どこ行った?」のような時間軸の問いに答えるとき\n"
    "- 誰かの名前を聞いて、その人物との過去の出来事を思い出したいとき\n"
    "- 似た状況に再び遭遇して、過去の似た経験を参照したいとき\n"
    "- 何か違和感があり、自分の過去の判断や約束を確認したいとき\n"
    "\n"
    "# 引数の書き方\n"
    "- about: 思い出したい内容の自由文。**具体的な人物名・場所名・物の名前が"
    "含まれていると recall がより的確になります** (例: 「カイトと閲覧室で"
    "何を話したか」)。固有名詞が含まれない概念的な問い (例: 「俺昨日何"
    "したっけ?」) でも使えますが、その場合は time_range と組み合わせる"
    "のが効果的。\n"
    "- time_range: 時間範囲の絞り込み (任意)。\"recent\"=直近の数時間、"
    "\"today\"=今日、\"yesterday\"=昨日、\"this_week\"=今週、\"any\"=絞らない (既定)。\n"
    "\n"
    "# 結果\n"
    "思い出した過去の出来事の説明文 (複数件のことがあります)。"
    "全く思い出せなかったときは「思い出そうとしたが何も浮かばなかった」と"
    "返ります。\n"
    "\n"
    "# 注意\n"
    "うろ覚え・誤想起の可能性があります。返ってきた内容を新しい事実として"
    "外部に言及するときは、自分の記憶であることを明示する (例: 「確か...だった"
    "気がする」「うろ覚えだけど...」) と人間らしくなります。世界状態は変えません。"
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
