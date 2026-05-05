"""環境音1エントリの定義（値オブジェクト）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    AmbientSoundDefValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.ambient_sound_filter import (
    AmbientSoundFilter,
)


@dataclass(frozen=True)
class AmbientSoundDef:
    """環境音 atlas の1エントリ。

    Attributes:
        id: シナリオ内一意の識別子。イベントにも載る。
        tags: スポットの ambient_tags との交差で候補に上がる。
        prose: 観測テキスト本文（同スポット用）。
        probability_per_tick: 1 tick あたりの発火確率 [0.0, 1.0]。
        sound_strength: 隣接スポットへの音の強さ（SoundPropagation 用）[0.0, 1.0]。
        filters: フェーズ / 天候 / 屋内屋外による絞り込み。
    """

    id: str
    tags: FrozenSet[str]
    prose: str
    probability_per_tick: float
    sound_strength: float
    filters: AmbientSoundFilter

    def __post_init__(self) -> None:
        if not self.id:
            raise AmbientSoundDefValidationException(
                "AmbientSoundDef.id must not be empty"
            )
        if not self.prose:
            raise AmbientSoundDefValidationException(
                "AmbientSoundDef.prose must not be empty"
            )
        if not 0.0 <= self.probability_per_tick <= 1.0:
            raise AmbientSoundDefValidationException(
                f"AmbientSoundDef.probability_per_tick must be in [0.0, 1.0]: "
                f"{self.probability_per_tick}"
            )
        if not 0.0 <= self.sound_strength <= 1.0:
            raise AmbientSoundDefValidationException(
                f"AmbientSoundDef.sound_strength must be in [0.0, 1.0]: "
                f"{self.sound_strength}"
            )
