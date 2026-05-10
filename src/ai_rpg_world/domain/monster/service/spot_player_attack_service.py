"""プレイヤー → モンスター攻撃の純粋ドメインサービス。

`SpotMonsterAttackService` の対称版。最小実装として:
- ダメージ計算は `attacker.base_stats.attack` をそのまま採用（防御値・乱数なし）
- monster の cooldown は気にしない（プレイヤー側のクールダウンは別途
  ツール側 / プレイヤー集約側で管理する想定。本 PR では入れない）
- 視認チェックは行わない。プレイヤーがモンスターをラベル M1 で指定できる
  時点で「同スポットに居て見えている」前提（current_state ビルダーが
  暗闇では section ごと隠す）
- monster.apply_damage を経由するため `MonsterDamagedEvent` /
  `MonsterDiedEvent` は aggregate 側で自動発火する

呼び出し側はこのサービスを直接呼んだ後、必要に応じて観測 event
（`PlayerAttackedMonsterInSpotEvent`）を SpotGraphAggregate に追加する
責務を持つ（orchestrator / executor 層）。

戻り値は `AttackOutcome`（モンスター → プレイヤー攻撃と統一）。
"""

from __future__ import annotations

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import (
    MonsterAggregate,
)
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterStatusEnum
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.world_graph.value_object.spot_attack_outcome import (
    AttackOutcome,
)


class SpotPlayerAttackService:
    """プレイヤーが同スポットのモンスター 1 体に攻撃を行う純粋ドメインサービス。"""

    def try_attack(
        self,
        attacker: PlayerStatusAggregate,
        target_monster: MonsterAggregate,
        current_tick: WorldTick,
    ) -> AttackOutcome:
        """前提条件を順にチェックし、成立すれば damage を monster に適用する。

        前提条件 (失敗時は executed=False):
        - 攻撃者がダウンしていない
        - target_monster が ALIVE (DEAD / 未出現は target にできない)

        成立時:
        - `attacker.base_stats.attack` をそのまま damage として
          `monster.apply_damage(damage, current_tick, killer_player_id=...)` を呼ぶ
        - HP が 0 になったら aggregate 内部で `_die` が発火し
          `MonsterDiedEvent` が追加される
        - `AttackOutcome.target_incapacitated` は致命攻撃で MonsterDead に
          遷移したかを示す（PlayerDowned と統一概念）
        """
        if attacker.is_down:
            return AttackOutcome(executed=False, reason="attacker_down")

        if target_monster.status != MonsterStatusEnum.ALIVE:
            return AttackOutcome(executed=False, reason="target_dead")

        damage = max(0, attacker.base_stats.attack)
        if damage == 0:
            # PR #127 の monster→player 側と同じ整合: 0 ダメージは event
            # 不発に倒し、ログ・観測のノイズを増やさない。
            return AttackOutcome(executed=False, reason="zero_damage")

        target_monster.apply_damage(
            final_damage=damage,
            current_tick=current_tick,
            killer_player_id=attacker.player_id,
        )

        target_incapacitated = target_monster.status != MonsterStatusEnum.ALIVE
        return AttackOutcome(
            executed=True,
            reason="ok",
            damage=damage,
            target_incapacitated=target_incapacitated,
        )
