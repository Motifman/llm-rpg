"""環境音 atlas（値オブジェクト）。

シナリオデータから受け取った AmbientSoundDef 集合を保持し、
タグ・フィルタによる候補絞り込みを提供する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterator, Optional, Tuple

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    AmbientSoundAtlasValidationException,
    AmbientSoundConfigValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.ambient_sound_def import (
    AmbientSoundDef,
)


@dataclass(frozen=True)
class AmbientSoundAtlas:
    """シナリオが宣言した環境音 atlas。

    Attributes:
        defs: AmbientSoundDef のタプル。順序は安定（決定論的なロール順序のため）。
    """

    defs: Tuple[AmbientSoundDef, ...]

    def __post_init__(self) -> None:
        ids: set = set()
        for d in self.defs:
            if d.id in ids:
                raise AmbientSoundAtlasValidationException(
                    f"Duplicate AmbientSoundDef.id in atlas: {d.id}"
                )
            ids.add(d.id)

    def is_empty(self) -> bool:
        return not self.defs

    def __iter__(self) -> Iterator[AmbientSoundDef]:
        return iter(self.defs)

    def find_by_id(self, sound_id: str) -> Optional[AmbientSoundDef]:
        for d in self.defs:
            if d.id == sound_id:
                return d
        return None

    def candidates_for_tags(
        self,
        spot_tags: FrozenSet[str],
    ) -> Tuple[AmbientSoundDef, ...]:
        """スポットのタグと交差する全 def を返す（フィルタは未適用）。"""
        if not spot_tags:
            return ()
        return tuple(d for d in self.defs if d.tags & spot_tags)


@dataclass(frozen=True)
class AmbientSoundThrottleConfig:
    """配信スロットルの設定。

    Attributes:
        min_gap_ticks_per_player: 同一プレイヤーへの環境音配信間隔（>=0）。
            0 なら毎 tick 配信可能。
        dedup_window_size: 同一プレイヤー直近配信履歴のサイズ（>=0）。
            ここに含まれる sound_id は再配信しない。
    """

    min_gap_ticks_per_player: int = 4
    dedup_window_size: int = 3

    def __post_init__(self) -> None:
        if self.min_gap_ticks_per_player < 0:
            raise AmbientSoundConfigValidationException(
                "AmbientSoundThrottleConfig.min_gap_ticks_per_player must be >= 0"
            )
        if self.dedup_window_size < 0:
            raise AmbientSoundConfigValidationException(
                "AmbientSoundThrottleConfig.dedup_window_size must be >= 0"
            )


@dataclass(frozen=True)
class AmbientSoundConfig:
    """環境音機能全体の設定。

    Attributes:
        enabled: 機能の有効化フラグ。
        update_interval_ticks: stage service が走る間隔（1 なら毎 tick）。
        throttle: 配信スロットル設定。
        atlas: 環境音 atlas。
    """

    enabled: bool
    update_interval_ticks: int
    throttle: AmbientSoundThrottleConfig
    atlas: AmbientSoundAtlas

    def __post_init__(self) -> None:
        if self.update_interval_ticks < 1:
            raise AmbientSoundConfigValidationException(
                "AmbientSoundConfig.update_interval_ticks must be >= 1"
            )
