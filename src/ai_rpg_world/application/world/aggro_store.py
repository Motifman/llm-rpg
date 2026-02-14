"""
アプリケーション層のヘイト（アグロ）ストア。
戦闘で被弾したアクターが「誰にどれだけ攻撃されたか」を保持し、
ターゲット選択（HighestThreatTargetPolicy）で利用する。
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class AggroStore(ABC):
    """ヘイト値を保持・取得するストアのインターフェース。"""

    @abstractmethod
    def add_aggro(
        self,
        spot_id: SpotId,
        victim_id: WorldObjectId,
        attacker_id: WorldObjectId,
        amount: int = 1,
    ) -> None:
        """
        被弾者（victim）に対する攻撃者（attacker）のヘイトを加算する。

        Args:
            spot_id: マップのスポットID
            victim_id: 被弾したアクターのID
            attacker_id: 攻撃したアクターのID
            amount: 加算するヘイト量（1 以上であること。0 以下は不正）

        Raises:
            ValueError: amount が 0 以下の場合
        """
        pass

    @abstractmethod
    def get_threat_by_attacker(
        self,
        spot_id: SpotId,
        attacker_id: WorldObjectId,
    ) -> Dict[WorldObjectId, int]:
        """
        指定した攻撃者（attacker）が各被弾者に対して持つヘイト値を返す。
        TargetSelectionContext.threat_by_id にそのまま渡せる形式。

        Args:
            spot_id: マップのスポットID
            attacker_id: 攻撃者（行動主体）のID

        Returns:
            被弾者ID -> ヘイト値の辞書。該当がなければ空辞書。
        """
        pass
