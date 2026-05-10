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

from typing import Callable, Optional

from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
    SpotAttackOrchestrator,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import (
    BehaviorStateEnum,
    MonsterStatusEnum,
    ReactionPolicyEnum,
)
from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterRepository,
)
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
from ai_rpg_world.domain.world_graph.value_object.spot_attack_outcome import (
    AttackOutcome,
)


# FLEE 中に呼ぶ wander 関数。tick service 側の `_try_wander_force` を渡す
# (chance を無視して必ず passable 接続へ移動を試みる版)。
ForceWanderFn = Callable[
    [MonsterAggregate, SpotGraphAggregate, SpotId], bool
]


class MonsterReactionHandler:
    """直近被弾モンスターの FLEE / CHASE 反応を処理する。

    `SpotMonsterBehaviorTickService` の priority chain step 1 から呼ばれる。
    """

    def __init__(
        self,
        monster_repository: MonsterRepository,
        player_status_repository: PlayerStatusRepository,
        attack_orchestrator: SpotAttackOrchestrator,
        force_wander_fn: ForceWanderFn,
    ) -> None:
        self._monster_repository = monster_repository
        self._player_status_repository = player_status_repository
        self._orchestrator = attack_orchestrator
        self._force_wander_fn = force_wander_fn

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
        # FLEE が grace 切れで終わっていたら IDLE に戻す（次フレームに通常 chain）
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
            # state 遷移を永続化。SQLite repo では save しないと次 tick で
            # state が揮発する。
            self._monster_repository.save(monster)
            self._continue_flee(monster, graph, spot_id)
            return AttackOutcome(executed=False, reason="fleeing")
        if target == "chase":
            attacker_ref = monster.last_attacker_ref
            if attacker_ref is None:
                # attacker_ref 不明では CHASE できない。fall through。
                return None
            monster.enter_chase_state(
                attacker_ref=attacker_ref,
                last_known_spot_id=spot_id,
            )
            self._monster_repository.save(monster)
            return self._continue_chase(monster, graph, spot_id, current_tick)
        return None

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _decide_reaction_target(
        self, monster: MonsterAggregate,
    ) -> Optional[str]:
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
        選ぶ。攻撃者が居なくなれば結果的に逃げ切れる。
        """
        self._force_wander_fn(monster, graph, spot_id)

    def _continue_chase(
        self,
        monster: MonsterAggregate,
        graph: SpotGraphAggregate,
        spot_id: SpotId,
        current_tick: WorldTick,
    ) -> Optional[AttackOutcome]:
        """CHASE 中の 1 tick 行動: 同 spot に target が居れば攻撃。

        - 追跡対象は CHASE 開始時に固定された `chase_attacker_ref` を使う
          (`last_attacker_ref` は後続の被弾で上書きされうるため)。
        - target が同 spot に居ない / grace 切れ / ref 不正の場合は IDLE
          に戻して `None` を返し、priority chain の続行 (attack/forage/wander)
          を許す。
        """
        attacker_ref = monster.chase_attacker_ref()
        if attacker_ref is None:
            monster.clear_behavior_state_to_idle()
            self._monster_repository.save(monster)
            return None

        # grace 切れチェック
        last_attacked = monster.last_attacked_tick
        if last_attacked is not None and (
            current_tick.value - last_attacked.value
            > monster.template.flee_grace_ticks
        ):
            monster.clear_behavior_state_to_idle()
            self._monster_repository.save(monster)
            return None

        if attacker_ref.is_player:
            target_player = self._find_player_at_spot(
                graph, spot_id, attacker_ref.player_id
            )
            if target_player is None:
                monster.clear_behavior_state_to_idle()
                self._monster_repository.save(monster)
                return None
            return self._orchestrator.execute_monster_attack(
                attacker_monster=monster,
                target_player=target_player,
                graph=graph,
                spot_id=spot_id,
                current_tick=current_tick,
            )
        # monster の場合
        target_monster = self._find_monster_at_spot(
            graph, spot_id, attacker_ref.monster_id
        )
        if target_monster is None:
            monster.clear_behavior_state_to_idle()
            self._monster_repository.save(monster)
            return None
        return self._orchestrator.execute_monster_to_monster_attack(
            attacker_monster=monster,
            target_monster=target_monster,
            graph=graph,
            spot_id=spot_id,
            current_tick=current_tick,
        )

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
