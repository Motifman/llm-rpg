"""スポットグラフ世界の攻撃ユースケースを統合するアプリケーションサービス。

モンスター → プレイヤー攻撃と プレイヤー → モンスター攻撃の両方が同じ
オーケストレーション骨組み（"domain service 呼出 → event 発火 → 全 aggregate
save"）を持っているため、ここに 1 つにまとめて重複を排除する。

呼び出し側（tick service / tool executor）は次の責務だけを持つ:
1. 候補となる attacker / target を選ぶ（policy）
2. orchestrator に loaded aggregate を渡す
3. 戻ってきた `AttackOutcome` で UI / ログを組み立てる

orchestrator 自身は:
- domain service を呼んでダメージを適用
- 成立時に `MonsterAttackedPlayerInSpotEvent` /
  `PlayerAttackedMonsterInSpotEvent` を SpotGraphAggregate に追加
- 関係する全 aggregate (graph / monster / player) を save

`AttackOutcome.target_incapacitated` は両 event の同名 field にそのまま
渡される（Phase B の event 対称化により翻訳が不要になった）。

将来追加される攻撃種別（スキル攻撃・cross-domain effect 攻撃・範囲攻撃）も
同じ orchestrator にメソッドを足すか、内部の domain service を差し替えるだけで
event 発火 + save パスが無料で付いてくる。
"""

from __future__ import annotations

import logging
from typing import Optional

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import (
    MonsterAggregate,
)
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterStatusEnum
from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterRepository,
)
from ai_rpg_world.domain.monster.service.spot_monster_attack_service import (
    SpotMonsterAttackService,
)
from ai_rpg_world.domain.monster.service.spot_player_attack_service import (
    SpotPlayerAttackService,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAttackedPlayerInSpotEvent,
    MonsterPredatedMonsterInSpotEvent,
    PlayerAttackedMonsterInSpotEvent,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.service.spot_perception_service import (
    SpotPerceptionService,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.domain.world_graph.value_object.spot_attack_outcome import (
    AttackOutcome,
)

logger = logging.getLogger(__name__)


class SpotAttackOrchestrator:
    """攻撃ユースケースのオーケストレーション。

    callers は loaded aggregate を渡し、orchestrator が domain service 呼出 +
    event 発火 + save を担当する。aggregate のロードは callers の責任に残す
    （tick service と tool executor で「どのアグリゲートを load するか」の
    policy が異なるため）。
    """

    def __init__(
        self,
        spot_graph_repository: ISpotGraphRepository,
        monster_repository: MonsterRepository,
        player_status_repository: PlayerStatusRepository,
        *,
        monster_attack_service: Optional[SpotMonsterAttackService] = None,
        player_attack_service: Optional[SpotPlayerAttackService] = None,
        perception_service: Optional[SpotPerceptionService] = None,
    ) -> None:
        self._spot_graph_repository = spot_graph_repository
        self._monster_repository = monster_repository
        self._player_status_repository = player_status_repository
        self._monster_attack_service = (
            monster_attack_service or SpotMonsterAttackService()
        )
        self._player_attack_service = (
            player_attack_service or SpotPlayerAttackService()
        )
        self._perception = perception_service or SpotPerceptionService()

    # ------------------------------------------------------------------
    # モンスター → プレイヤー攻撃
    # ------------------------------------------------------------------

    def execute_monster_attack(
        self,
        *,
        attacker_monster: MonsterAggregate,
        target_player: PlayerStatusAggregate,
        graph: SpotGraphAggregate,
        spot_id: SpotId,
        current_tick: WorldTick,
    ) -> AttackOutcome:
        """モンスターからプレイヤーへの攻撃を 1 回実行する。

        - lighting は graph から自動算出（光源持ちエンティティ判定は最小実装
          として行わない）
        - 成立時に `MonsterAttackedPlayerInSpotEvent` を graph に追加し、
          monster / player / graph を save
        - 不成立時は何も保存しない（aggregate も無変更）

        Returns: `AttackOutcome`（共通フォーマット）
        """
        effective_lighting = self._compute_lighting(graph, spot_id)
        outcome = self._monster_attack_service.try_attack(
            monster=attacker_monster,
            target_player=target_player,
            effective_lighting=effective_lighting,
            current_tick=current_tick,
        )
        if not outcome.executed:
            return outcome

        # 被害者が view できているかは「環境光量だけ」で判定する単純化。
        # dark_vision モンスターは攻撃可能だが暗闇のプレイヤーには見えないため、
        # target_visible=False を出して formatter に「暗闇から襲われた」を選ばせる。
        target_visible = effective_lighting not in (
            LightingEnum.DARK,
            LightingEnum.PITCH_BLACK,
        )
        graph.add_event(
            MonsterAttackedPlayerInSpotEvent.create(
                aggregate_id=graph.graph_id,
                aggregate_type="SpotGraphAggregate",
                attacker_monster_id=attacker_monster.monster_id,
                spot_id=spot_id,
                target_player_id=EntityId.create(target_player.player_id.value),
                damage=outcome.damage,
                target_incapacitated=outcome.target_incapacitated,
                target_visible=target_visible,
            )
        )
        self._monster_repository.save(attacker_monster)
        self._player_status_repository.save(target_player)
        self._spot_graph_repository.save(graph)
        return outcome

    # ------------------------------------------------------------------
    # プレイヤー → モンスター攻撃
    # ------------------------------------------------------------------

    def execute_player_attack(
        self,
        *,
        attacker_player: PlayerStatusAggregate,
        target_monster: MonsterAggregate,
        graph: SpotGraphAggregate,
        current_tick: WorldTick,
    ) -> AttackOutcome:
        """プレイヤーからモンスターへの攻撃を 1 回実行する。

        spot_id は graph 上のモンスター位置から自動解決する。本 PR では
        致命攻撃でも presence は自動除去しないため `get_monster_spot` は
        成功する前提（despawn 配線が入った場合は orchestrator 側で
        attack 前のキャッシュに切り替える必要あり）。

        Returns: `AttackOutcome`
        """
        outcome = self._player_attack_service.try_attack(
            attacker=attacker_player,
            target_monster=target_monster,
            current_tick=current_tick,
        )
        if not outcome.executed:
            return outcome

        spot_id_for_event = graph.get_monster_spot(target_monster.monster_id)
        graph.add_event(
            PlayerAttackedMonsterInSpotEvent.create(
                aggregate_id=graph.graph_id,
                aggregate_type="SpotGraphAggregate",
                attacker_entity_id=EntityId.create(attacker_player.player_id.value),
                target_monster_id=target_monster.monster_id,
                spot_id=spot_id_for_event,
                damage=outcome.damage,
                target_incapacitated=outcome.target_incapacitated,
            )
        )
        self._monster_repository.save(target_monster)
        self._player_status_repository.save(attacker_player)
        self._spot_graph_repository.save(graph)
        return outcome

    # ------------------------------------------------------------------
    # モンスター → モンスター捕食 (Phase 3b)
    # ------------------------------------------------------------------

    def execute_predation_attack(
        self,
        *,
        attacker_monster: MonsterAggregate,
        prey_monster: MonsterAggregate,
        graph: SpotGraphAggregate,
        spot_id: SpotId,
        current_tick: WorldTick,
    ) -> AttackOutcome:
        """モンスターが prey モンスターに攻撃を 1 回行う（多 tick 戦闘モデル）。

        前提条件 (失敗時 executed=False):
        - attacker が ALIVE + cooldown 切れ
        - 視認可能（環境光量 OR dark_vision、player 攻撃と同じ判定）
        - prey が ALIVE
        - damage > 0

        成立時:
        - `prey.apply_damage(damage, current_tick, attacker_id=...)` で HP 減少
          → 致命なら aggregate 内部で `_die` が発火し `MonsterDiedEvent` 追加
        - `attacker.record_attack(current_tick)` で cooldown 更新
        - 致命攻撃 (`target_incapacitated=True`) なら
          `attacker.record_prey_kill(template.hunger_decrease_on_prey_kill)` で
          hunger 回復
        - `prey.record_attacked_by_in_spot(...)` を呼んで Phase 4 (反撃 / 逃走)
          のための「最後に攻撃された tick」を記録
        - `MonsterPredatedMonsterInSpotEvent` を graph に追加
        - 関係 aggregate (attacker / prey / graph) を save

        damage 計算: `attacker.template.base_stats.attack` をそのまま採用
        （モデル B、防御値・乱数なし）。
        """
        # 攻撃者の前提
        if attacker_monster.status != MonsterStatusEnum.ALIVE:
            return AttackOutcome(executed=False, reason="attacker_dead")
        if not attacker_monster.can_attack_now(current_tick):
            return AttackOutcome(executed=False, reason="cannot_attack")

        # prey の前提
        if prey_monster.status != MonsterStatusEnum.ALIVE:
            return AttackOutcome(executed=False, reason="target_dead")

        # 視認: monster_attack の視認チェックと同じロジック（環境光量 +
        # attacker の dark_vision）。dark_vision 無し + 暗闇では狩らない。
        effective_lighting = self._compute_lighting(graph, spot_id)
        if not self._monster_attack_service._visibility.can_see_target(  # noqa: SLF001
            attacker_monster.template, effective_lighting
        ):
            return AttackOutcome(executed=False, reason="not_visible")

        damage = max(0, attacker_monster.template.base_stats.attack)
        if damage == 0:
            return AttackOutcome(executed=False, reason="zero_damage")

        # ダメージ適用 (HP 0 で aggregate 内部から _die → MonsterDiedEvent)
        prey_monster.apply_damage(
            final_damage=damage,
            current_tick=current_tick,
            attacker_id=attacker_monster.world_object_id,
        )
        attacker_monster.record_attack(current_tick)

        target_incapacitated = prey_monster.status != MonsterStatusEnum.ALIVE
        if target_incapacitated:
            # 致命攻撃なら hunger 回復。`record_prey_kill` 内部で
            # starvation_ticks <= 0 や hunger_decrease <= 0 を no-op で
            # 抜けるので、設定が無いテンプレでも安全に呼べる。
            attacker_monster.record_prey_kill(
                attacker_monster.template.hunger_decrease_on_prey_kill
            )

        # Phase 4 用フック: 最後に攻撃された tick を prey 側に残す。
        # 致命攻撃で死んだ後の no-op は aggregate 側でガードされる。
        prey_monster.record_attacked_by_in_spot(
            attacker_id=attacker_monster.world_object_id,
            current_tick=current_tick,
        )

        graph.add_event(
            MonsterPredatedMonsterInSpotEvent.create(
                aggregate_id=graph.graph_id,
                aggregate_type="SpotGraphAggregate",
                attacker_monster_id=attacker_monster.monster_id,
                target_monster_id=prey_monster.monster_id,
                spot_id=spot_id,
                damage=damage,
                target_incapacitated=target_incapacitated,
            )
        )
        self._monster_repository.save(attacker_monster)
        self._monster_repository.save(prey_monster)
        self._spot_graph_repository.save(graph)

        return AttackOutcome(
            executed=True,
            reason="ok",
            damage=damage,
            target_incapacitated=target_incapacitated,
        )

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _compute_lighting(
        self, graph: SpotGraphAggregate, spot_id: SpotId
    ) -> LightingEnum:
        """スポットの実効照明。光源所持判定は最小実装では行わない。

        TODO: SpotGraphCurrentStateBuilder と同じく光源持ちエンティティの
        有無を見て DIM へ引き上げる必要がある。inventory 解決のコストが高い
        ため tick 1 回の処理として今は省略。
        """
        node = graph.get_spot(spot_id)
        atmosphere: Optional[SpotAtmosphere] = node.atmosphere
        return self._perception.compute_effective_lighting(
            atmosphere, spot_has_any_light_bearer=False
        )
