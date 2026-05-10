"""モンスター → プレイヤー攻撃の純粋ドメインサービス。

スポットグラフ世界での最小戦闘実装。攻撃を試みる前提条件をすべてここで
チェックし、成立するならダメージを 2 つの集約 (MonsterAggregate と
PlayerStatusAggregate) に反映する。

責務:
- 状態 (ALIVE / cooldown) のチェックは aggregate に任せる
- 視認チェックは MonsterVisibilityService に委譲
- 「敵対」判断は最小実装として `MonsterFactionEnum.ENEMY` のみを攻撃許可
- ダメージ計算は最小実装として `template.base_stats.attack` をそのまま採用
  (防御・乱数・命中率なし)
- 集約変更後は呼び出し側 (application 層 / orchestrator) が永続化する想定。
  本サービスは event の追加先 aggregate を意図的に持たない
  → MonsterAttackedPlayerInSpotEvent はアプリケーション層で
    SpotGraphAggregate に追加してもらう

戻り値は `AttackOutcome`（プレイヤー → モンスター攻撃と統一）。
"""

from __future__ import annotations

from ai_rpg_world.domain.monster.aggregate.monster_aggregate import (
    MonsterAggregate,
)
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.monster.service.monster_visibility_service import (
    MonsterVisibilityService,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.value_object.spot_attack_outcome import (
    AttackOutcome,
)
from ai_rpg_world.domain.common.value_object import WorldTick


class SpotMonsterAttackService:
    """同スポットに居る敵対プレイヤー 1 体に攻撃を試みる純粋ドメインサービス。"""

    def __init__(
        self,
        visibility_service: MonsterVisibilityService | None = None,
    ) -> None:
        self._visibility = visibility_service or MonsterVisibilityService()

    def try_attack(
        self,
        monster: MonsterAggregate,
        target_player: PlayerStatusAggregate,
        effective_lighting: LightingEnum,
        current_tick: WorldTick,
    ) -> AttackOutcome:
        """前提条件を順にチェックし、成立すれば damage を player に適用する。

        前提条件 (失敗時は executed=False):
        - monster の faction が ENEMY (最小実装)
        - monster が ALIVE かつ cooldown 切れ (`can_attack_now`)
        - 視認可能 (環境光量 OR dark_vision)
        - target_player がダウンしていない (既に倒れた相手は攻撃しない)

        成立時:
        - `template.base_stats.attack` をそのまま damage として
          `player.apply_damage(damage)` を呼ぶ
        - 監督 aggregate に `record_attack(current_tick)` で cooldown を記録
        - PlayerDownedEvent / MonsterDamagedEvent 等は各 aggregate が発火する
        """
        if monster.template.faction != MonsterFactionEnum.ENEMY:
            return AttackOutcome(executed=False, reason="not_hostile")

        if not monster.can_attack_now(current_tick):
            # cooldown または DEAD どちらでもまとめて "cannot_attack"
            return AttackOutcome(executed=False, reason="cannot_attack")

        if not self._visibility.can_see_target(
            monster.template, effective_lighting
        ):
            return AttackOutcome(executed=False, reason="not_visible")

        if target_player.is_down:
            return AttackOutcome(executed=False, reason="target_down")

        damage = max(0, monster.template.base_stats.attack)
        if damage == 0:
            # `attack=0` のテンプレ（バリデーション上は許容）でも attack が
            # 成立すると prose に「0 のダメージを受けた」と出てしまうため、
            # 攻撃自体を不発扱いにして event を発火しない。cooldown 起点も
            # 進めない（連射されても無害だが、明示的に no-op）。
            return AttackOutcome(executed=False, reason="zero_damage")

        target_player.apply_damage(damage)
        monster.record_attack(current_tick)

        return AttackOutcome(
            executed=True,
            reason="ok",
            damage=damage,
            target_incapacitated=target_player.is_down,
        )
