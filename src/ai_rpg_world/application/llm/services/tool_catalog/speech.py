"""発言系ツールの定義 (Issue #264 後続で SAY/WHISPER を統合)。

旧 SAY_DEFINITION / WHISPER_DEFINITION の 2 tool は廃止し、channel 引数を
持つ単一 SPEECH_DEFINITION に統合した (SHOUT も同時に LLM へ公開)。
詳細は ``tool_catalog/spot_graph.py`` の ``SPEECH_DEFINITION`` を参照。

availability resolver は本家経路用 (tile-map ベース等) に残し、SPEECH_DEFINITION
1 つを返す。
"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.availability_resolvers import (
    SayAvailabilityResolver,
)
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    SPEECH_DEFINITION,
)


def get_speech_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """発言系ツールの (definition, resolver) 一覧を返す。

    Issue #264 後続: 旧 say / whisper を統合した SPEECH_DEFINITION のみを返す。
    availability resolver は say の解像度 (= 同 spot 範囲があるかどうか) で
    判定する (SayAvailabilityResolver を流用)。
    """
    return [
        (SPEECH_DEFINITION, SayAvailabilityResolver()),
    ]


__all__ = [
    "get_speech_specs",
    "SPEECH_DEFINITION",
]
