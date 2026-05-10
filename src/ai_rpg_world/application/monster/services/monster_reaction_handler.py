"""モンスターの「攻撃された相手に対する反応」を処理するハンドラ。

`SpotMonsterBehaviorTickService` の priority chain step 1 として呼び出され、
直近被弾を覚えているモンスターの FLEE / CHASE 状態遷移と、その状態に対応する
1 tick の行動 (FLEE: wander、CHASE: 反撃) を実行する。

設計:
- tick service から `try_react()` を呼ぶ。返り値は `Optional[AttackOutcome]`。
  - `None`: 反応する条件を満たさない → tick service は priority chain を続行
  - 非 None: state 遷移または attack 試行があった → chain は止まる
- FLEE 中の wander 移動は tick service 側の wander 機構を再利用したいので、
  `force_wander_fn` を依存注入で受け取る。

不変条件:
- `chase_attacker_ref` (state スナップショット) を真として CHASE target を解決
  する。`last_attacker_ref` は集約フィールドで後続の被弾で上書きされうるため
  追跡対象としては使わない。
- 状態遷移後は必ず `monster_repository.save(monster)` で永続化する (SQLite
  repo では save しないと state が揮発する)。
"""

from __future__ import annotations

import logging
from typing import Callable, FrozenSet, Literal, Optional

from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
    SpotAttackOrchestrator,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import (
    BehaviorStateEnum,
    MonsterStatusEnum,
    ReactionPolicyEnum,
)
from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterRepository,
)
from ai_rpg_world.domain.monster.value_object.attacker_ref import AttackerRef
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAbandonedChaseInSpotEvent,
    MonsterStartedChasingInSpotEvent,
    MonsterStartedFleeingInSpotEvent,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ConnectionNotPassableException,
    EntityNotInGraphException,
    MonsterNotInGraphException,
)
from ai_rpg_world.domain.world_graph.service.spot_path_finder import find_next_hop
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_attack_outcome import (
    AttackOutcome,
)


logger = logging.getLogger(__name__)


# graph 上の鍵フラグを返す provider。tick service と共通のものを渡す。
WorldFlagsProvider = Callable[[], FrozenSet[str]]


# FLEE 中に呼ぶ wander 関数。tick service 側の `_try_wander_force` を渡す
# (chance を無視して必ず passable 接続へ移動を試みる版)。
ForceWanderFn = Callable[
    [MonsterAggregate, SpotGraphAggregate, SpotId], bool
]

# `_decide_reaction_target` の戻り値。文字列リテラルではなく Literal で
# タイプセーフに表現する (typo を型チェッカーで検出可能)。
ReactionTarget = Literal["flee", "chase"]


class MonsterReactionHandler:
    """直近被弾モンスターの FLEE / CHASE 反応を処理する。

    `SpotMonsterBehaviorTickService` の priority chain step 1 から呼ばれる。

    既知の技術的負債:
    - 1 tick 内で同一 monster に対して `monster_repository.save()` が複数回
      呼ばれる経路が存在する (state 遷移 → orchestrator が attack save 等)。
      InMemory / SQLite では冪等で問題ないが、将来 楽観ロックを導入する場合は
      tick 末で 1 回に集約する必要がある (PR #131 レビュー MEDIUM 指摘と同根)。
    """

    def __init__(
        self,
        monster_repository: MonsterRepository,
        player_status_repository: PlayerStatusRepository,
        attack_orchestrator: SpotAttackOrchestrator,
        force_wander_fn: ForceWanderFn,
        *,
        world_flags_provider: Optional[WorldFlagsProvider] = None,
    ) -> None:
        self._monster_repository = monster_repository
        self._player_status_repository = player_status_repository
        self._orchestrator = attack_orchestrator
        self._force_wander_fn = force_wander_fn
        # multi-spot CHASE で BFS 経路探索の際に通行条件解決に使う。
        # 注入されない場合は空 frozenset (= フラグ依存通路は塞がれる、安全側)。
        self._world_flags_provider = world_flags_provider

    def try_react(
        self,
        monster: MonsterAggregate,
        graph: SpotGraphAggregate,
        spot_id: SpotId,
        current_tick: WorldTick,
    ) -> Optional[AttackOutcome]:
        """直近に攻撃を受けた monster の反応を実行する。

        処理フロー:
        1. 既に FLEE 中なら継続行動 (隣接 spot へ逃走)、grace 切れで IDLE 化
        2. 既に CHASE 中なら反撃攻撃を試みる、grace 切れで IDLE 化
        3. どちらの state でもない場合、`reaction_to_attack` policy + 直近の
           被弾 (`last_attacked_tick`) を見て FLEE/CHASE に遷移してアクション

        Returns:
            None: 反応する条件を満たさない（priority chain は次へ進む）
            AttackOutcome: 反応の実行結果（chain は止まる）
        """
        template = monster.template

        # 状態継続: 既に FLEE / CHASE なら state に従って動く
        if monster.is_fleeing(current_tick):
            self._continue_flee(monster, graph, spot_id)
            return AttackOutcome(executed=False, reason="fleeing")
        # FLEE が grace 切れで終わっていたら IDLE に戻す（次フレームに通常 chain）。
        # FLEE 終了は「自然消滅」として扱い、observation event は発火しない
        # (CHASE の Abandoned event とは意図的に非対称)。プレイヤー視点では
        # 既存の MonsterLeft/Appeared (FLEE 中の wander 移動) で「逃げ去って
        # 行った」が表現済みのため、追加の終了 event は冗長と判断。
        if monster.behavior_state == BehaviorStateEnum.FLEE:
            monster.clear_behavior_state_to_idle()
            self._monster_repository.save(monster)

        if monster.is_chasing():
            return self._continue_chase(monster, graph, spot_id, current_tick)

        # 状態遷移の判断: PASSIVE は何もしない
        if template.reaction_to_attack == ReactionPolicyEnum.PASSIVE:
            return None
        # grace 内の被弾が無ければ反応しない
        last_attacked = monster.last_attacked_tick
        if last_attacked is None:
            return None
        if (current_tick.value - last_attacked.value) > template.flee_grace_ticks:
            return None

        # policy 別に FLEE / CHASE を決定
        target = self._decide_reaction_target(monster)
        if target == "flee":
            monster.enter_flee_state(current_tick, template.flee_grace_ticks)
            # state 遷移を永続化 + 観測 event 発火。SQLite repo では save
            # しないと次 tick で state が揮発する。event は同 spot 全員へ
            # 「相手が逃げ出した」prose として届く。
            self._monster_repository.save(monster)
            graph.add_event(
                MonsterStartedFleeingInSpotEvent.create(
                    aggregate_id=graph.graph_id,
                    aggregate_type="SpotGraphAggregate",
                    monster_id=monster.monster_id,
                    spot_id=spot_id,
                )
            )
            self._continue_flee(monster, graph, spot_id)
            return AttackOutcome(executed=False, reason="fleeing")
        if target == "chase":
            attacker_ref: Optional[AttackerRef] = monster.last_attacker_ref
            if attacker_ref is None:
                # attacker_ref 不明では CHASE できない。fall through。
                return None
            monster.enter_chase_state(
                attacker_ref=attacker_ref,
                last_observed_target_spot_id=spot_id,
                current_tick=current_tick,
            )
            self._monster_repository.save(monster)
            # CHASE 開始 event 発火: target が player か monster かに応じて
            # 該当 ID を埋める (discriminated union)。
            graph.add_event(
                MonsterStartedChasingInSpotEvent.create(
                    aggregate_id=graph.graph_id,
                    aggregate_type="SpotGraphAggregate",
                    monster_id=monster.monster_id,
                    spot_id=spot_id,
                    target_player_id=(
                        self._player_id_to_entity_id(attacker_ref.player_id)
                        if attacker_ref.is_player else None
                    ),
                    target_monster_id=(
                        attacker_ref.monster_id
                        if attacker_ref.is_monster else None
                    ),
                )
            )
            return self._continue_chase(monster, graph, spot_id, current_tick)
        return None

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _decide_reaction_target(
        self, monster: MonsterAggregate,
    ) -> Optional[ReactionTarget]:
        """policy + HP 比から "flee" / "chase" / None を返す。"""
        policy = monster.template.reaction_to_attack
        if policy == ReactionPolicyEnum.ALWAYS_FLEE:
            return "flee"
        if policy == ReactionPolicyEnum.ALWAYS_RETALIATE:
            return "chase"
        if policy == ReactionPolicyEnum.FLEE_WHEN_LOW_HP:
            hp = monster.hp
            if hp.max_hp > 0:
                ratio = hp.value / hp.max_hp
                if ratio < monster.template.flee_threshold:
                    return "flee"
            return "chase"
        return None

    def _continue_flee(
        self,
        monster: MonsterAggregate,
        graph: SpotGraphAggregate,
        spot_id: SpotId,
    ) -> None:
        """FLEE 中の 1 tick 行動: passable な隣接 spot へ移動を試みる。

        攻撃者の方向は避けたいが、最小実装では「ランダムな passable 接続」を
        選ぶ。攻撃者が居なくなれば結果的に逃げ切れる。`current_tick` は
        wander 経路では参照しないためシグネチャから除外している。
        """
        self._force_wander_fn(monster, graph, spot_id)

    def _continue_chase(
        self,
        monster: MonsterAggregate,
        graph: SpotGraphAggregate,
        spot_id: SpotId,
        current_tick: WorldTick,
    ) -> Optional[AttackOutcome]:
        """CHASE 中の 1 tick 行動。

        優先順位:
        1. 追跡対象が同 spot に居る → 攻撃 (orchestrator に委譲)
        2. 追跡対象が graph 上の他 spot に居る → BFS で 1 hop 移動。
           `last_observed_target_spot_id` を更新 (multi-spot 追跡)。
        3. 追跡対象が graph 上に居ない (despawn / 死亡):
           a. `last_observed_target_spot_id` が未設定 → CHASE 解除
           b. 現 spot != last_observed_target_spot_id → そこへ向かって 1 hop
              (見失った場所へ駆け付ける段階)
           c. 現 spot == last_observed_target_spot_id:
              - search_timer == 0 → 探索開始 (chase_search_ticks をセット)
              - search_timer > 0 → 周辺を 1 hop wander + timer 減算
           d. search_timer 切れで IDLE 復帰

        終了条件:
        - 追跡対象 ref が None (state 不整合)
        - grace 切れ (`flee_grace_ticks` 経過)
        - target spot / 探索先への passable 経路が無い
        - 探索タイマー切れ
        """
        attacker_ref: Optional[AttackerRef] = monster.chase_attacker_ref()
        if attacker_ref is None:
            # 不整合系: CHASE 状態にあるのに追跡対象 ref が無い。実運用では
            # DB マイグレーション後の残留 state 等で発生し得る。観測 prose
            # に出すほどの意味がないため event は発火しないが、debug の
            # 手がかりとして warning ログだけは残す。
            logger.warning(
                "CHASE state without chase_attacker_ref for monster=%s, "
                "falling back to IDLE without event",
                monster.monster_id.value,
            )
            monster.clear_behavior_state_to_idle()
            self._monster_repository.save(monster)
            return None

        # grace 切れチェック (被弾以来の反応 tick)
        last_attacked = monster.last_attacked_tick
        if last_attacked is not None and (
            current_tick.value - last_attacked.value
            > monster.template.flee_grace_ticks
        ):
            self._abandon_chase(monster, graph, spot_id, reason="grace_expired")
            return None

        # CHASE 累積 tick 上限チェック (Phase 4b PR c)。
        # `chase_max_ticks=0` は「無制限」を意味するため、判定対象外。
        # 比較は `>` (厳密超過) で実装している。つまり開始 tick から
        # ちょうど `chase_max_ticks` 経過した時点はまだ CHASE 継続、
        # `chase_max_ticks + 1` 経過で初めて IDLE 化する。grace 切れ判定と
        # 統一した境界。
        chase_max_ticks = monster.template.chase_max_ticks
        chase_started = monster.chase_started_at_tick
        if (
            chase_max_ticks > 0
            and chase_started is not None
            and (current_tick.value - chase_started.value) > chase_max_ticks
        ):
            self._abandon_chase(
                monster, graph, spot_id, reason="max_ticks_exceeded",
            )
            return None

        # 1. 同 spot 居れば攻撃 (search 中であっても target 再発見なら攻撃に戻る)
        if attacker_ref.is_player:
            target_player = self._find_player_at_spot(
                graph, spot_id, attacker_ref.player_id
            )
            if target_player is not None:
                self._reset_search_on_rediscovery(monster)
                return self._orchestrator.execute_monster_attack(
                    attacker_monster=monster,
                    target_player=target_player,
                    graph=graph,
                    spot_id=spot_id,
                    current_tick=current_tick,
                )
        else:
            target_monster_obj = self._find_monster_at_spot(
                graph, spot_id, attacker_ref.monster_id
            )
            if target_monster_obj is not None:
                self._reset_search_on_rediscovery(monster)
                return self._orchestrator.execute_monster_to_monster_attack(
                    attacker_monster=monster,
                    target_monster=target_monster_obj,
                    graph=graph,
                    spot_id=spot_id,
                    current_tick=current_tick,
                )

        # 2. 追跡対象が graph 上の他 spot に居れば BFS 1 hop
        target_spot = self._resolve_target_spot(graph, attacker_ref)
        if target_spot is not None:
            # 探索中だった場合は search_timer をリセットしてから移動 (再発見扱い)
            self._reset_search_on_rediscovery(monster)
            return self._chase_visible_target(
                monster=monster, graph=graph, from_spot=spot_id,
                target_spot=target_spot,
            )

        # 3. target が graph 上に居ない → 見失いフェーズ
        return self._handle_lost_target(
            monster=monster, graph=graph, current_spot=spot_id,
        )

    @staticmethod
    def _player_id_to_entity_id(player_id: PlayerId) -> EntityId:
        """`PlayerId` を graph 上の `EntityId` に変換する。

        現状の世界モデルでは「player_id.value (int) と entity_id.value (int)
        が同一空間を共有する」前提で配線されている (graph.place_entity の
        呼び出し側もこの規約に従う)。本 helper は変換を一箇所に集約し、
        将来 player ID 空間が分離した場合の差し替えポイントを 1 つにする。
        """
        return EntityId.create(player_id.value)

    def _abandon_chase(
        self,
        monster: MonsterAggregate,
        graph: SpotGraphAggregate,
        spot_id: SpotId,
        reason: str,
    ) -> None:
        """CHASE → IDLE に戻す + Abandoned event 発火 + save。

        観測パイプラインで「相手が諦めて去っていった」prose を組み立てる
        ための信号。`clear_behavior_state_to_idle()` 単独ではなく本 helper
        経由で呼ぶことで、後続の wander 移動 (MonsterLeft/Appeared) と
        意味的に紐付く。
        """
        monster.clear_behavior_state_to_idle()
        graph.add_event(
            MonsterAbandonedChaseInSpotEvent.create(
                aggregate_id=graph.graph_id,
                aggregate_type="SpotGraphAggregate",
                monster_id=monster.monster_id,
                spot_id=spot_id,
                reason=reason,
            )
        )
        self._monster_repository.save(monster)

    def _reset_search_on_rediscovery(self, monster: MonsterAggregate) -> None:
        """target を再発見した際に search_timer をリセットして即時 save。

        - search 中でない場合は no-op (集約 API 側でガード)
        - リセットしたら save まで責任を持つ。攻撃が cooldown 等で不成立に
          終わっても search_timer=0 が永続化されるよう、`save` を必ず呼ぶ。
          これがないと SQLite 環境で次 tick に再度探索状態に戻る恐れがある。
        """
        if not monster.is_searching_lost_target():
            return
        monster.reset_search_timer_on_rediscovery()
        self._monster_repository.save(monster)

    def _chase_visible_target(
        self,
        monster: MonsterAggregate,
        graph: SpotGraphAggregate,
        from_spot: SpotId,
        target_spot: SpotId,
    ) -> Optional[AttackOutcome]:
        """target が graph 上に居る場合の 1 hop 追跡。"""
        moved = self._move_one_hop_toward(
            monster=monster, graph=graph,
            from_spot=from_spot, target_spot=target_spot,
        )
        if not moved:
            self._abandon_chase(monster, graph, from_spot, reason="no_path")
            return None
        # last_observed_target_spot_id を最新の target spot で更新。
        # 次 tick 以降の見失いフェーズで「ここに駆け付ける」手がかりになる。
        monster.update_chase_last_observed_target_spot(target_spot)
        self._monster_repository.save(monster)
        return AttackOutcome(executed=False, reason="chasing_to_other_spot")

    def _handle_lost_target(
        self,
        monster: MonsterAggregate,
        graph: SpotGraphAggregate,
        current_spot: SpotId,
    ) -> Optional[AttackOutcome]:
        """target が graph 上に居ない場合のフェーズ。

        last_observed_target_spot_id へ向かう / 着いたら探索 / timer 切れで IDLE。
        """
        last_observed = monster.chase_last_observed_target_spot_id
        if last_observed is None:
            # 手がかり無し → CHASE 解除
            self._abandon_chase(
                monster, graph, current_spot, reason="target_lost",
            )
            return None

        # 探索フェーズ中?
        if monster.is_searching_lost_target():
            # 周辺を 1 hop wander、timer 減算
            self._force_wander_fn(monster, graph, current_spot)
            still_running = monster.tick_chase_search_timer()
            if not still_running:
                # timer 切れ → 諦めて IDLE
                self._abandon_chase(
                    monster, graph, current_spot, reason="search_expired",
                )
                return None
            self._monster_repository.save(monster)
            return AttackOutcome(executed=False, reason="searching_lost_target")

        # まだ探索開始前: last_observed に向かうか、着いていれば探索開始
        if current_spot != last_observed:
            # last_observed へ駆け付ける 1 hop
            moved = self._move_one_hop_toward(
                monster=monster, graph=graph,
                from_spot=current_spot, target_spot=last_observed,
            )
            if not moved:
                self._abandon_chase(
                    monster, graph, current_spot, reason="no_path",
                )
                return None
            self._monster_repository.save(monster)
            return AttackOutcome(executed=False, reason="heading_to_last_observed")

        # last_observed に到着済み → 探索フェーズを開始
        search_ticks = monster.template.chase_search_ticks
        if search_ticks <= 0:
            # 探索無効テンプレ → 即 IDLE
            self._abandon_chase(
                monster, graph, current_spot, reason="search_expired",
            )
            return None
        monster.start_chase_search(search_ticks)
        # 探索開始 tick も 1 tick 分のアクション (wander) として消費する。
        # `chase_search_ticks=1` を指定した場合: wander 1 回 → 即 timer=0 → IDLE。
        # `chase_search_ticks=N` (N>=2) の場合: 到着 tick で wander 1 回 + 後続
        # (N-1) tick で wander → 計 N 回探索後 IDLE。
        self._force_wander_fn(monster, graph, current_spot)
        still_running = monster.tick_chase_search_timer()
        if not still_running:
            self._abandon_chase(
                monster, graph, current_spot, reason="search_expired",
            )
            return None
        self._monster_repository.save(monster)
        return AttackOutcome(executed=False, reason="searching_lost_target")

    def _resolve_target_spot(
        self,
        graph: SpotGraphAggregate,
        attacker_ref: AttackerRef,
    ) -> Optional[SpotId]:
        """`attacker_ref` が指す対象が現在居る spot を返す。居なければ None。

        Note: player の `EntityId` は `player_id.value` をそのまま整数空間で
        共有する設計 (graph.place_entity 側と整合)。将来 player ID 空間が
        変わる場合はこの変換も同期して更新する必要がある。
        """
        if attacker_ref.is_player:
            try:
                return graph.get_entity_spot(
                    self._player_id_to_entity_id(attacker_ref.player_id)
                )
            except EntityNotInGraphException:
                return None
        try:
            return graph.get_monster_spot(attacker_ref.monster_id)
        except MonsterNotInGraphException:
            return None

    def _move_one_hop_toward(
        self,
        monster: MonsterAggregate,
        graph: SpotGraphAggregate,
        from_spot: SpotId,
        target_spot: SpotId,
    ) -> bool:
        """`target_spot` に向かう最短経路の 1 hop を実行する。成立なら True。"""
        world_flags = (
            self._world_flags_provider()
            if self._world_flags_provider is not None
            else frozenset()
        )
        owned_item_spec_ids: FrozenSet[ItemSpecId] = frozenset()

        def _is_passable(conn) -> bool:
            return graph.can_traverse_connection(
                conn.connection_id, owned_item_spec_ids, world_flags
            )

        # Phase 4b PR (c): MonsterTemplate.chase_max_distance を BFS の
        # 打ち切り基準にする。0 なら制限なし (`None` 扱い)。これにより
        # 「target が遠ざかったら諦める」挙動を distance 単位で制御できる。
        max_distance_setting = monster.template.chase_max_distance
        max_distance = max_distance_setting if max_distance_setting > 0 else None

        next_hop = find_next_hop(
            graph=graph,
            from_spot=from_spot,
            target_spot=target_spot,
            is_passable=_is_passable,
            max_distance=max_distance,
        )
        if next_hop is None:
            return False
        try:
            graph.move_monster(
                monster_id=monster.monster_id,
                connection_id=next_hop,
                owned_item_spec_ids=owned_item_spec_ids,
                world_flags=world_flags,
            )
        except ConnectionNotPassableException:
            # BFS 時点で通行可と判定したが move_monster までの間に同 tick 内で
            # 他のアクションが状態を変えた場合 (例: 別 monster が扉を閉めた)
            # の TOCTOU。シングルスレッドの現状では稀だが防御的に処理する。
            # CHASE 解除は呼び出し元 _continue_chase に委ねる。
            logger.debug(
                "CHASE: connection became not-passable after BFS for monster=%s",
                monster.monster_id.value,
            )
            return False
        return True

    def _find_player_at_spot(
        self,
        graph: SpotGraphAggregate,
        spot_id: SpotId,
        player_id: PlayerId,
    ) -> Optional[PlayerStatusAggregate]:
        """同 spot に居る指定 player が生存中なら aggregate を返す、なければ None。"""
        presence = graph.presence_at(spot_id)
        for entity_id in presence.present_entity_ids:
            if entity_id.value == player_id.value:
                player = self._player_status_repository.find_by_id(player_id)
                if player is not None and not player.is_down:
                    return player
        return None

    def _find_monster_at_spot(
        self,
        graph: SpotGraphAggregate,
        spot_id: SpotId,
        target_monster_id: MonsterId,
    ) -> Optional[MonsterAggregate]:
        """同 spot に居る指定 monster が生存中なら aggregate を返す、なければ None。"""
        presence = graph.monster_presence_at(spot_id)
        if target_monster_id not in presence.present_monster_ids:
            return None
        target = self._monster_repository.find_by_id(target_monster_id)
        if target is None or target.status != MonsterStatusEnum.ALIVE:
            return None
        return target
