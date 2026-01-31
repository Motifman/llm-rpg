from typing import Optional

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
from ai_rpg_world.domain.player.event.status_events import (
    PlayerDownedEvent,
    PlayerRevivedEvent,
    PlayerLevelUpEvent,
    PlayerHpHealedEvent,
    PlayerMpConsumedEvent,
    PlayerMpHealedEvent,
    PlayerStaminaConsumedEvent,
    PlayerStaminaHealedEvent,
    PlayerGoldEarnedEvent,
    PlayerGoldPaidEvent,
)
from ai_rpg_world.domain.player.exception import (
    InsufficientMpException,
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
        is_down: bool = False,
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
        self._is_down = is_down

    @property
    def player_id(self) -> PlayerId:
        """プレイヤーID"""
        return self._player_id

    @property
    def base_stats(self) -> BaseStats:
        """基礎ステータス"""
        return self._base_stats

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
        return True

    def can_consume_resources(self) -> bool:
        """リソースを消費できる状態かどうか

        Returns:
            bool: リソース消費が可能ならTrue
        """
        return not self._is_down

    def take_damage(self, damage: int) -> None:
        """ダメージを受ける

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
            ValueError: スタミナが不足している場合
        """
        if self._is_down:
            raise PlayerDownedException("ダウン状態のプレイヤーはスタミナを消費できません")

        if not self._stamina.can_consume(amount):
            raise ValueError(f"スタミナが不足しています。必要: {amount}, 現在: {self._stamina.value}")

        old_stamina = self._stamina.value
        self._stamina = self._stamina.consume(amount)

        self.add_event(PlayerStaminaConsumedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerStatusAggregate",
            consumed_amount=amount,
            remaining_stamina=self._stamina.value,
        ))

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

    def revive(self, hp_recovery_percent: float) -> None:
        """戦闘不能状態から復帰する

        Args:
            hp_recovery_percent: HP回復率（0.0〜1.0）

        Raises:
            ValueError: 既にダウン状態でない場合
        """
        if not self._is_down:
            raise ValueError("プレイヤーは戦闘不能状態ではありません")

        # HPを回復率に応じて回復
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

