"""モンスター pack の群れ逃走 (leader 連動 FLEE) を処理するハンドラ
(Phase 4-O C #2)。

`SpotMonsterBehaviorTickService` の priority chain で reaction の直後 /
pack_reinforcement の前に呼ばれ、「pack leader が FLEE 状態に入ったら
follower (= 同 pack の他 member で `pack_flee_follower=True` のもの) も
連動して FLEE する」挙動を実装する。

設計:
- follower 側のテンプレで `pack_flee_follower=True` を明示した monster
  だけが追従する。default False なので後方互換。
- leader 自身は通常の `MonsterReactionHandler` 経路で FLEE に入る (= 殴ら
  れて ALWAYS_FLEE / FLEE_WHEN_LOW_HP の policy で発動)。本 handler は
  follower 専用。
- follower の FLEE 持続時間は `pack_flee_follower_duration` で独立に制御。
  leader の grace が短い場合に follower が即抜けないようにする。
- 自分が既に FLEE/CHASE 中なら無反応 (state 競合回避)。
- 自分が leader (= `is_pack_leader=True`) なら無反応 (leader は通常経路)。

実装メモ:
- pack 内に複数の monster が追従可能なら、全員が FLEE に入る (上限なし)。
  pack 援護の `max_pack_responders` のような上限は付けない (群れ全体が
  崩壊する演出が意図なので、上限を入れると逆に弱くなる)。
"""

from __future__ import annotations

import logging
from typing import List, Optional

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterStatusEnum
from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterRepository,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterFollowedPackFleeInSpotEvent,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    MonsterNotInGraphException,
)


logger = logging.getLogger(__name__)


class MonsterPackFleeHandler:
    """pack leader の FLEE に follower が連動する。

    `SpotMonsterBehaviorTickService` の priority chain で reaction の直後 /
    pack_reinforcement の前に呼ばれる。
    """

    def __init__(self, monster_repository: MonsterRepository) -> None:
        self._monster_repository = monster_repository

    def try_follow_pack_flee(
        self,
        monster: MonsterAggregate,
        graph: SpotGraphAggregate,
        spot_id: SpotId,
        current_tick: WorldTick,
    ) -> bool:
        """`monster` が pack leader の FLEE に追従して FLEE に入ったら True。

        以下のいずれかなら早期 return False:
        - follower 機能がテンプレで無効 (`pack_flee_follower=False`)
        - duration <= 0 (機能無効化されている)
        - monster が pack に所属していない
        - monster 自身が leader (leader は通常経路で FLEE)
        - 既に FLEE/CHASE 中
        - 同 pack に FLEE 中の leader が居ない
        """
        template = monster.template
        if not template.pack_flee_follower:
            return False
        if template.pack_flee_follower_duration <= 0:
            return False
        if monster.pack_id is None:
            return False
        if monster.is_pack_leader:
            return False
        if monster.is_fleeing(current_tick) or monster.is_chasing():
            return False

        leader = self._find_fleeing_pack_leader(monster, current_tick)
        if leader is None:
            return False

        # FLEE 状態に遷移 + 観測 event 発火
        monster.enter_flee_state(
            current_tick, template.pack_flee_follower_duration,
        )
        self._monster_repository.save(monster)

        graph.add_event(
            MonsterFollowedPackFleeInSpotEvent.create(
                aggregate_id=graph.graph_id,
                aggregate_type="SpotGraphAggregate",
                follower_monster_id=monster.monster_id,
                leader_monster_id=leader.monster_id,
                follower_spot_id=spot_id,
                spot_id=spot_id,
            )
        )
        return True

    # ------------------------------------------------------------------
    # 内部 helper
    # ------------------------------------------------------------------

    def _find_fleeing_pack_leader(
        self, monster: MonsterAggregate, current_tick: WorldTick,
    ) -> Optional[MonsterAggregate]:
        """同 pack で FLEE 中の leader を返す。複数該当する場合は monster_id
        昇順の先頭を選ぶ (pack に複数 leader が居る異常系の防御)。

        leader 不在 / leader が ALIVE 以外 / FLEE 中でない場合は None。
        """
        members = self._monster_repository.find_by_pack_id(monster.pack_id)
        candidates: List[MonsterAggregate] = []
        for member in members:
            if member.monster_id == monster.monster_id:
                continue
            if not member.is_pack_leader:
                continue
            if member.status != MonsterStatusEnum.ALIVE:
                continue
            if not member.is_fleeing(current_tick):
                continue
            candidates.append(member)
        if not candidates:
            return None
        candidates.sort(key=lambda m: m.monster_id.value)
        return candidates[0]
