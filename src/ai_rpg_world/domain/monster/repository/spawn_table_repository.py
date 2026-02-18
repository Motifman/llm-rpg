"""スポーン定義（スポット単位のスポーンテーブル）のリポジトリインターフェース。"""

from abc import abstractmethod
from typing import Optional

from ai_rpg_world.domain.monster.value_object.spot_spawn_table import SpotSpawnTable
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class SpawnTableRepository:
    """
    スポット単位のスポーンテーブルを取得するリポジトリ。
    設定的な要素は後から差し替え可能な骨格用。
    """

    @abstractmethod
    def find_by_spot_id(self, spot_id: SpotId) -> Optional[SpotSpawnTable]:
        """指定スポットのスポーンテーブルを取得する。存在しない場合は None。"""
        pass
