from typing import Optional, List

from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.service.player_config_service import PlayerConfigService, DefaultPlayerConfigService
from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.player.event.status_events import (
    PlayerDownedEvent,
    PlayerEvadedEvent,
    PlayerRevivedEvent,
    PlayerLevelUpEvent,
    PlayerHpHealedEvent,
    PlayerMpConsumedEvent,
    PlayerMpHealedEvent,
    PlayerStaminaConsumedEvent,
    PlayerStaminaHealedEvent,
    PlayerGoldEarnedEvent,
    PlayerGoldPaidEvent,
    PlayerLocationChangedEvent,
)
from ai_rpg_world.domain.player.exception import (
    InsufficientMpException,
    InsufficientStaminaException,
    InsufficientHpException,
    InsufficientGoldException,
    PlayerDownedException
)


class PlayerStatusAggregate(AggregateRoot):
    """プレイヤーステータス集約"""

    def __init__(
        self,
        player_id: PlayerId,
        base_stats: BaseStats,
        stat_growth_factor: StatGrowthFactor,
        exp_table: ExpTable,
        growth: Growth,
        gold: Gold,
        hp: Hp,
        mp: Mp,
        stamina: Stamina,
        current_spot_id: Optional[SpotId] = None,
        current_coordinate: Optional[Coordinate] = None,
        current_destination: Optional[Coordinate] = None,
        planned_path: List[Coordinate] = None,
        is_down: bool = False,
        active_effects: List[StatusEffect] = None,
    ):
        super().__init__()
        self._player_id = player_id
        self._base_stats = base_stats
        self._stat_growth_factor = stat_growth_factor
        self._exp_table = exp_table
        self._growth = growth
        self._gold = gold
        self._hp = hp
        self._mp = mp
        self._stamina = stamina
        self._current_spot_id = current_spot_id
        self._current_coordinate = current_coordinate
        self._current_destination = current_destination
        self._planned_path = planned_path or []
        self._is_down = is_down
        self._active_effects = active_effects or []

    @property
    def player_id(self) -> PlayerId:
        """プレイヤーID"""
        return self._player_id

    @property
    def base_stats(self) -> BaseStats:
        """基礎ステータス"""
        return self._base_stats

    def get_effective_stats(self, current_tick: WorldTick) -> BaseStats:
        """バフ・デバフ適用後の実効ステータス（期限切れを除外）"""
        # 期限切れエフェクトのクリーンアップ
        self.cleanup_expired_effects(current_tick)
        
        atk_mult = 1.0
        def_mult = 1.0
        spd_mult = 1.0
        
        for effect in self._active_effects:
            if effect.effect_type == StatusEffectType.ATTACK_UP:
                atk_mult *= effect.value
            elif effect.effect_type == StatusEffectType.ATTACK_DOWN:
                atk_mult *= effect.value
            elif effect.effect_type == StatusEffectType.DEFENSE_UP:
                def_mult *= effect.value
            elif effect.effect_type == StatusEffectType.DEFENSE_DOWN:
                def_mult *= effect.value
            elif effect.effect_type == StatusEffectType.SPEED_UP:
                spd_mult *= effect.value
            elif effect.effect_type == StatusEffectType.SPEED_DOWN:
                spd_mult *= effect.value
                
        return BaseStats(
            max_hp=self._base_stats.max_hp,
            max_mp=self._base_stats.max_mp,
            attack=int(self._base_stats.attack * atk_mult),
            defense=int(self._base_stats.defense * def_mult),
            speed=int(self._base_stats.speed * spd_mult),
            critical_rate=self._base_stats.critical_rate,
            evasion_rate=self._base_stats.evasion_rate,
        )

    @property
    def stat_growth_factor(self) -> StatGrowthFactor:
        """ステータス成長率"""
        return self._stat_growth_factor

    @property
    def exp_table(self) -> ExpTable:
        """経験値テーブル"""
        return self._exp_table

    @property
    def growth(self) -> Growth:
        """レベルと経験値"""
        return self._growth

    @property
    def gold(self) -> Gold:
        """ゴールド"""
        return self._gold

    @property
    def hp(self) -> Hp:
        """HP"""
        return self._hp

    @property
    def mp(self) -> Mp:
        """MP"""
        return self._mp

    @property
    def stamina(self) -> Stamina:
        """スタミナ"""
        return self._stamina

    @property
    def is_down(self) -> bool:
        """戦闘不能状態かどうか"""
        return self._is_down

    @property
    def current_spot_id(self) -> Optional[SpotId]:
        """現在のスポットID"""
        return self._current_spot_id

    @property
    def current_coordinate(self) -> Optional[Coordinate]:
        """現在の座標"""
        return self._current_coordinate

    @property
    def current_destination(self) -> Optional[Coordinate]:
        """現在の目的地座標（同じスポット内）"""
        return self._current_destination

    @property
    def planned_path(self) -> List[Coordinate]:
        """計画された経路"""
        return self._planned_path.copy()

    def set_destination(self, destination: Coordinate, path: List[Coordinate]) -> None:
        """目的地と経路を設定する"""
        self._current_destination = destination
        self._planned_path = path

    def clear_path(self) -> None:
        """経路をクリアする"""
        self._planned_path = []
        self._current_destination = None

    def advance_path(self) -> Optional[Coordinate]:
        """経路を1ステップ進める。次に進むべき座標を返し、経路から削除する。"""
        if not self._planned_path:
            return None
        
        # [0] は現在地のはずなので、[1] を返す
        if len(self._planned_path) < 2:
            self.clear_path()
            return None
            
        next_coord = self._planned_path.pop(1)
        if len(self._planned_path) <= 1:
            self.clear_path()
            
        return next_coord

    def update_location(self, spot_id: SpotId, coordinate: Coordinate) -> None:
        """現在地を更新する"""
        if self._current_spot_id == spot_id and self._current_coordinate == coordinate:
            return

        old_spot_id = self._current_spot_id
        old_coordinate = self._current_coordinate
        self._current_spot_id = spot_id
        self._current_coordinate = coordinate

        self.add_event(PlayerLocationChangedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerStatusAggregate",
            old_spot_id=old_spot_id,
            old_coordinate=old_coordinate,
            new_spot_id=spot_id,
            new_coordinate=coordinate,
        ))

    def can_act(self) -> bool:
        """戦闘行動が可能かどうか

        Returns:
            bool: 戦闘行動が可能ならTrue
        """
        return not self._is_down

    def can_receive_healing(self) -> bool:
        """回復を受けられる状態かどうか

        Returns:
            bool: 回復を受けられるならTrue
        """
        return not self._is_down

    def can_consume_resources(self) -> bool:
        """リソースを消費できる状態かどうか

        Returns:
            bool: リソース消費が可能ならTrue
        """
        return not self._is_down

    def apply_damage(self, damage: int) -> None:
        """計算済みのダメージを適用する

        Args:
            damage: ダメージ量
        """
        self._hp = self._hp.damage(damage)

        # HPが0になった場合は戦闘不能状態にする
        if not self._hp.is_alive():
            self._is_down = True
            self.add_event(PlayerDownedEvent.create(
                aggregate_id=self._player_id,
                aggregate_type="PlayerStatusAggregate",
            ))

    def record_evasion(self) -> None:
        """回避を記録する（行動可能状態のみ）"""
        if self._is_down:
            raise PlayerDownedException("ダウン状態のプレイヤーは回避を記録できません")

        self.add_event(PlayerEvadedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerStatusAggregate",
            current_hp=self._hp.value,
        ))

    def gain_exp(self, exp_amount: int) -> None:
        """経験値を獲得する

        Args:
            exp_amount: 獲得経験値量

        Raises:
            PlayerDownedException: ダウン状態の場合
        """
        if self._is_down:
            raise PlayerDownedException("ダウン状態のプレイヤーは経験値を獲得できません")

        old_level = self._growth.level
        new_growth, leveled_up = self._growth.gain_exp(exp_amount)
        self._growth = new_growth

        if leveled_up:
            # レベルアップ時のステータス成長
            growth_factor = StatGrowthFactor.for_level(self._growth.level)
            stat_growth = self._base_stats.grow(growth_factor)
            old_base_stats = self._base_stats
            self._base_stats = stat_growth

            # HP/MPの上限を新しいBaseStatsに合わせて更新
            if self._base_stats.max_hp != old_base_stats.max_hp:
                self._hp = Hp.create(self._hp.value, self._base_stats.max_hp)
            if self._base_stats.max_mp != old_base_stats.max_mp:
                self._mp = Mp.create(self._mp.value, self._base_stats.max_mp)

            self.add_event(PlayerLevelUpEvent.create(
                aggregate_id=self._player_id,
                aggregate_type="PlayerStatusAggregate",
                old_level=old_level,
                new_level=self._growth.level,
                stat_growth=stat_growth,
            ))

    def heal_hp(self, amount: int) -> None:
        """HPを回復する

        Args:
            amount: 回復量
        """
        if not self.can_receive_healing():
            return

        old_hp = self._hp.value
        self._hp = self._hp.heal(amount)

        self.add_event(PlayerHpHealedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerStatusAggregate",
            healed_amount=self._hp.value - old_hp,
            total_hp=self._hp.value,
        ))

    def use_mp(self, amount: int) -> None:
        """MPを消費する

        Args:
            amount: 消費量

        Raises:
            PlayerDownedException: ダウン状態の場合
            InsufficientMpException: MPが不足している場合
        """
        if self._is_down:
            raise PlayerDownedException("ダウン状態のプレイヤーはMPを消費できません")

        if not self._mp.can_consume(amount):
            raise InsufficientMpException(f"MPが不足しています。必要: {amount}, 現在: {self._mp.value}")

        old_mp = self._mp.value
        self._mp = self._mp.consume(amount)

        self.add_event(PlayerMpConsumedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerStatusAggregate",
            consumed_amount=amount,
            remaining_mp=self._mp.value,
        ))

    def heal_mp(self, amount: int) -> None:
        """MPを回復する

        Args:
            amount: 回復量
        """
        old_mp = self._mp.value
        self._mp = self._mp.heal(amount)

        self.add_event(PlayerMpHealedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerStatusAggregate",
            healed_amount=self._mp.value - old_mp,
            total_mp=self._mp.value,
        ))

    def earn_gold(self, amount: int) -> None:
        """ゴールドを獲得する

        Args:
            amount: 獲得量
        """
        old_gold = self._gold.value
        self._gold = self._gold.add(amount)

        self.add_event(PlayerGoldEarnedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerStatusAggregate",
            earned_amount=amount,
            total_gold=self._gold.value,
        ))

    def pay_gold(self, amount: int) -> None:
        """ゴールドを支払う

        Args:
            amount: 支払量

        Raises:
            PlayerDownedException: ダウン状態の場合
            InsufficientGoldException: ゴールドが不足している場合
        """
        if self._is_down:
            raise PlayerDownedException("ダウン状態のプレイヤーはゴールドを支払えません")

        if not self._gold.can_subtract(amount):
            raise InsufficientGoldException(f"ゴールドが不足しています。必要: {amount}, 現在: {self._gold.value}")

        old_gold = self._gold.value
        self._gold = self._gold.subtract(amount)

        self.add_event(PlayerGoldPaidEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerStatusAggregate",
            paid_amount=amount,
            total_gold=self._gold.value,
        ))

    def consume_stamina(self, amount: int) -> None:
        """スタミナを消費する

        Args:
            amount: 消費量

        Raises:
            PlayerDownedException: ダウン状態の場合
            InsufficientStaminaException: スタミナが不足している場合
        """
        if self._is_down:
            raise PlayerDownedException("ダウン状態のプレイヤーはスタミナを消費できません")

        if not self._stamina.can_consume(amount):
            raise InsufficientStaminaException(f"スタミナが不足しています。必要: {amount}, 現在: {self._stamina.value}")

        old_stamina = self._stamina.value
        self._stamina = self._stamina.consume(amount)

        self.add_event(PlayerStaminaConsumedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerStatusAggregate",
            consumed_amount=amount,
            remaining_stamina=self._stamina.value,
        ))

    def validate_resource_consumption(
        self,
        mp_cost: int = 0,
        stamina_cost: int = 0,
        hp_cost: int = 0
    ) -> None:
        """リソース消費が可能かバリデーションを行う

        Args:
            mp_cost: MP消費量
            stamina_cost: スタミナ消費量
            hp_cost: HP消費量（現在のHPを超えてはならない）

        Raises:
            PlayerDownedException: ダウン状態の場合
            InsufficientMpException: MP不足
            InsufficientStaminaException: スタミナ不足
            InsufficientHpException: HP不足
        """
        if self._is_down:
            raise PlayerDownedException("ダウン状態のプレイヤーはリソースを消費できません")

        if mp_cost > 0 and not self._mp.can_consume(mp_cost):
            raise InsufficientMpException(f"MPが不足しています。必要: {mp_cost}, 現在: {self._mp.value}")

        if stamina_cost > 0 and not self._stamina.can_consume(stamina_cost):
            raise InsufficientStaminaException(f"スタミナが不足しています。必要: {stamina_cost}, 現在: {self._stamina.value}")

        if hp_cost > 0 and hp_cost >= self._hp.value:
            raise InsufficientHpException(f"HPが不足しています。必要: {hp_cost}, 現在: {self._hp.value}")

    def consume_resources(
        self,
        mp_cost: int = 0,
        stamina_cost: int = 0,
        hp_cost: int = 0
    ) -> None:
        """リソースを一括で消費する

        Args:
            mp_cost: MP消費量
            stamina_cost: スタミナ消費量
            hp_cost: HP消費量

        Raises:
            PlayerDownedException: ダウン状態の場合
            InsufficientMpException: MP不足
            InsufficientStaminaException: スタミナ不足
            InsufficientHpException: HP不足
        """
        # バリデーション
        self.validate_resource_consumption(mp_cost, stamina_cost, hp_cost)

        # 消費
        if mp_cost > 0:
            self.use_mp(mp_cost)
        if stamina_cost > 0:
            self.consume_stamina(stamina_cost)
        if hp_cost > 0:
            self.apply_damage(hp_cost)

    def heal_stamina(self, amount: int) -> None:
        """スタミナを回復する

        Args:
            amount: 回復量
        """
        old_stamina = self._stamina.value
        self._stamina = self._stamina.recover(amount)

        self.add_event(PlayerStaminaHealedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerStatusAggregate",
            healed_amount=self._stamina.value - old_stamina,
            total_stamina=self._stamina.value,
        ))

    def revive(self, config: PlayerConfigService = DefaultPlayerConfigService()) -> None:
        """戦闘不能状態から復帰する

        Args:
            config: プレイヤー設定サービス

        Raises:
            ValueError: 既にダウン状態でない場合
        """
        if not self._is_down:
            raise ValueError("プレイヤーは戦闘不能状態ではありません")

        # HPを設定された率に応じて回復
        hp_recovery_percent = config.get_revive_hp_rate()
        recovery_hp = int(self._base_stats.max_hp * hp_recovery_percent)
        old_hp = self._hp.value
        self._hp = Hp.create(recovery_hp, self._base_stats.max_hp)

        # ダウン状態を解除
        self._is_down = False

        self.add_event(PlayerRevivedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerStatusAggregate",
            hp_recovered=self._hp.value - old_hp,
            total_hp=self._hp.value,
        ))

    def add_status_effect(self, effect: StatusEffect) -> None:
        """ステータス効果を追加する"""
        self._active_effects.append(effect)

    def cleanup_expired_effects(self, current_tick: WorldTick) -> None:
        """期限切れのステータス効果を削除する"""
        self._active_effects = [e for e in self._active_effects if not e.is_expired(current_tick)]
