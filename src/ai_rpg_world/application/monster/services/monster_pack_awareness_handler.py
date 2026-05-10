"""モンスター pack の警戒共有 (scout の CHASE 連動) を処理するハンドラ
(Phase 4-O C #3)。

`SpotMonsterBehaviorTickService` の priority chain で reaction の直後 /
pack_flee の後 / pack_reinforcement の後に呼ばれ、「同 pack の scout
(= 任意の member で CHASE 中) が target を追跡しているなら、近くの仲間も
同じ target を CHASE 開始する」挙動を実装する。

設計:
- 自分が `pack_awareness_radius > 0` のテンプレで明示有効化されている
  monster だけが受信対象。default 0 で機能無効 (後方互換)。
- scout 側に特別なフラグは不要 (CHASE 中であることがトリガー)。任意の
  pack member が target を視認 → CHASE 開始 → 自動で pack に伝播する。
- 自分が既に FLEE/CHASE 中なら無反応 (state 競合回避)。
- scout 自身が `chase_attacker_ref` を持つ前提 (= 通常の CHASE 経路で
  入った monster なら必ず持つ。pack 援護経由の CHASE でも同様)。
- pack 援護 (`pack_help_radius`) との違い: 援護は「殴られた仲間」を契機
  にするが、警戒共有は「scout が CHASE 中」を契機にする。両方有効な
  monster はどちらの経路でも CHASE に入れるが、結果は同じ (CHASE 開始)
  なので競合しない。

実装メモ:
- 援護と同じく BFS で距離測定 (`spot_path_finder.find_hop_distance`)
- 上限なし: 距離内の全 follower が同 target を CHASE 開始 (群れ警戒の
  演出。`max_pack_responders` のような上限は付けない)
- pack_members は optional 引数で外から渡せる (PR #145 と同じ最適化)
"""

from __future__ import annotations

import logging
from typing import Callable, FrozenSet, List, Optional

from ai_rpg_world.application.monster.services._pack_handler_helpers import (
    resolve_monster_spot,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterStatusEnum
from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterRepository,
)
from ai_rpg_world.domain.monster.value_object.attacker_ref import AttackerRef
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAlertedByPackInSpotEvent,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    MonsterNotInGraphException,
)
from ai_rpg_world.domain.world_graph.service.spot_path_finder import (
    find_hop_distance,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


logger = logging.getLogger(__name__)


WorldFlagsProvider = Callable[[], FrozenSet[str]]


class MonsterPackAwarenessHandler:
    """pack の scout が CHASE 中なら、近くの仲間も同じ target を CHASE する。

    `SpotMonsterBehaviorTickService` の priority chain で reaction →
    pack_flee → pack_reinforcement → **本 handler** の順で呼ばれる。
    """

    def __init__(
        self,
        monster_repository: MonsterRepository,
        *,
        world_flags_provider: Optional[WorldFlagsProvider] = None,
    ) -> None:
        self._monster_repository = monster_repository
        self._world_flags_provider = world_flags_provider

    def try_alert_from_pack(
        self,
        monster: MonsterAggregate,
        graph: SpotGraphAggregate,
        spot_id: SpotId,
        current_tick: WorldTick,
        *,
        pack_members: Optional[List[MonsterAggregate]] = None,
    ) -> bool:
        """`monster` が pack scout の CHASE を察知して CHASE に入ったら True。

        Args:
            pack_members: 同 pack 内の member リスト (optional, PR #145 と
                同じ最適化パターン)。

        以下のいずれかなら早期 return False:
        - awareness 機能がテンプレで無効 (`pack_awareness_radius == 0`)
        - monster が pack に所属していない
        - 既に FLEE/CHASE 中
        - 同 pack に CHASE 中の scout が居ない (or scout の
          `chase_attacker_ref` が None)
        - 自分が scout から `pack_awareness_radius` hop 以上離れている
        """
        template = monster.template
        if template.pack_awareness_radius <= 0:
            return False
        if monster.pack_id is None:
            return False
        if monster.is_fleeing(current_tick) or monster.is_chasing():
            return False

        if pack_members is None:
            pack_members = self._monster_repository.find_by_pack_id(
                monster.pack_id
            )
        scout = self._find_chasing_pack_scout_from(monster, pack_members)
        if scout is None:
            return False

        # scout の現在 spot を引いて警戒共有距離を測る
        scout_spot = resolve_monster_spot(graph, scout)
        if scout_spot is None:
            return False

        world_flags = (
            self._world_flags_provider()
            if self._world_flags_provider is not None
            else frozenset()
        )

        def _is_passable(conn) -> bool:
            return graph.can_traverse_connection(
                conn.connection_id, frozenset(), world_flags,
            )

        distance = find_hop_distance(
            graph=graph,
            from_spot=spot_id,
            target_spot=scout_spot,
            is_passable=_is_passable,
            max_distance=template.pack_awareness_radius,
        )
        if distance is None:
            return False

        # scout の chase_attacker_ref を継承して自分も CHASE 開始
        scout_target_ref = scout.chase_attacker_ref()
        if scout_target_ref is None:
            return False  # 不整合系 (scout が CHASE 中だが ref 無し)

        # `last_observed_target_spot_id` には scout の現在 spot を proxy
        # として渡す。target の真の現在位置は responder からは不明なので、
        # scout が直近で target に反応した位置を「最後に target を見た
        # spot」として共有する近似モデル。target が scout から既に別 spot
        # に移動済みの場合、responder は scout の spot に向かい、そこで
        # target を見つけられなければ search → 諦める通常経路で動く。
        # pack 援護 (`MonsterPackReinforcementHandler`) で victim_spot を
        # proxy にしているのと同じ設計判断。
        monster.enter_chase_state(
            attacker_ref=scout_target_ref,
            last_observed_target_spot_id=scout_spot,
            current_tick=current_tick,
        )
        self._monster_repository.save(monster)

        graph.add_event(
            MonsterAlertedByPackInSpotEvent.create(
                aggregate_id=graph.graph_id,
                aggregate_type="SpotGraphAggregate",
                responder_monster_id=monster.monster_id,
                scout_monster_id=scout.monster_id,
                responder_spot_id=spot_id,
                spot_id=spot_id,
                target_player_id=(
                    EntityId.create(scout_target_ref.player_id.value)
                    if scout_target_ref.is_player else None
                ),
                target_monster_id=(
                    scout_target_ref.monster_id
                    if scout_target_ref.is_monster else None
                ),
            )
        )
        return True

    # ------------------------------------------------------------------
    # 内部 helper
    # ------------------------------------------------------------------

    def _find_chasing_pack_scout_from(
        self,
        monster: MonsterAggregate,
        members: List[MonsterAggregate],
    ) -> Optional[MonsterAggregate]:
        """与えられた pack member 群から CHASE 中で `chase_attacker_ref` が
        セット済みの scout を返す。

        自分自身は除外。複数該当する場合は monster_id 昇順の先頭を選ぶ
        (再現性確保)。CHASE 中だが ref が無い不整合 member は除外。
        """
        candidates: List[MonsterAggregate] = []
        for member in members:
            if member.monster_id == monster.monster_id:
                continue
            if member.status != MonsterStatusEnum.ALIVE:
                continue
            if not member.is_chasing():
                continue
            if member.chase_attacker_ref() is None:
                continue
            candidates.append(member)
        if not candidates:
            return None
        candidates.sort(key=lambda m: m.monster_id.value)
        return candidates[0]

    # `_resolve_monster_spot` は `_pack_handler_helpers.resolve_monster_spot`
    # に統合した (HIGH #3 対応: 援護ハンドラと完全重複していたため共通化)。
