from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.sound_clarity import SoundClarityEnum
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


@dataclass(frozen=True)
class SoundRecipient:
    """音が届いたエンティティとその明瞭さ。

    Issue #269 第17回観察: SHOUT/SAY を聞いた listener に方向情報が無く、
    遠くの声が聞こえても見当違いの方向に動いてしまう問題があった。listener
    に「どの接続 (扉/通路) を通って音が届いたか」を返すため、BFS の最後の
    1 hop を覚えておく:

    - ``source_connection_name``: 音が listener の現在スポットに到達した
      最後のホップで通った接続の名前 (例: 「閲覧室の扉」)。
    - ``source_adjacent_spot_id``: その接続の listener 側から見た「向こう」
      にある隣接スポット ID。LLM が travel_to の destination を組み立てる
      ための機械的な手がかり。
    - 話者と同じスポット (hop=0) で聞いた listener では、これらは ``None``
      ("方向が無い" を表す)。
    """

    entity_id: EntityId
    spot_id: SpotId
    clarity: SoundClarityEnum
    source_connection_name: Optional[str] = None
    source_adjacent_spot_id: Optional[SpotId] = None
