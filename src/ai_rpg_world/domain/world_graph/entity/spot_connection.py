from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    SpotConnectionValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.passage_condition import PassageCondition


@dataclass(frozen=True)
class SpotConnection:
    """スポット間の接続（有向エッジ）。

    通行可否と音透過率は次の優先順位で決まる:
    1. `passage` が指定されていれば、`is_passable` / `sound_permeability`
       は passage の値で **常に上書きされる**（コンストラクタに直接
       渡された値があってもサイレントに無視される）。これは passage が
       接続の単一の真実情報源 (single source of truth) であることを
       明示するため。
    2. `passage` が None の場合のみ、レガシーフィールド
       `is_passable` / `sound_permeability` を直接保持する。

    新規シナリオは passage を使うこと。レガシーフィールドは旧データの
    後方互換のために残してある。
    """

    connection_id: ConnectionId
    from_spot_id: SpotId
    to_spot_id: SpotId
    name: str
    description: str
    travel_ticks: int
    is_bidirectional: bool
    passage_conditions: List[PassageCondition] = field(default_factory=list)
    sound_permeability: float = 1.0
    is_passable: bool = True
    passage: Optional[Passage] = None

    def __post_init__(self) -> None:
        if self.travel_ticks < 0:
            raise SpotConnectionValidationException(
                f"travel_ticks must be non-negative: {self.travel_ticks}"
            )
        if not (0.0 <= self.sound_permeability <= 1.0):
            raise SpotConnectionValidationException(
                f"sound_permeability must be between 0.0 and 1.0: {self.sound_permeability}"
            )
        if self.passage is not None:
            # passage がある場合は is_passable / sound_permeability を同期する。
            # frozen dataclass なので object.__setattr__ で上書き。
            object.__setattr__(self, "is_passable", self.passage.traversable)
            object.__setattr__(self, "sound_permeability", self.passage.sound_permeability)

    # 通行可否・音透過率の単一参照口。passage と legacy フィールドが両方
    # 存在する設計上、読み手は必ずこのプロパティ経由でアクセスする。
    # 将来の拡張（方向性付き透過率、時間帯変調など）はここに集約する。
    @property
    def effective_traversable(self) -> bool:
        """通行可能か。passage が source of truth。"""
        if self.passage is not None:
            return self.passage.traversable
        return self.is_passable

    @property
    def effective_sound_permeability(self) -> float:
        """音透過率 [0.0, 1.0]。passage が source of truth。"""
        if self.passage is not None:
            return self.passage.sound_permeability
        return self.sound_permeability
