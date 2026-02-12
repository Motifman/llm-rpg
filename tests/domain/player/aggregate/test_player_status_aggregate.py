import pytest
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
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
)
from ai_rpg_world.domain.player.exception import (
    InsufficientMpException,
    InsufficientStaminaException,
    InsufficientHpException,
    InsufficientGoldException,
    PlayerDownedException
)
from ai_rpg_world.domain.combat.service.combat_logic_service import CombatLogicService


# テスト用のヘルパー関数
def create_test_base_stats(
    max_hp: int = 100,
    max_mp: int = 50,
    attack: int = 20,
    defense: int = 15,
    speed: int = 10,
    critical_rate: float = 0.05,
    evasion_rate: float = 0.03
) -> BaseStats:
    """テスト用のBaseStatsを作成"""
    return BaseStats(
        max_hp=max_hp,
        max_mp=max_mp,
        attack=attack,
        defense=defense,
        speed=speed,
        critical_rate=critical_rate,
        evasion_rate=evasion_rate
    )


def create_test_stat_growth_factor(
    hp_factor: float = 0.1,
    mp_factor: float = 0.1,
    attack_factor: float = 0.1,
    defense_factor: float = 0.1,
    speed_factor: float = 0.1,
    critical_rate_factor: float = 0.01,
    evasion_rate_factor: float = 0.01
) -> StatGrowthFactor:
    """テスト用のStatGrowthFactorを作成"""
    return StatGrowthFactor(
        hp_factor=hp_factor,
        mp_factor=mp_factor,
        attack_factor=attack_factor,
        defense_factor=defense_factor,
        speed_factor=speed_factor,
        critical_rate_factor=critical_rate_factor,
        evasion_rate_factor=evasion_rate_factor
    )


def create_test_exp_table() -> ExpTable:
    """テスト用のExpTableを作成"""
    # base_exp=50, exponent=1.5, level_offset=0.0
    # これによりレベル2: 50*(1^1.5)=50, レベル3: 50*(2^1.5)=50*2.828=141, レベル4: 50*(3^1.5)=50*5.196=259, レベル5: 50*(4^1.5)=50*8=400
    return ExpTable(base_exp=50.0, exponent=1.5, level_offset=0.0)


def create_test_growth(level: int = 1, total_exp: int = 0) -> Growth:
    """テスト用のGrowthを作成"""
    exp_table = create_test_exp_table()
    return Growth(level=level, total_exp=total_exp, exp_table=exp_table)


def create_test_status_aggregate(
    player_id: int = 1,
    base_stats: BaseStats = None,
    stat_growth_factor: StatGrowthFactor = None,
    growth: Growth = None,
    gold: int = 100,
    hp: int = 100,
    mp: int = 50,
    stamina: int = 100,
    is_down: bool = False
) -> PlayerStatusAggregate:
    """テスト用のPlayerStatusAggregateを作成"""
    if base_stats is None:
        base_stats = create_test_base_stats()
    if stat_growth_factor is None:
        stat_growth_factor = create_test_stat_growth_factor()
    if growth is None:
        growth = create_test_growth()

    exp_table = create_test_exp_table()

    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=base_stats,
        stat_growth_factor=stat_growth_factor,
        exp_table=exp_table,
        growth=growth,
        gold=Gold.create(gold),
        hp=Hp.create(hp, base_stats.max_hp),
        mp=Mp.create(mp, base_stats.max_mp),
        stamina=Stamina.create(stamina, stamina),  # max_stamina = stamina
        is_down=is_down
    )


class TestPlayerStatusAggregate:
    """PlayerStatusAggregateのテスト"""

    def test_create_status_aggregate(self):
        """ステータス集約が正しく作成されること"""
        aggregate = create_test_status_aggregate()

        assert aggregate.player_id.value == 1
        assert aggregate.base_stats.max_hp == 100
        assert aggregate.base_stats.max_mp == 50
        assert aggregate.gold.value == 100
        assert aggregate.hp.value == 100
        assert aggregate.hp.max_hp == 100
        assert aggregate.mp.value == 50
        assert aggregate.mp.max_mp == 50
        assert aggregate.stamina.value == 100
        assert aggregate.stamina.max_stamina == 100
        assert aggregate.growth.level == 1
        assert aggregate.growth.total_exp == 0
        assert aggregate.is_down == False

    def test_apply_damage_normal(self):
        """ダメージを受け、HPが減少すること"""
        aggregate = create_test_status_aggregate(hp=100)
        initial_hp = aggregate.hp.value

        aggregate.apply_damage(30)

        assert aggregate.hp.value == initial_hp - 30
        assert aggregate.is_down == False

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 0  # HPが残っているので戦闘不能イベントは発行されない

    def test_apply_damage_down(self):
        """ダメージでHPが0になり、戦闘不能になること"""
        aggregate = create_test_status_aggregate(hp=50)

        aggregate.apply_damage(50)

        assert aggregate.hp.value == 0
        assert aggregate.is_down == True

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], PlayerDownedEvent)
        assert events[0].aggregate_id == aggregate.player_id

    def test_apply_damage_over_kill(self):
        """ダメージがHPを超える場合、HPが0になること"""
        aggregate = create_test_status_aggregate(hp=30)

        aggregate.apply_damage(100)

        assert aggregate.hp.value == 0
        assert aggregate.is_down == True

    def test_application_style_damage_flow_success(self):
        """アプリケーション層経由で計算したダメージが適用されること"""
        aggregate = create_test_status_aggregate(hp=100)
        attacker_stats = create_test_base_stats(
            attack=40,
            defense=10,
            critical_rate=0.0,
            evasion_rate=0.0,
        )

        damage = CombatLogicService.calculate_damage(
            attacker_stats=attacker_stats,
            defender_stats=aggregate.base_stats,
        )
        if damage.is_evaded:
            aggregate.record_evasion()
        else:
            aggregate.apply_damage(damage.value)

        # Damage = (40 - 15/2) = 32.5 -> int(32)
        assert aggregate.hp.value == 68
        assert aggregate.is_down == False
        assert len(aggregate.get_events()) == 0

    def test_application_style_damage_flow_evaded(self):
        """アプリケーション層経由で回避時にPlayerEvadedEventが発行されること"""
        aggregate = create_test_status_aggregate(hp=80)
        attacker_stats = create_test_base_stats(
            attack=40,
            defense=10,
            critical_rate=0.0,
            evasion_rate=0.0,
        )
        # テストの決定性を担保するため、防御側の回避率を100%にする
        defender_stats = create_test_base_stats(
            attack=aggregate.base_stats.attack,
            defense=aggregate.base_stats.defense,
            critical_rate=aggregate.base_stats.critical_rate,
            evasion_rate=1.0,
        )

        damage = CombatLogicService.calculate_damage(
            attacker_stats=attacker_stats,
            defender_stats=defender_stats,
        )
        if damage.is_evaded:
            aggregate.record_evasion()
        else:
            aggregate.apply_damage(damage.value)

        assert aggregate.hp.value == 80
        events = aggregate.get_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, PlayerEvadedEvent)
        assert event.aggregate_id == aggregate.player_id
        assert event.aggregate_type == "PlayerStatusAggregate"
        assert event.current_hp == 80

    def test_record_evasion_success(self):
        """回避記録時にイベントが発行されること"""
        aggregate = create_test_status_aggregate(hp=80, is_down=False)

        aggregate.record_evasion()

        events = aggregate.get_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, PlayerEvadedEvent)
        assert event.aggregate_id == aggregate.player_id
        assert event.aggregate_type == "PlayerStatusAggregate"
        assert event.current_hp == 80
        assert hasattr(event, "event_id")
        assert hasattr(event, "occurred_at")

    def test_record_evasion_when_downed_raises_exception(self):
        """ダウン状態では回避記録できないこと"""
        aggregate = create_test_status_aggregate(is_down=True)

        with pytest.raises(PlayerDownedException, match="ダウン状態のプレイヤーは回避を記録できません"):
            aggregate.record_evasion()

    def test_gain_exp_level_up(self):
        """経験値を獲得し、レベルアップすること"""
        aggregate = create_test_status_aggregate()
        initial_level = aggregate.growth.level
        initial_stats = aggregate.base_stats

        aggregate.gain_exp(60)  # レベル2に到達する経験値

        assert aggregate.growth.level == initial_level + 1
        assert aggregate.growth.total_exp == 60

        # BaseStatsが成長していることを確認
        assert aggregate.base_stats.max_hp > initial_stats.max_hp
        assert aggregate.base_stats.max_mp > initial_stats.max_mp

        # HP/MPの上限が更新されていることを確認
        assert aggregate.hp.max_hp == aggregate.base_stats.max_hp
        assert aggregate.mp.max_mp == aggregate.base_stats.max_mp

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], PlayerLevelUpEvent)
        assert events[0].old_level == initial_level
        assert events[0].new_level == initial_level + 1

    def test_gain_exp_no_level_up(self):
        """経験値を獲得してもレベルアップしない場合"""
        aggregate = create_test_status_aggregate()
        initial_level = aggregate.growth.level

        aggregate.gain_exp(49)  # レベルアップしない経験値

        assert aggregate.growth.level == initial_level
        assert aggregate.growth.total_exp == 49

        # イベントが発行されていないことを確認
        events = aggregate.get_events()
        assert len(events) == 0

    def test_gain_exp_when_downed(self):
        """ダウン状態で経験値を獲得しようとすると例外が発生すること"""
        aggregate = create_test_status_aggregate(is_down=True)

        with pytest.raises(PlayerDownedException, match="ダウン状態のプレイヤーは経験値を獲得できません"):
            aggregate.gain_exp(50)

    def test_heal_hp(self):
        """HPを回復すること"""
        aggregate = create_test_status_aggregate(hp=50)

        aggregate.heal_hp(30)

        assert aggregate.hp.value == 80

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], PlayerHpHealedEvent)
        assert events[0].healed_amount == 30
        assert events[0].total_hp == 80

    def test_heal_hp_over_max(self):
        """HP回復が最大値を超える場合、最大値になること"""
        aggregate = create_test_status_aggregate(hp=90)

        aggregate.heal_hp(20)  # 110になるが、最大値は100

        assert aggregate.hp.value == 100

    def test_use_mp_normal(self):
        """MPを消費すること"""
        aggregate = create_test_status_aggregate(mp=50)

        aggregate.use_mp(20)

        assert aggregate.mp.value == 30

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], PlayerMpConsumedEvent)
        assert events[0].consumed_amount == 20
        assert events[0].remaining_mp == 30

    def test_use_mp_insufficient(self):
        """MPが不足している場合、例外が発生すること"""
        aggregate = create_test_status_aggregate(mp=10)

        with pytest.raises(InsufficientMpException):
            aggregate.use_mp(20)

        # MPが消費されていないことを確認
        assert aggregate.mp.value == 10

    def test_use_mp_when_downed(self):
        """ダウン状態でMPを消費しようとすると例外が発生すること"""
        aggregate = create_test_status_aggregate(is_down=True)

        with pytest.raises(PlayerDownedException, match="ダウン状態のプレイヤーはMPを消費できません"):
            aggregate.use_mp(20)

    def test_heal_mp(self):
        """MPを回復すること"""
        aggregate = create_test_status_aggregate(mp=20)

        aggregate.heal_mp(15)

        assert aggregate.mp.value == 35

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], PlayerMpHealedEvent)
        assert events[0].healed_amount == 15
        assert events[0].total_mp == 35

    def test_heal_mp_over_max(self):
        """MP回復が最大値を超える場合、最大値になること"""
        aggregate = create_test_status_aggregate(mp=45)

        aggregate.heal_mp(10)  # 55になるが、最大値は50

        assert aggregate.mp.value == 50

    def test_consume_stamina_normal(self):
        """スタミナを消費すること"""
        aggregate = create_test_status_aggregate(stamina=100)

        aggregate.consume_stamina(20)

        assert aggregate.stamina.value == 80

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], PlayerStaminaConsumedEvent)
        assert events[0].consumed_amount == 20
        assert events[0].remaining_stamina == 80

    def test_consume_stamina_insufficient(self):
        """スタミナが不足している場合、例外が発生すること"""
        aggregate = create_test_status_aggregate(stamina=10)

        with pytest.raises(InsufficientStaminaException, match="スタミナが不足しています"):
            aggregate.consume_stamina(20)

        # スタミナが消費されていないことを確認
        assert aggregate.stamina.value == 10

    def test_consume_stamina_when_downed(self):
        """ダウン状態でスタミナを消費しようとすると例外が発生すること"""
        aggregate = create_test_status_aggregate(is_down=True)

        with pytest.raises(PlayerDownedException, match="ダウン状態のプレイヤーはスタミナを消費できません"):
            aggregate.consume_stamina(20)

    def test_heal_stamina(self):
        """スタミナを回復すること"""
        aggregate = create_test_status_aggregate()
        # スタミナを50/100に設定
        aggregate._stamina = Stamina.create(50, 100)

        aggregate.heal_stamina(25)

        assert aggregate.stamina.value == 75

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], PlayerStaminaHealedEvent)
        assert events[0].healed_amount == 25
        assert events[0].total_stamina == 75

    def test_heal_stamina_over_max(self):
        """スタミナ回復が最大値を超える場合、最大値になること"""
        aggregate = create_test_status_aggregate()
        # スタミナを90/100に設定
        aggregate._stamina = Stamina.create(90, 100)

        aggregate.heal_stamina(20)  # 110になるが、最大値は100

        assert aggregate.stamina.value == 100

    def test_revive_normal(self):
        """戦闘不能状態から復帰すること"""
        aggregate = create_test_status_aggregate(hp=0, is_down=True)

        aggregate.revive()  # デフォルト設定(10%)で復帰

        assert aggregate.hp.value == 10  # max_hp(100) * 0.1
        assert aggregate.is_down == False

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], PlayerRevivedEvent)
        assert events[0].hp_recovered == 10
        assert events[0].total_hp == 10

    def test_revive_custom_config(self):
        """カスタム設定で復帰すること"""
        from ai_rpg_world.domain.player.service.player_config_service import DefaultPlayerConfigService
        aggregate = create_test_status_aggregate(hp=0, is_down=True)
        config = DefaultPlayerConfigService(revive_hp_rate=0.5)

        aggregate.revive(config=config)

        assert aggregate.hp.value == 50
        assert aggregate.is_down == False

    def test_downed_transition_flow(self):
        """ダウン -> 回復不可 -> 蘇生 -> 回復可能 の遷移テスト"""
        aggregate = create_test_status_aggregate(hp=100)
        
        # 1. ダウン状態にする
        aggregate.apply_damage(100)
        assert aggregate.is_down is True
        assert aggregate.can_receive_healing() is False
        
        # 2. ダウン中の回復試行（回復しないはず）
        aggregate.clear_events()
        aggregate.heal_hp(50)
        assert aggregate.hp.value == 0
        assert len(aggregate.get_events()) == 0
        
        # 3. 蘇生
        aggregate.revive()
        assert aggregate.is_down is False
        assert aggregate.hp.value == 10
        assert aggregate.can_receive_healing() is True
        
        # 4. 蘇生後の回復
        aggregate.clear_events()
        aggregate.heal_hp(50)
        assert aggregate.hp.value == 60
        assert len(aggregate.get_events()) == 1
        assert isinstance(aggregate.get_events()[0], PlayerHpHealedEvent)

    def test_revive_not_down(self):
        """戦闘不能状態でない場合、例外が発生すること"""
        aggregate = create_test_status_aggregate(is_down=False)

        with pytest.raises(ValueError, match="プレイヤーは戦闘不能状態ではありません"):
            aggregate.revive(0.5)

    def test_earn_gold(self):
        """ゴールドを獲得すること"""
        aggregate = create_test_status_aggregate(gold=100)

        aggregate.earn_gold(50)

        assert aggregate.gold.value == 150

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], PlayerGoldEarnedEvent)
        assert events[0].earned_amount == 50
        assert events[0].total_gold == 150

    def test_pay_gold_normal(self):
        """ゴールドを支払うこと"""
        aggregate = create_test_status_aggregate(gold=100)

        aggregate.pay_gold(30)

        assert aggregate.gold.value == 70

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], PlayerGoldPaidEvent)
        assert events[0].paid_amount == 30
        assert events[0].total_gold == 70

    def test_pay_gold_insufficient(self):
        """ゴールドが不足している場合、例外が発生すること"""
        aggregate = create_test_status_aggregate(gold=20)

        with pytest.raises(InsufficientGoldException):
            aggregate.pay_gold(50)

        # ゴールドが支払われていないことを確認
        assert aggregate.gold.value == 20

    def test_pay_gold_when_downed(self):
        """ダウン状態でゴールドを支払おうとすると例外が発生すること"""
        aggregate = create_test_status_aggregate(is_down=True, gold=100)

        with pytest.raises(PlayerDownedException, match="ダウン状態のプレイヤーはゴールドを支払えません"):
            aggregate.pay_gold(30)

    def test_can_act_methods(self):
        """状態チェックメソッドが正しく動作すること"""
        # 正常状態
        aggregate = create_test_status_aggregate()
        assert aggregate.can_act() == True
        assert aggregate.can_receive_healing() == True
        assert aggregate.can_consume_resources() == True

        # 戦闘不能状態（ダウン状態）
        aggregate = create_test_status_aggregate(is_down=True)
        assert aggregate.can_act() == False
        assert aggregate.can_receive_healing() == False
        assert aggregate.can_consume_resources() == False

    def test_location_updates(self):
        """位置情報と経路情報の更新テスト"""
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
        from ai_rpg_world.domain.player.event.status_events import PlayerLocationChangedEvent

        aggregate = create_test_status_aggregate()
        spot1 = SpotId(1)
        coord1 = Coordinate(0, 0, 0)
        
        # 1. 位置の更新
        aggregate.update_location(spot1, coord1)
        assert aggregate.current_spot_id == spot1
        assert aggregate.current_coordinate == coord1
        
        events = aggregate.get_events()
        assert any(isinstance(e, PlayerLocationChangedEvent) for e in events)
        
        # 2. 経路の設定
        dest = Coordinate(5, 5, 0)
        path = [coord1, Coordinate(1, 0, 0), dest]
        aggregate.set_destination(dest, path)
        
        assert aggregate.current_destination == dest
        assert aggregate.planned_path == path
        
        # 3. 経路を1ステップ進める
        next_coord = aggregate.advance_path()
        assert next_coord == Coordinate(1, 0, 0)
        # 現在地（[0]）と進んだ先（[1]）が残る
        assert len(aggregate.planned_path) == 2
        
        # 4. 経路のクリア
        aggregate.clear_path()
        assert aggregate.current_destination is None
        assert aggregate.planned_path == []

    def test_advance_path_exhaustion(self):
        """経路を最後まで進めた時の挙動"""
        from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
        aggregate = create_test_status_aggregate()
        
        path = [Coordinate(0, 0), Coordinate(0, 1)]
        aggregate.set_destination(Coordinate(0, 1), path)
        
        next_coord = aggregate.advance_path()
        assert next_coord == Coordinate(0, 1)
        # 残り1要素以下になったらクリアされる仕様
        assert aggregate.planned_path == []
        assert aggregate.current_destination is None

    def test_consume_resources_zero_costs(self):
        """ゼロコストでの消費が正常に終了すること"""
        aggregate = create_test_status_aggregate(hp=100, mp=50, stamina=100)
        aggregate.clear_events()
        
        # 何も消費しない
        aggregate.consume_resources(mp_cost=0, stamina_cost=0, hp_cost=0)
        
        assert aggregate.hp.value == 100
        assert aggregate.mp.value == 50
        assert aggregate.stamina.value == 100
        assert len(aggregate.get_events()) == 0

    def test_consume_resources_all_success(self):
        """全リソースを正常に消費できること"""
        aggregate = create_test_status_aggregate(hp=100, mp=50, stamina=100)
        aggregate.clear_events()
        
        aggregate.consume_resources(mp_cost=10, stamina_cost=20, hp_cost=30)
        
        assert aggregate.hp.value == 70
        assert aggregate.mp.value == 40
        assert aggregate.stamina.value == 80
        
        events = aggregate.get_events()
        # HPダメージ（apply_damage）はイベントを発行しない（死亡時のみ）
        # MP消費、スタミナ消費のイベントが発行される
        assert len(events) == 2
        assert any(isinstance(e, PlayerMpConsumedEvent) for e in events)
        assert any(isinstance(e, PlayerStaminaConsumedEvent) for e in events)

    def test_consume_resources_insufficient_mp(self):
        """MP不足時に適切な例外が発生し、リソースが消費されないこと"""
        aggregate = create_test_status_aggregate(hp=100, mp=5, stamina=100)
        
        with pytest.raises(InsufficientMpException, match="MPが不足しています"):
            aggregate.consume_resources(mp_cost=10, stamina_cost=20, hp_cost=30)
            
        # 状態が変わっていないこと
        assert aggregate.hp.value == 100
        assert aggregate.mp.value == 5
        assert aggregate.stamina.value == 100

    def test_consume_resources_insufficient_stamina(self):
        """スタミナ不足時に適切な例外が発生し、リソースが消費されないこと"""
        aggregate = create_test_status_aggregate(hp=100, mp=50, stamina=10)
        
        with pytest.raises(InsufficientStaminaException, match="スタミナが不足しています"):
            aggregate.consume_resources(mp_cost=10, stamina_cost=20, hp_cost=30)
            
        # 状態が変わっていないこと
        assert aggregate.hp.value == 100
        assert aggregate.mp.value == 50
        assert aggregate.stamina.value == 10

    def test_consume_resources_insufficient_hp(self):
        """HP不足（死亡コスト）時に適切な例外が発生し、リソースが消費されないこと"""
        aggregate = create_test_status_aggregate(hp=20, mp=50, stamina=100)
        
        with pytest.raises(InsufficientHpException, match="HPが不足しています"):
            aggregate.consume_resources(mp_cost=10, stamina_cost=20, hp_cost=30)
            
        # 状態が変わっていないこと
        assert aggregate.hp.value == 20
        assert aggregate.mp.value == 50
        assert aggregate.stamina.value == 100

    def test_consume_resources_when_downed(self):
        """ダウン状態での消費試行時に例外が発生すること"""
        aggregate = create_test_status_aggregate(is_down=True)
        
        with pytest.raises(PlayerDownedException, match="ダウン状態のプレイヤーはリソースを消費できません"):
            aggregate.consume_resources(mp_cost=1, stamina_cost=1, hp_cost=1)

    def test_consume_resources_partial_costs(self):
        """一部のリソースのみを指定して消費できること"""
        aggregate = create_test_status_aggregate(hp=100, mp=50, stamina=100)
        
        # MPのみ
        aggregate.consume_resources(mp_cost=10)
        assert aggregate.mp.value == 40
        assert aggregate.hp.value == 100
        assert aggregate.stamina.value == 100
        
        # スタミナのみ
        aggregate.consume_resources(stamina_cost=20)
        assert aggregate.stamina.value == 80
        
        # HPのみ
        aggregate.consume_resources(hp_cost=30)
        assert aggregate.hp.value == 70

    def test_consume_resources_validation_priority(self):
        """バリデーションの優先順位（MP > Stamina > HP）の確認"""
        aggregate = create_test_status_aggregate(hp=5, mp=5, stamina=5)
        
        # MPとスタミナが両方不足している場合、MP不足が優先される
        with pytest.raises(InsufficientMpException):
            aggregate.consume_resources(mp_cost=10, stamina_cost=10)
            
        # スタミナとHPが両方不足している場合、スタミナ不足が優先される
        with pytest.raises(InsufficientStaminaException):
            aggregate.consume_resources(stamina_cost=10, hp_cost=10)

    class TestStatusEffects:
        def test_get_effective_stats_with_multiplicative_buffs(self):
            # Given
            aggregate = create_test_status_aggregate(base_stats=create_test_base_stats(attack=20))
            # 1.5倍バフと1.2倍バフを付与
            from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
            from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
            from ai_rpg_world.domain.common.value_object import WorldTick
            aggregate.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 1.5, WorldTick(100)))
            aggregate.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 1.2, WorldTick(100)))
            
            # When
            effective_stats = aggregate.get_effective_stats(WorldTick(10))
            
            # Then
            # 20 * 1.5 * 1.2 = 36
            assert effective_stats.attack == 36

        def test_get_effective_stats_filters_expired_effects(self):
            # Given
            aggregate = create_test_status_aggregate(base_stats=create_test_base_stats(attack=20))
            # 期限切れ(Tick 5)の 2.0倍バフ
            from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
            from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
            from ai_rpg_world.domain.common.value_object import WorldTick
            aggregate.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 2.0, WorldTick(5)))
            # 有効な 1.5倍バフ
            aggregate.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 1.5, WorldTick(20)))
            
            # When
            effective_stats = aggregate.get_effective_stats(WorldTick(10))
            
            # Then
            # 20 * 1.5 = 30
            assert effective_stats.attack == 30
            assert len(aggregate._active_effects) == 1

        def test_buff_and_debuff_stacking(self):
            # Given
            aggregate = create_test_status_aggregate(base_stats=create_test_base_stats(attack=20))
            # 1.5倍バフと 0.5倍デバフ
            from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
            from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
            from ai_rpg_world.domain.common.value_object import WorldTick
            aggregate.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 1.5, WorldTick(100)))
            aggregate.add_status_effect(StatusEffect(StatusEffectType.ATTACK_DOWN, 0.5, WorldTick(100)))
            
            # When
            effective_stats = aggregate.get_effective_stats(WorldTick(10))
            
            # Then
            # 20 * 1.5 * 0.5 = 15
            assert effective_stats.attack == 15
