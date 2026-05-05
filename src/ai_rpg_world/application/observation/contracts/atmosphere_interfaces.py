"""Atmosphere バッファのインターフェース。

汎用設計: 環境音以外（匂い・気温の体感など）にも将来再利用できるよう、
カテゴリ非依存の操作のみを提供する。カテゴリ別フィルタは呼び出し側で行う。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ai_rpg_world.application.observation.contracts.atmosphere_dtos import (
    AtmosphereEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class IAtmosphereBuffer(ABC):
    """プレイヤーごとに低優先度の周囲情報エントリを保持するバッファ。"""

    @abstractmethod
    def append(self, player_id: PlayerId, entry: AtmosphereEntry) -> None: ...

    @abstractmethod
    def recent(
        self,
        player_id: PlayerId,
        max_count: int,
    ) -> List[AtmosphereEntry]:
        """直近 max_count 件のエントリを新しい順で返す。"""

    @abstractmethod
    def all(self, player_id: PlayerId) -> List[AtmosphereEntry]: ...

    @abstractmethod
    def clear(self, player_id: PlayerId) -> None: ...
