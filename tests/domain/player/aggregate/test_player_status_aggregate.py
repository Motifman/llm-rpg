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
    PlayerDownedException,
    SpeechValidationException,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import PursuitFailureReason
from ai_rpg_world.domain.pursuit.event.pursuit_events import (
    PursuitCancelledEvent,
    PursuitFailedEvent,
    PursuitStartedEvent,
    PursuitUpdatedEvent,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import (
    PursuitLastKnownState,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import (
    PursuitTargetSnapshot,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.player.value_object.player_navigation_state import (
    PlayerNavigationState,
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
    is_down: bool = False,
    current_spot_id=None,
    current_coordinate=None,
) -> PlayerStatusAggregate:
    """テスト用のPlayerStatusAggregateを作成"""
    if base_stats is None:
        base_stats = create_test_base_stats()
    if stat_growth_factor is None:
        stat_growth_factor = create_test_stat_growth_factor()
    if growth is None:
        growth = create_test_growth()

    exp_table = create_test_exp_table()

    navigation_state = (
        PlayerNavigationState.from_parts(
            current_spot_id=current_spot_id,
            current_coordinate=current_coordinate,
        )
        if current_spot_id is not None or current_coordinate is not None
        else None
    )

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
        is_down=is_down,
        navigation_state=navigation_state,
    )


def create_test_pursuit_snapshot(
    target_id: int = 99,
    spot_id: int = 1,
    coordinate: Coordinate = None,
) -> PursuitTargetSnapshot:
    """テスト用の追跡対象スナップショットを作成"""
    return PursuitTargetSnapshot(
        target_id=WorldObjectId.create(target_id),
        spot_id=SpotId(spot_id),
        coordinate=coordinate or Coordinate(3, 4, 0),
    )


def create_test_last_known_state(
    target_id: int = 99,
    spot_id: int = 1,
    coordinate: Coordinate = None,
) -> PursuitLastKnownState:
    """テスト用の最後の既知状態を作成"""
    return PursuitLastKnownState(
        target_id=WorldObjectId.create(target_id),
        spot_id=SpotId(spot_id),
        coordinate=coordinate or Coordinate(3, 4, 0),
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
        assert events[0].killer_player_id is None

    def test_apply_damage_down_with_killer_player_id(self):
        """プレイヤーによって倒された場合、PlayerDownedEvent に killer_player_id が記録されること"""
        aggregate = create_test_status_aggregate(hp=50)
        killer_id = PlayerId(2)

        aggregate.apply_damage(50, killer_player_id=killer_id)

        assert aggregate.hp.value == 0
        assert aggregate.is_down is True
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], PlayerDownedEvent)
        assert events[0].aggregate_id == aggregate.player_id
        assert events[0].killer_player_id == killer_id

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
        """戦闘不能状態から復帰すること（回復率を値で渡す）"""
        aggregate = create_test_status_aggregate(hp=0, is_down=True)

        aggregate.revive(hp_recovery_rate=0.1)  # 10%で復帰

        assert aggregate.hp.value == 10  # max_hp(100) * 0.1
        assert aggregate.is_down == False

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], PlayerRevivedEvent)
        assert events[0].hp_recovered == 10
        assert events[0].total_hp == 10

    def test_revive_custom_rate(self):
        """指定した回復率で復帰すること"""
        aggregate = create_test_status_aggregate(hp=0, is_down=True)

        aggregate.revive(hp_recovery_rate=0.5)

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
        
        # 3. 蘇生（回復率を値で渡す）
        aggregate.revive(hp_recovery_rate=0.1)
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
            aggregate.revive(hp_recovery_rate=0.5)

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

    def test_start_pursuit_stores_separate_state_and_emits_started_event(self):
        """追跡開始が静的移動とは別状態で保持され、開始イベントを発行すること"""
        aggregate = create_test_status_aggregate()
        snapshot = create_test_pursuit_snapshot()

        aggregate.start_pursuit(snapshot)

        assert aggregate.has_active_pursuit is True
        assert aggregate.pursuit_state is not None
        assert aggregate.pursuit_state.target_id == snapshot.target_id
        assert aggregate.pursuit_state.target_snapshot == snapshot
        assert aggregate.current_destination is None
        assert aggregate.planned_path == []

        events = aggregate.get_events()
        started = next(e for e in events if isinstance(e, PursuitStartedEvent))
        assert started.actor_id == WorldObjectId.create(aggregate.player_id.value)
        assert started.target_id == snapshot.target_id
        assert started.target_snapshot == snapshot
        assert started.last_known.coordinate == snapshot.coordinate

    def test_update_pursuit_emits_only_for_meaningful_changes(self):
        """追跡更新は対象状態の変化があったときだけイベントを発行すること"""
        aggregate = create_test_status_aggregate()
        snapshot = create_test_pursuit_snapshot()
        aggregate.start_pursuit(snapshot)
        aggregate.clear_events()

        assert aggregate.update_pursuit(target_snapshot=snapshot) is False
        assert aggregate.get_events() == []

        new_snapshot = create_test_pursuit_snapshot(coordinate=Coordinate(4, 4, 0))
        new_last_known = create_test_last_known_state(coordinate=Coordinate(4, 4, 0))

        assert aggregate.update_pursuit(target_snapshot=new_snapshot, last_known=new_last_known) is True
        assert aggregate.pursuit_state.target_snapshot == new_snapshot
        assert aggregate.pursuit_state.last_known == new_last_known

        events = aggregate.get_events()
        updated = next(e for e in events if isinstance(e, PursuitUpdatedEvent))
        assert updated.target_snapshot == new_snapshot
        assert updated.last_known == new_last_known

    def test_update_pursuit_is_noop_when_snapshot_and_last_known_are_unchanged(self):
        """追跡継続が同じ snapshot/last_known を渡しても更新イベントを出さないこと"""
        aggregate = create_test_status_aggregate()
        snapshot = create_test_pursuit_snapshot()
        aggregate.start_pursuit(snapshot)
        aggregate.clear_events()

        unchanged_last_known = create_test_last_known_state(coordinate=snapshot.coordinate)

        assert (
            aggregate.update_pursuit(
                target_snapshot=snapshot,
                last_known=unchanged_last_known,
            )
            is False
        )
        assert aggregate.get_events() == []

    def test_fail_pursuit_clears_only_pursuit_state_and_emits_failed_event(self):
        """追跡失敗は追跡だけを終了し、静的移動状態は維持すること"""
        aggregate = create_test_status_aggregate(current_spot_id=SpotId(1), current_coordinate=Coordinate(0, 0, 0))
        path = [Coordinate(0, 0, 0), Coordinate(1, 0, 0), Coordinate(2, 0, 0)]
        aggregate.set_destination(Coordinate(2, 0, 0), path)
        aggregate.start_pursuit(create_test_pursuit_snapshot())
        aggregate.clear_events()

        aggregate.fail_pursuit(PursuitFailureReason.PATH_UNREACHABLE)

        assert aggregate.pursuit_state is None
        assert aggregate.current_destination == Coordinate(2, 0, 0)
        assert aggregate.planned_path == path

        events = aggregate.get_events()
        failed = next(e for e in events if isinstance(e, PursuitFailedEvent))
        assert failed.failure_reason == PursuitFailureReason.PATH_UNREACHABLE
        assert failed.target_id == WorldObjectId.create(99)

    def test_clear_path_does_not_cancel_active_pursuit(self):
        """静的移動の経路クリアでは追跡状態が消えないこと"""
        aggregate = create_test_status_aggregate(current_spot_id=SpotId(1), current_coordinate=Coordinate(0, 0, 0))
        aggregate.set_destination(
            Coordinate(2, 0, 0),
            [Coordinate(0, 0, 0), Coordinate(1, 0, 0), Coordinate(2, 0, 0)],
        )
        snapshot = create_test_pursuit_snapshot()
        aggregate.start_pursuit(snapshot)
        aggregate.clear_events()

        aggregate.clear_path()

        assert aggregate.current_destination is None
        assert aggregate.planned_path == []
        assert aggregate.pursuit_state is not None
        assert aggregate.pursuit_state.target_snapshot == snapshot
        assert aggregate.get_events() == []

    def test_cancel_pursuit_emits_cancelled_event_and_clears_state(self):
        """明示的な追跡中断で中断イベントが発行されること"""
        aggregate = create_test_status_aggregate()
        aggregate.start_pursuit(create_test_pursuit_snapshot())
        aggregate.clear_events()

        aggregate.cancel_pursuit()

        assert aggregate.pursuit_state is None
        events = aggregate.get_events()
        cancelled = next(e for e in events if isinstance(e, PursuitCancelledEvent))
        assert cancelled.target_id == WorldObjectId.create(99)

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

    def test_speak_say_success(self):
        """発言（SAY）で PlayerSpokeEvent が発火すること"""
        spot_id = SpotId(1)
        coord = Coordinate(0, 0, 0)
        aggregate = create_test_status_aggregate(
            player_id=1,
            current_spot_id=spot_id,
            current_coordinate=coord,
        )
        aggregate.speak(
            content="こんにちは",
            channel=SpeechChannel.SAY,
            spot_id=spot_id,
            speaker_coordinate=coord,
        )
        events = aggregate.get_events()
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, PlayerSpokeEvent)
        assert ev.aggregate_id == aggregate.player_id
        assert ev.content == "こんにちは"
        assert ev.channel == SpeechChannel.SAY
        assert ev.spot_id == spot_id
        assert ev.speaker_coordinate == coord
        assert ev.target_player_id is None

    def test_speak_shout_success(self):
        """シャウト（SHOUT）で PlayerSpokeEvent が発火すること"""
        spot_id = SpotId(2)
        coord = Coordinate(1, 1, 0)
        aggregate = create_test_status_aggregate(
            player_id=2,
            current_spot_id=spot_id,
            current_coordinate=coord,
        )
        aggregate.speak(
            content="助けて！",
            channel=SpeechChannel.SHOUT,
            spot_id=spot_id,
            speaker_coordinate=coord,
        )
        events = aggregate.get_events()
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, PlayerSpokeEvent)
        assert ev.channel == SpeechChannel.SHOUT
        assert ev.content == "助けて！"

    def test_speak_whisper_success(self):
        """囁き（WHISPER）で宛先を指定して PlayerSpokeEvent が発火すること"""
        spot_id = SpotId(1)
        coord = Coordinate(0, 0, 0)
        target = PlayerId(99)
        aggregate = create_test_status_aggregate(
            player_id=1,
            current_spot_id=spot_id,
            current_coordinate=coord,
        )
        aggregate.speak(
            content="内緒だよ",
            channel=SpeechChannel.WHISPER,
            spot_id=spot_id,
            speaker_coordinate=coord,
            target_player_id=target,
        )
        events = aggregate.get_events()
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, PlayerSpokeEvent)
        assert ev.channel == SpeechChannel.WHISPER
        assert ev.target_player_id == target
        assert ev.content == "内緒だよ"

    def test_speak_whisper_without_target_raises(self):
        """囁きで宛先未指定の場合は SpeechValidationException"""
        spot_id = SpotId(1)
        coord = Coordinate(0, 0, 0)
        aggregate = create_test_status_aggregate(
            player_id=1,
            current_spot_id=spot_id,
            current_coordinate=coord,
        )
        with pytest.raises(SpeechValidationException, match="宛先プレイヤーを指定してください"):
            aggregate.speak(
                content="こんにちは",
                channel=SpeechChannel.WHISPER,
                spot_id=spot_id,
                speaker_coordinate=coord,
                target_player_id=None,
            )

    def test_speak_empty_content_raises(self):
        """発言内容が空の場合は SpeechValidationException"""
        spot_id = SpotId(1)
        coord = Coordinate(0, 0, 0)
        aggregate = create_test_status_aggregate(
            player_id=1,
            current_spot_id=spot_id,
            current_coordinate=coord,
        )
        with pytest.raises(SpeechValidationException, match="発言内容を空にできません"):
            aggregate.speak(
                content="",
                channel=SpeechChannel.SAY,
                spot_id=spot_id,
                speaker_coordinate=coord,
            )
        with pytest.raises(SpeechValidationException, match="発言内容を空にできません"):
            aggregate.speak(
                content="   ",
                channel=SpeechChannel.SAY,
                spot_id=spot_id,
                speaker_coordinate=coord,
            )

    def test_speak_when_downed_raises(self):
        """ダウン状態では発言できず PlayerDownedException"""
        spot_id = SpotId(1)
        coord = Coordinate(0, 0, 0)
        aggregate = create_test_status_aggregate(
            player_id=1,
            is_down=True,
            current_spot_id=spot_id,
            current_coordinate=coord,
        )
        with pytest.raises(PlayerDownedException, match="ダウン状態のプレイヤーは発言できません"):
            aggregate.speak(
                content="助けて",
                channel=SpeechChannel.SAY,
                spot_id=spot_id,
                speaker_coordinate=coord,
            )

    def test_speak_strips_content(self):
        """発言内容の前後空白はトリムされてイベントに含まれること"""
        spot_id = SpotId(1)
        coord = Coordinate(0, 0, 0)
        aggregate = create_test_status_aggregate(
            player_id=1,
            current_spot_id=spot_id,
            current_coordinate=coord,
        )
        aggregate.speak(
            content="  hello  ",
            channel=SpeechChannel.SAY,
            spot_id=spot_id,
            speaker_coordinate=coord,
        )
        events = aggregate.get_events()
        assert len(events) == 1
        assert events[0].content == "hello"

    class TestStatusEffects:
        def test_effective_stats_with_multiplicative_buffs_via_domain_service(self):
            # 実効ステータスはアプリ層で compute_effective_stats を使用する
            from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
            from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
            from ai_rpg_world.domain.common.value_object import WorldTick
            from ai_rpg_world.domain.common.service.effective_stats_domain_service import compute_effective_stats

            aggregate = create_test_status_aggregate(base_stats=create_test_base_stats(attack=20))
            aggregate.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 1.5, WorldTick(100)))
            aggregate.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 1.2, WorldTick(100)))

            effective_stats = compute_effective_stats(
                aggregate.base_stats, aggregate.active_effects, WorldTick(10)
            )
            assert effective_stats.attack == 36  # 20 * 1.5 * 1.2

        def test_effective_stats_filters_expired_effects_via_domain_service(self):
            from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
            from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
            from ai_rpg_world.domain.common.value_object import WorldTick
            from ai_rpg_world.domain.common.service.effective_stats_domain_service import compute_effective_stats

            aggregate = create_test_status_aggregate(base_stats=create_test_base_stats(attack=20))
            aggregate.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 2.0, WorldTick(5)))
            aggregate.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 1.5, WorldTick(20)))

            effective_stats = compute_effective_stats(
                aggregate.base_stats, aggregate.active_effects, WorldTick(10)
            )
            assert effective_stats.attack == 30  # 20 * 1.5 のみ（期限切れは除外）
            aggregate.cleanup_expired_effects(WorldTick(10))
            assert len(aggregate.active_effects) == 1

        def test_buff_and_debuff_stacking_via_domain_service(self):
            from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
            from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
            from ai_rpg_world.domain.common.value_object import WorldTick
            from ai_rpg_world.domain.common.service.effective_stats_domain_service import compute_effective_stats

            aggregate = create_test_status_aggregate(base_stats=create_test_base_stats(attack=20))
            aggregate.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 1.5, WorldTick(100)))
            aggregate.add_status_effect(StatusEffect(StatusEffectType.ATTACK_DOWN, 0.5, WorldTick(100)))

            effective_stats = compute_effective_stats(
                aggregate.base_stats, aggregate.active_effects, WorldTick(10)
            )
            assert effective_stats.attack == 15  # 20 * 1.5 * 0.5


class TestPlayerStatusAttentionLevel:
    """PlayerStatusAggregate の注意レベル（attention_level）のテスト"""

    def test_default_attention_level_is_full(self):
        from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel

        aggregate = create_test_status_aggregate()
        assert aggregate.attention_level == AttentionLevel.FULL

    def test_set_attention_level_changes_value(self):
        from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel

        aggregate = create_test_status_aggregate()
        aggregate.set_attention_level(AttentionLevel.IGNORE)
        assert aggregate.attention_level == AttentionLevel.IGNORE
        aggregate.set_attention_level(AttentionLevel.FILTER_SOCIAL)
        assert aggregate.attention_level == AttentionLevel.FILTER_SOCIAL

    def test_constructor_accepts_attention_level(self):
        from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel

        aggregate = PlayerStatusAggregate(
            player_id=PlayerId(1),
            base_stats=create_test_base_stats(),
            stat_growth_factor=create_test_stat_growth_factor(),
            exp_table=create_test_exp_table(),
            growth=create_test_growth(),
            gold=Gold.create(1000),
            hp=Hp.create(100, 100),
            mp=Mp.create(50, 50),
            stamina=Stamina.create(100, 100),
            attention_level=AttentionLevel.FILTER_SOCIAL,
        )
        assert aggregate.attention_level == AttentionLevel.FILTER_SOCIAL
