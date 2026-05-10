"""pack 連動 handler 群 (reinforcement / flee / awareness) で共有する
ヘルパー関数 (Phase 4-O C 全体)。

3 つの handler で重複していたロジックを集約することで、保守ポイントを
1 箇所にする。基底クラスではなく自由関数として提供することで、各 handler
の責務 (どんな state 遷移を起こすか) は handler 側に閉じる。
"""

from __future__ import annotations

from typing import Optional

from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    MonsterNotInGraphException,
)


def resolve_monster_spot(
    graph: SpotGraphAggregate, monster: MonsterAggregate,
) -> Optional[SpotId]:
    """graph 上の monster の現在 spot を取得する。未配置なら None。

    pack handler 群 (援護 / 警戒共有) で「仲間までの距離を測る」際に共通
    して必要になる lookup。`MonsterNotInGraphException` だけ握りつぶして
    None 返却する (それ以外の例外は明示的に伝播)。
    """
    try:
        return graph.get_monster_spot(monster.monster_id)
    except MonsterNotInGraphException:
        return None
