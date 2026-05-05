"""スポットの「現在暗いか？」を合成判定するドメインサービス（stateless）。

合成ルール:
    spot.is_intrinsically_dark OR (spot.is_outdoor AND time_of_day.is_dark)

設計意図:
- 「常時暗いスポット」（地下・遮光された屋内など）は時刻に依存せず暗い。
- 「屋外スポット」は夜・深夜などフェーズが暗い時のみ暗い。
- 屋内かつ ``is_intrinsically_dark=False`` の場合（窓のない普通の建物内部など）は、
  本サービスは「暗くない」を返す。視覚モデルとしては SpotAtmosphere.lighting で
  独立に表現できるため、本サービスは時間依存の暗闇のみを担当する。

DayNight サイクルが無効なシナリオでは ``time_of_day=None`` を渡して呼ぶことで、
``is_intrinsically_dark`` のみが効くようになる。
"""

from __future__ import annotations

from typing import Optional

from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.value_object.time_of_day import TimeOfDay


class SpotDarknessQueryService:
    """スポットが現時点で暗いかを合成判定する。"""

    def is_dark(
        self,
        spot: SpotNode,
        time_of_day: Optional[TimeOfDay],
    ) -> bool:
        if spot.is_intrinsically_dark:
            return True
        if spot.is_outdoor and time_of_day is not None and time_of_day.is_dark:
            return True
        return False
