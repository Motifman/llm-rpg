"""モンスター pack の援護行動を処理するハンドラ (Phase 4-O C)。

`SpotMonsterBehaviorTickService` の priority chain step 1.5 (reaction の
直後 / attack の前) として呼び出され、「仲間が殴られたら近くの pack
member が CHASE で駆け付ける」挙動を実装する。

設計:
- 同 pack の member が直近 grace_ticks 以内に被弾している (= victim) なら、
  自分が template の `pack_help_radius` 以内に居て、かつ自分自身も pack
  援護機能が有効 (`pack_help_radius > 0` && `max_pack_responders > 0`)
  なら、victim を殴った相手 (`last_attacker_ref`) を target として CHASE
  状態に入る。
- 「最大何匹応答するか」は victim の `max_pack_responders` で制限する。
  victim が「2 匹までしか呼ばない」なら 3 匹目以降は反応しない。
- 既に CHASE / FLEE 状態の monster は援護に反応しない (state 競合回避)。
- 既に同じ target を CHASE 中の monster は二重応答しない。

重要:
- BFS は `SpotPathFinder.find_next_hop` ではなく距離測定用に使うので、
  ここでは graph 経由で距離を計測する小さな helper を内部で持つ。
  pack_help_radius=1 なら隣接 spot のみ。
- victim の attacker_ref が None の場合 (ref 不明) は援護できない。
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Callable, FrozenSet, List, Optional

from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
    SpotAttackOrchestrator,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import (
    BehaviorStateEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterRepository,
)
from ai_rpg_world.domain.monster.value_object.attacker_ref import AttackerRef
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterRespondedToPackHelpInSpotEvent,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    MonsterNotInGraphException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


logger = logging.getLogger(__name__)


# graph 上の通行可否を返す provider (鍵フラグ等を解決)。
WorldFlagsProvider = Callable[[], FrozenSet[str]]


class MonsterPackReinforcementHandler:
    """pack member が攻撃されたとき、近くの仲間が CHASE で駆け付ける。

    `SpotMonsterBehaviorTickService` の priority chain で「reaction の直後 /
    attack の前」に呼ばれる。reaction (= 自分が殴られた CHASE) の方が優先
    度が高い設計。
    """

    def __init__(
        self,
        monster_repository: MonsterRepository,
        *,
        world_flags_provider: Optional[WorldFlagsProvider] = None,
    ) -> None:
        self._monster_repository = monster_repository
        self._world_flags_provider = world_flags_provider

    def try_respond_to_pack_help(
        self,
        monster: MonsterAggregate,
        graph: SpotGraphAggregate,
        spot_id: SpotId,
        current_tick: WorldTick,
    ) -> bool:
        """`monster` が同 pack 仲間の救援に応答して CHASE に入ったら True。

        以下のいずれかに該当する場合は早期 return False:
        - monster が pack に所属していない (`pack_id is None`)
        - template で援護機能が無効 (`pack_help_radius == 0`)
        - monster が既に FLEE / CHASE 状態 (state 競合回避)
        - 同 pack に grace_ticks 内に被弾した victim が居ない
        - 自分が victim から `pack_help_radius` hop 以上離れている
        - victim の `max_pack_responders` 上限に既に達している
        """
        template = monster.template
        if template.pack_help_radius <= 0 or template.max_pack_responders <= 0:
            return False
        if monster.pack_id is None:
            return False
        if monster.is_fleeing(current_tick) or monster.is_chasing():
            return False

        victim = self._find_pack_victim(monster, current_tick)
        if victim is None:
            return False

        # victim の現在 spot を引いて援護距離を測る
        victim_spot = self._resolve_monster_spot(graph, victim)
        if victim_spot is None:
            return False
        distance = self._bfs_distance(
            graph=graph,
            from_spot=spot_id,
            target_spot=victim_spot,
            max_distance=template.pack_help_radius,
        )
        if distance is None:
            return False

        # victim 側が指定する応答上限。victim の template が制限を持つ
        # (殴られた本人がどれだけ仲間を呼ぶかを決める)
        responder_cap = victim.template.max_pack_responders
        if self._count_existing_responders(monster, victim) >= responder_cap:
            return False

        # CHASE 状態に遷移 (victim を殴った相手を追跡)
        attacker_ref = victim.last_attacker_ref
        if attacker_ref is None:
            # victim 側に attacker_ref が記録されていなければ援護できない
            return False
        monster.enter_chase_state(
            attacker_ref=attacker_ref,
            last_observed_target_spot_id=victim_spot,
            current_tick=current_tick,
        )
        self._monster_repository.save(monster)

        graph.add_event(
            MonsterRespondedToPackHelpInSpotEvent.create(
                aggregate_id=graph.graph_id,
                aggregate_type="SpotGraphAggregate",
                responder_monster_id=monster.monster_id,
                victim_monster_id=victim.monster_id,
                responder_spot_id=spot_id,
                spot_id=spot_id,
                target_player_id=(
                    EntityId.create(attacker_ref.player_id.value)
                    if attacker_ref.is_player else None
                ),
                target_monster_id=(
                    attacker_ref.monster_id
                    if attacker_ref.is_monster else None
                ),
            )
        )
        return True

    # ------------------------------------------------------------------
    # 内部 helper
    # ------------------------------------------------------------------

    def _find_pack_victim(
        self, monster: MonsterAggregate, current_tick: WorldTick,
    ) -> Optional[MonsterAggregate]:
        """同 pack で grace_ticks 以内に被弾した最初の生存 member を返す。

        自分自身は除外。`last_attacker_ref` が無い member もスキップ。
        複数該当する場合は monster_id 昇順で先頭を選ぶ (再現性確保)。
        """
        members = self._monster_repository.find_by_pack_id(monster.pack_id)
        candidates: List[MonsterAggregate] = []
        for member in members:
            if member.monster_id == monster.monster_id:
                continue
            if member.status != MonsterStatusEnum.ALIVE:
                continue
            if member.last_attacker_ref is None:
                continue
            if member.last_attacked_tick is None:
                continue
            grace = member.template.flee_grace_ticks
            if grace <= 0:
                continue
            elapsed = current_tick.value - member.last_attacked_tick.value
            if elapsed < 0 or elapsed > grace:
                continue
            candidates.append(member)
        if not candidates:
            return None
        candidates.sort(key=lambda m: m.monster_id.value)
        return candidates[0]

    def _count_existing_responders(
        self, current: MonsterAggregate, victim: MonsterAggregate,
    ) -> int:
        """victim と同じ target を既に CHASE 中の同 pack member 数を数える。

        `current` (これから応答しようとしている自分) は数えない。`victim`
        本人 (CHASE には入れない) も数えない。`max_pack_responders` 上限
        判定で「既に 2 匹応答済みならこれ以上は来ない」を実現する。
        """
        if victim.last_attacker_ref is None:
            return 0
        target_ref = victim.last_attacker_ref
        members = self._monster_repository.find_by_pack_id(victim.pack_id)
        count = 0
        for member in members:
            if member.monster_id == current.monster_id:
                continue
            if member.monster_id == victim.monster_id:
                continue
            if member.status != MonsterStatusEnum.ALIVE:
                continue
            if not member.is_chasing():
                continue
            chase_ref = member.chase_attacker_ref()
            if chase_ref is None:
                continue
            if self._refs_equal(chase_ref, target_ref):
                count += 1
        return count

    @staticmethod
    def _refs_equal(a: AttackerRef, b: AttackerRef) -> bool:
        if a.is_player and b.is_player:
            return a.player_id == b.player_id
        if a.is_monster and b.is_monster:
            return a.monster_id == b.monster_id
        return False

    def _resolve_monster_spot(
        self, graph: SpotGraphAggregate, monster: MonsterAggregate,
    ) -> Optional[SpotId]:
        try:
            return graph.get_monster_spot(monster.monster_id)
        except MonsterNotInGraphException:
            return None

    def _bfs_distance(
        self,
        graph: SpotGraphAggregate,
        from_spot: SpotId,
        target_spot: SpotId,
        max_distance: int,
    ) -> Optional[int]:
        """`from_spot` から `target_spot` までの最短 hop 数を返す。

        到達不可 / max_distance 超過なら None。同 spot は 0。passable
        フィルタは適用するが、所持アイテムは無し (鍵が要る通路は通れない
        前提)。
        """
        if from_spot == target_spot:
            return 0
        world_flags = (
            self._world_flags_provider()
            if self._world_flags_provider is not None
            else frozenset()
        )

        def _is_passable(conn) -> bool:
            return graph.can_traverse_connection(
                conn.connection_id, frozenset(), world_flags,
            )

        # BFS。max_distance を hop 上限として打ち切る。
        queue: deque[tuple[SpotId, int]] = deque([(from_spot, 0)])
        visited = {from_spot}
        while queue:
            current, depth = queue.popleft()
            if depth >= max_distance:
                continue
            connections = sorted(
                graph.iter_outgoing_connections_from(current),
                key=lambda c: c.connection_id.value,
            )
            for conn in connections:
                if not _is_passable(conn):
                    continue
                nxt = conn.to_spot_id
                if nxt in visited:
                    continue
                visited.add(nxt)
                if nxt == target_spot:
                    return depth + 1
                queue.append((nxt, depth + 1))
        return None
