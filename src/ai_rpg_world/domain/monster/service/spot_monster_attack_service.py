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
- 集約変更後は呼び出し側 (application 層) が UnitOfWork で永続化する想定。
  本サービスは event の追加先 aggregate を意図的に持たない
  → MonsterAttackedPlayerInSpotEvent はアプリケーション層で
    SpotGraphAggregate に追加してもらう

戻り値の `MonsterAttackOutcome` でアプリケーション層に「実際に当たったか / 倒したか / damage 値」を伝え、event 生成と prose 表現で使ってもらう。
"""

from __future__ import annotations

from dataclasses import dataclass

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
from ai_rpg_world.domain.common.value_object import WorldTick


@dataclass(frozen=True)
class MonsterAttackOutcome:
    """攻撃の結果。アプリケーション層が event 構築と prose 生成に使う。

    - `executed=False` の場合は前提条件不成立（cooldown / 視認不可 / 敵対外）
      で、aggregate は変更されない
    - `executed=True` の場合 `damage` だけ player に適用済み、
      `target_downed` でダウンしたかも分かる
    """

    executed: bool
    reason: str  # 不成立時の短い理由 (cooldown / not_visible / not_hostile / monster_dead)
    damage: int = 0
    target_downed: bool = False


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
    ) -> MonsterAttackOutcome:
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
            return MonsterAttackOutcome(executed=False, reason="not_hostile")

        if not monster.can_attack_now(current_tick):
            # cooldown または DEAD どちらでもまとめて "cannot_attack"
            return MonsterAttackOutcome(executed=False, reason="cannot_attack")

        if not self._visibility.can_see_target(
            monster.template, effective_lighting
        ):
            return MonsterAttackOutcome(executed=False, reason="not_visible")

        if target_player.is_down:
            return MonsterAttackOutcome(executed=False, reason="target_down")

        damage = max(0, monster.template.base_stats.attack)
        target_player.apply_damage(damage)
        monster.record_attack(current_tick)

        return MonsterAttackOutcome(
            executed=True,
            reason="ok",
            damage=damage,
            target_downed=target_player.is_down,
        )
