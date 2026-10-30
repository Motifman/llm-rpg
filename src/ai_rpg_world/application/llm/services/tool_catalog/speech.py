"""発言系ツールの定義 (Issue #264 後続で SAY/WHISPER を統合)。

旧 SAY_DEFINITION / WHISPER_DEFINITION の 2 tool は廃止し、channel 引数を
持つ単一 SPEECH_DEFINITION に統合した (SHOUT も同時に LLM へ公開)。
詳細は ``tool_catalog/spot_graph.py`` の ``SPEECH_DEFINITION`` を参照。

現在状態が取得できているかを SayAvailabilityResolver で判定し、
SPEECH_DEFINITION 1 つを返す。
"""

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.availability_resolvers import (
    SayAvailabilityResolver,
)
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    SPEECH_DEFINITION,
)


def get_speech_specs() -> list[tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """発言系ツールの (definition, resolver) 一覧を返す。

    Issue #264 後続: 旧 say / whisper を統合した SPEECH_DEFINITION のみを返す。
    SayAvailabilityResolver は現在状態の有無だけで利用可否を判定する。
    """
    return [
        (SPEECH_DEFINITION, SayAvailabilityResolver()),
    ]


__all__ = [
    "get_speech_specs",
    "SPEECH_DEFINITION",
]
