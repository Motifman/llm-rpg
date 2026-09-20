"""tick 経過で active status effect を処理するステージサービス (PR #2)。

毎 tick で全プレイヤーの active_effects に対して:
1. 継続効果を適用 (BLEEDING / HYPOTHERMIA / INFECTED の HP 漸減、REGENERATION の回復)
2. 期限切れの effect を掃除 (`cleanup_expired_effects`)
3. HP 0 で PlayerDownedEvent → DEAD outcome 連鎖 (E-3a 経路)

SpotGraphSimulationApplicationService の tick パイプラインに組み込む。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope import CommandScopeFactoryPort
    from ai_rpg_world.application.world_graph.player_status_tick_command_repository_provider import (
        PlayerStatusTickCommandRepositoryProviderPort,
    )


# 継続効果の毎 tick 変化量 (HP delta)。負数は damage、正数は heal。
# 値は v2 シナリオの 1 tick = 1 時間 スケールに合わせた暫定値。
DEFAULT_PER_TICK_HP_DELTA: dict[StatusEffectType, int] = {
    StatusEffectType.BLEEDING: -1,       # 出血: 強め (24 時間で -24 HP)
    StatusEffectType.HYPOTHERMIA: -1,    # 低体温: 出血と同程度
    StatusEffectType.INFECTED: -1,        # 感染症: 同程度 (放置で死)
    StatusEffectType.POISON: -2,          # 毒キノコ食害: 出血より速い
    StatusEffectType.REGENERATION: 1,     # 回復: 緩やか
}


class StatusEffectsTickStageService:
    """毎 tick で active_effects を進める stage service。

    - `_per_tick_hp_delta`: StatusEffectType → tick あたり HP delta マップ
    - 集約eventはscope由来repositoryから`CommandContext`へ収集し、確定後に配送する
    """

    def __init__(
        self,
        *,
        per_tick_hp_delta: Optional[dict[StatusEffectType, int]] = None,
        command_scope_factory: Optional[
            "CommandScopeFactoryPort[PlayerStatusTickCommandRepositoryProviderPort]"
        ] = None,
    ) -> None:
        self._per_tick_hp_delta = per_tick_hp_delta or dict(DEFAULT_PER_TICK_HP_DELTA)
        self._command_scope_factory = command_scope_factory

    def set_command_scope_factory(
        self,
        factory: "CommandScopeFactoryPort[PlayerStatusTickCommandRepositoryProviderPort]",
    ) -> None:
        """本番stageを1回の独立した確定境界へ接続する。"""
        self._command_scope_factory = factory

    def run(self, current_tick: WorldTick) -> None:
        """全プレイヤーの active_effects を tick 進行に合わせて処理する。"""
        scope_factory = self._command_scope_factory
        if scope_factory is None:
            raise RuntimeError(
                "status effects tickにはCommandScopeFactoryの配線が必要です"
            )
        with scope_factory.create() as scope:
            repositories = scope.repositories
            if repositories is None:
                raise RuntimeError(
                    "status effects tick用repository providerがありません"
                )
            self._run_with_repository(
                current_tick,
                repositories.player_statuses,
            )

    def _run_with_repository(
        self,
        current_tick: WorldTick,
        player_status_repository: PlayerStatusRepository,
    ) -> None:
        """指定repository上で状態異常を進める。"""
        updated = []
        for status in player_status_repository.find_all():
            # ダウン中は status effect の影響を止める (蘇生後に蓄積しない設計)
            if not status.can_act():
                continue
            if not status.active_effects:
                continue
            changed = False
            # 1. 継続効果の適用。
            # is_expired は current >= expiry なので、expiry_tick == current_tick の
            # 「最終 tick」でも True を返してしまう。そのまま skip にすると
            # duration_ticks=12 のはずが 11 回しか damage が入らない off-by-one が出る。
            # ここでは厳密に「current_tick が expiry を 超えた」ときだけ skip する。
            # その後の cleanup_expired_effects が expiry==current の effect も含めて掃除する。
            for effect in list(status.active_effects):
                if current_tick.value > effect.expiry_tick.value:
                    continue
                hp_delta = self._per_tick_hp_delta.get(effect.effect_type, 0)
                if hp_delta < 0:
                    status.apply_damage(-hp_delta)
                    changed = True
                elif hp_delta > 0:
                    status.heal_hp(hp_delta)
                    changed = True
            # 2. 期限切れの effect を掃除
            before_count = len(status.active_effects)
            status.cleanup_expired_effects(current_tick)
            if len(status.active_effects) != before_count:
                changed = True
            if changed:
                updated.append(status)
        if updated:
            player_status_repository.save_all(updated)
