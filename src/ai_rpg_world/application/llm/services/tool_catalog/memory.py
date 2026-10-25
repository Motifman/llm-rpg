"""エピソード記憶メタツールの定義。"""

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.contracts.tool_category import ToolCategory
from ai_rpg_world.application.llm.services.availability_resolvers import (
    EpisodeRecallAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_EPISODE_RECALL,
    TOOL_NAME_EPISODE_REVISE_INDEX,
)
from ai_rpg_world.being.domain.episode import INDEX_TEXT_MAX_LENGTH


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


def get_memory_specs(
    *,
    episode_recall_max_handles: int | None = None,
    episode_index_revision_enabled: bool = False,
) -> list[tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """目次つきのエピソードの道具を返す。

    ``episode_recall_max_handles`` を渡すと、目次つきのエピソードの呼び出し
    ``episode_recall`` をその上限で出す (#1623)。None なら出さない。
    ``episode_index_revision_enabled`` は、その目次を直す ``episode_revise_index``。
    """
    specs: list[tuple[ToolDefinitionDto, IAvailabilityResolver]] = []
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
    "EPISODE_REVISE_INDEX_DEFINITION",
    "episode_recall_definition",
    "get_memory_specs",
]
