import pytest
from unittest.mock import Mock
from src.domain.battle.battle import Battle
from src.domain.battle.battle_enum import BattleResultType, BattleState, ParticipantType
from src.domain.battle.battle_exception import BattleNotStartedException, BattleFullException, PlayerAlreadyInBattleException
from src.domain.battle.combat_state import CombatState
from src.domain.battle.battle_result import BattleActionResult, TurnStartResult, TurnEndResult
from src.domain.battle.turn_order_service import TurnOrderService, TurnEntry
from src.domain.player.hp import Hp
from src.domain.player.mp import Mp
from src.domain.player.base_status import BaseStatus
from src.domain.battle.battle_enum import Element, Race


@pytest.fixture
def mock_player():
    """テスト用のPlayerモックを作成"""
    player = Mock()
    player.player_id = 1
    player.name = "TestPlayer"
    player.race = Race.HUMAN
    player.element = Element.FIRE
    player.hp = Hp(100, 100)
    player.mp = Mp(50, 50)
    player.calculate_status_including_equipment.return_value = BaseStatus(
        attack=50, defense=30, speed=20, critical_rate=0.1, evasion_rate=0.05
    )
    return player


@pytest.fixture
def mock_monster():
    """テスト用のMonsterモックを作成"""
    monster = Mock()
    monster.monster_type_id = 100
    monster.name = "TestMonster"
    monster.race = Race.DRAGON
    monster.element = Element.WATER
    monster.max_hp = 200
    monster.max_mp = 30
    monster.calculate_status_including_equipment.return_value = BaseStatus(
        attack=60, defense=40, speed=15, critical_rate=0.05, evasion_rate=0.03
    )
    return monster


@pytest.fixture
def mock_monster_for_join():
    """参加用のMonsterモックを作成"""
    monster = Mock()
    monster.monster_type_id = 101
    monster.name = "NewMonster"
    monster.race = Race.DRAGON
    monster.element = Element.FIRE
    monster.max_hp = 150
    monster.max_mp = 25
    monster.calculate_status_including_equipment.return_value = BaseStatus(
        attack=50, defense=35, speed=18, critical_rate=0.04, evasion_rate=0.04
    )
    return monster


@pytest.fixture
def mock_turn_order_service():
    """テスト用のTurnOrderServiceモックを作成"""
    service = Mock(spec=TurnOrderService)
    service.calculate_initial_turn_order.return_value = [
        TurnEntry(participant_key=(ParticipantType.PLAYER, 1), speed=20, priority=0),
        TurnEntry(participant_key=(ParticipantType.MONSTER, 1), speed=15, priority=0)
    ]
    service.recalculate_turn_order_for_next_round.return_value = [
        TurnEntry(participant_key=(ParticipantType.PLAYER, 1), speed=20, priority=0),
        TurnEntry(participant_key=(ParticipantType.MONSTER, 1), speed=15, priority=0)
    ]
    return service


@pytest.fixture
def battle(mock_turn_order_service):
    """テスト用のBattleインスタンスを作成"""
    # TurnOrderServiceをモックに置き換え
    original_init = Battle.__init__

    def mock_init(self, battle_id, spot_id, players, monsters, max_players=4, max_monsters=4, max_rounds=10):
        original_init(self, battle_id, spot_id, players, monsters, max_players, max_monsters, max_rounds)
        self._turn_order_service = mock_turn_order_service

    Battle.__init__ = mock_init

    try:
        battle = Battle(
            battle_id=1,
            spot_id=10,
            players=[],
            monsters=[],
            max_players=4,
            max_monsters=4,
            max_rounds=10
        )
        yield battle
    finally:
        # 元の__init__メソッドに戻す
        Battle.__init__ = original_init


class TestBattleInitialization:
    """Battle初期化のテスト"""

    def test_create_battle_with_valid_parameters(self, battle):
        """有効なパラメータでBattleを作成できる"""
        assert battle.battle_id == 1
        assert battle.spot_id == 10
        assert battle._max_players == 4
        assert battle._max_monsters == 4
        assert battle._max_rounds == 10
        assert battle._state == BattleState.WAITING
        assert len(battle._combat_states) == 0
        assert len(battle._player_ids) == 0
        assert len(battle._monster_ids) == 0

    def test_create_battle_with_invalid_max_players(self):
        """無効なmax_playersでBattle作成するとエラー"""
        with pytest.raises(ValueError, match="max_players must be greater than 0"):
            Battle(1, 10, [], [], max_players=0)

    def test_create_battle_with_invalid_max_monsters(self):
        """無効なmax_monstersでBattle作成するとエラー"""
        with pytest.raises(ValueError, match="max_monsters must be greater than 0"):
            Battle(1, 10, [], [], max_monsters=0)

    def test_create_battle_with_invalid_max_rounds(self):
        """無効なmax_roundsでBattle作成するとエラー"""
        with pytest.raises(ValueError, match="max_rounds must be greater than 0"):
            Battle(1, 10, [], [], max_rounds=0)

    def test_add_player_within_limit(self, battle, mock_player):
        """上限内のプレイヤーを追加できる"""
        battle._add_player(mock_player)

        assert len(battle._player_ids) == 1
        assert 1 in battle._player_ids
        assert (ParticipantType.PLAYER, 1) in battle._combat_states
        assert battle._contribution_scores[1] == 0

    def test_add_player_exceeds_limit(self, battle, mock_player):
        """上限を超えてプレイヤーを追加するとエラー"""
        battle._max_players = 1
        battle._add_player(mock_player)

        another_player = Mock()
        another_player.player_id = 2
        another_player.name = "AnotherPlayer"

        with pytest.raises(BattleFullException):
            battle._add_player(another_player)

    def test_add_duplicate_player(self, battle, mock_player):
        """同じプレイヤーを重複して追加するとエラー"""
        battle._add_player(mock_player)

        with pytest.raises(PlayerAlreadyInBattleException):
            battle._add_player(mock_player)

    def test_add_monster_within_limit(self, battle, mock_monster):
        """上限内のモンスターを追加できる"""
        battle._add_monster(mock_monster)

        assert len(battle._monster_ids) == 1
        assert 1 in battle._monster_ids
        assert (ParticipantType.MONSTER, 1) in battle._combat_states
        assert mock_monster.monster_type_id in battle._monster_type_ids

    def test_add_monster_exceeds_limit(self, battle, mock_monster):
        """上限を超えてモンスターを追加するとエラー"""
        battle._max_monsters = 1
        battle._add_monster(mock_monster)

        another_monster = Mock()
        another_monster.monster_type_id = 101
        another_monster.name = "AnotherMonster"

        with pytest.raises(BattleFullException):
            battle._add_monster(another_monster)


class TestBattleFlow:
    """戦闘フローのテスト"""

    def test_start_battle_with_participants(self, battle, mock_player, mock_monster, mock_turn_order_service):
        """参加者がいる状態で戦闘を開始できる"""
        battle._add_player(mock_player)
        battle._add_monster(mock_monster)

        battle.start_battle()

        assert battle._state == BattleState.IN_PROGRESS
        assert battle._current_turn_index == 0
        assert battle._current_round == 1
        assert len(battle._turn_order) == 2
        mock_turn_order_service.calculate_initial_turn_order.assert_called_once()

    def test_start_battle_not_waiting_raises_exception(self, battle):
        """WAITING状態でないときにstart_battleを呼ぶとエラー"""
        battle._state = BattleState.IN_PROGRESS

        with pytest.raises(BattleNotStartedException):
            battle.start_battle()

    def test_get_current_actor(self, battle, mock_player, mock_monster, mock_turn_order_service):
        """現在のアクターを取得できる"""
        battle._add_player(mock_player)
        battle._add_monster(mock_monster)
        battle.start_battle()

        current_actor = battle.get_current_actor()

        assert current_actor.participant_key[0] == ParticipantType.PLAYER
        assert current_actor.participant_key[1] == 1

    def test_get_current_actor_no_turn_order_raises_error(self, battle):
        """ターン順序が計算されていないときにget_current_actorを呼ぶとエラー"""
        with pytest.raises(ValueError, match="Turn order not calculated"):
            battle.get_current_actor()

    def test_start_turn_sets_defending_to_false(self, battle, mock_player, mock_monster, mock_turn_order_service):
        """ターン開始時に防御状態が解除される"""
        battle._add_player(mock_player)
        battle._add_monster(mock_monster)
        battle.start_battle()

        # 防御状態を設定
        original_state = battle._combat_states[(ParticipantType.PLAYER, 1)]
        defending_state = original_state.with_defend()
        battle._combat_states[(ParticipantType.PLAYER, 1)] = defending_state

        battle.start_turn()

        # 防御状態が解除されていることを確認
        updated_state = battle._combat_states[(ParticipantType.PLAYER, 1)]
        assert not updated_state.is_defending

    def test_advance_to_next_turn_in_same_round(self, battle, mock_player, mock_monster, mock_turn_order_service):
        """同じラウンド内の次のターンに進める"""
        battle._add_player(mock_player)
        battle._add_monster(mock_monster)
        battle.start_battle()

        initial_index = battle._current_turn_index
        result = battle.advance_to_next_turn()

        assert result is True
        assert battle._current_turn_index == initial_index + 1
        assert battle._current_round == 1

    def test_advance_to_next_round(self, battle, mock_player, mock_monster, mock_turn_order_service):
        """次のラウンドに進める"""
        battle._add_player(mock_player)
        battle._add_monster(mock_monster)
        battle.start_battle()

        # ターン順序の最後まで進める
        battle._current_turn_index = len(battle._turn_order) - 1
        result = battle.advance_to_next_turn()

        assert result is True
        assert battle._current_turn_index == 0
        assert battle._current_round == 2
        mock_turn_order_service.recalculate_turn_order_for_next_round.assert_called_once()


class TestBattleEndConditions:
    """戦闘終了条件のテスト"""

    def test_check_battle_end_victory_when_all_monsters_dead(self, battle, mock_player, mock_monster):
        """全モンスターが死亡したら勝利"""
        battle._add_player(mock_player)
        battle._add_monster(mock_monster)

        # モンスターを死亡状態にする
        monster_state = battle._combat_states[(ParticipantType.MONSTER, 1)]
        dead_monster_state = monster_state.with_hp_damaged(monster_state.current_hp.value)
        battle._combat_states[(ParticipantType.MONSTER, 1)] = dead_monster_state

        result = battle.check_battle_end_conditions()

        assert result == BattleResultType.VICTORY

    def test_check_battle_end_defeat_when_all_players_dead(self, battle, mock_player, mock_monster):
        """全プレイヤーが死亡したら敗北"""
        battle._add_player(mock_player)
        battle._add_monster(mock_monster)

        # プレイヤーを死亡状態にする
        player_state = battle._combat_states[(ParticipantType.PLAYER, 1)]
        dead_player_state = player_state.with_hp_damaged(player_state.current_hp.value)
        battle._combat_states[(ParticipantType.PLAYER, 1)] = dead_player_state

        result = battle.check_battle_end_conditions()

        assert result == BattleResultType.DEFEAT

    def test_check_battle_end_draw_when_max_rounds_reached(self, battle, mock_player, mock_monster):
        """最大ラウンド数に達したら引き分け"""
        battle._add_player(mock_player)
        battle._add_monster(mock_monster)

        battle._current_round = battle._max_rounds

        result = battle.check_battle_end_conditions()

        assert result == BattleResultType.DRAW

    def test_check_battle_end_no_end_condition(self, battle, mock_player, mock_monster):
        """終了条件を満たさない場合はNone"""
        battle._add_player(mock_player)
        battle._add_monster(mock_monster)

        result = battle.check_battle_end_conditions()

        assert result is None


class TestBattleResultApplication:
    """戦闘結果適用のテスト"""

    def test_apply_turn_start_result(self, battle, mock_player):
        """ターン開始結果を適用できる"""
        battle._add_player(mock_player)

        turn_start_result = TurnStartResult(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            can_act=True,
            damage=10,
            healing=5
        )

        battle.apply_turn_start_result(turn_start_result)

        updated_state = battle._combat_states[(ParticipantType.PLAYER, 1)]
        assert updated_state.current_hp.value == 95  # 100 - 10 + 5

    def test_apply_turn_start_result_invalid_actor(self, battle):
        """無効なアクターのターン開始結果適用でエラー"""
        turn_start_result = TurnStartResult(
            actor_id=999,
            participant_type=ParticipantType.PLAYER,
            can_act=True
        )

        with pytest.raises(ValueError, match="Combat state not found"):
            battle.apply_turn_start_result(turn_start_result)

    def test_apply_battle_action_result(self, battle, mock_player):
        """戦闘アクション結果を適用できる"""
        from src.domain.battle.battle_result import BattleActionResult, ActorStateChange

        battle._add_player(mock_player)

        # アクション結果を作成
        actor_state_change = ActorStateChange(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            hp_change=0,
            mp_change=-10
        )
        action_result = BattleActionResult(
            success=True,
            messages=["攻撃成功"],
            actor_state_change=actor_state_change,
            target_state_changes=[]
        )

        battle.apply_battle_action_result(action_result)

        # MPが消費されていることを確認
        updated_state = battle._combat_states[(ParticipantType.PLAYER, 1)]
        assert updated_state.current_mp.value == 40  # 50 - 10

    def test_apply_turn_end_result(self, battle, mock_player):
        """ターン終了結果を適用できる"""
        battle._add_player(mock_player)

        turn_end_result = TurnEndResult(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            damage=5,
            healing=3
        )

        battle.apply_turn_end_result(turn_end_result)

        updated_state = battle._combat_states[(ParticipantType.PLAYER, 1)]
        assert updated_state.current_hp.value == 98  # 100 - 5 + 3


class TestBattleParticipantManagement:
    """参加者管理のテスト"""

    def test_join_player_during_battle(self, battle, mock_player):
        """戦闘中にプレイヤーが参加できる"""
        battle.start_battle()  # 戦闘を開始

        new_player = Mock()
        new_player.player_id = 2
        new_player.name = "NewPlayer"

        battle.join_player(new_player, 1)

        assert 2 in battle._player_ids
        assert (ParticipantType.PLAYER, 2) in battle._combat_states

    def test_join_monster_during_battle(self, battle, mock_monster_for_join):
        """戦闘中にモンスターが参加できる"""
        battle.start_battle()  # 戦闘を開始

        battle.join_monster(mock_monster_for_join, 1)

        assert len(battle._monster_ids) == 1  # カウンターが1から始まるのでIDは1
        assert (ParticipantType.MONSTER, 1) in battle._combat_states

    def test_player_escape(self, battle, mock_player):
        """プレイヤーが戦闘から離脱できる"""
        battle._add_player(mock_player)

        battle.player_escape(mock_player)

        assert 1 not in battle._player_ids
        assert (ParticipantType.PLAYER, 1) not in battle._combat_states
        assert 1 in battle._escaped_player_ids

    def test_player_escape_not_in_battle_raises_error(self, battle, mock_player):
        """戦闘に参加していないプレイヤーの離脱でエラー"""
        with pytest.raises(ValueError, match="Player not in battle"):
            battle.player_escape(mock_player)


class TestBattleUtilityMethods:
    """ユーティリティメソッドのテスト"""

    def test_get_combat_state(self, battle, mock_player):
        """戦闘状態を取得できる"""
        battle._add_player(mock_player)

        state = battle.get_combat_state(ParticipantType.PLAYER, 1)

        assert state is not None
        assert state.entity_id == 1
        assert state.participant_type == ParticipantType.PLAYER

    def test_get_combat_states(self, battle, mock_player, mock_monster):
        """全ての戦闘状態を取得できる"""
        battle._add_player(mock_player)
        battle._add_monster(mock_monster)

        states = battle.get_combat_states()

        assert len(states) == 2
        assert (ParticipantType.PLAYER, 1) in states
        assert (ParticipantType.MONSTER, 1) in states

    def test_get_player_ids(self, battle, mock_player):
        """プレイヤーIDを取得できる"""
        battle._add_player(mock_player)

        player_ids = battle.get_player_ids()

        assert player_ids == [1]

    def test_get_monster_type_ids(self, battle, mock_monster):
        """モンスタータイプIDを取得できる"""
        battle._add_monster(mock_monster)

        monster_type_ids = battle.get_monster_type_ids()

        assert monster_type_ids == [100]

    def test_end_battle(self, battle):
        """戦闘を終了できる"""
        battle._state = BattleState.IN_PROGRESS

        battle.end_battle(BattleResultType.VICTORY)

        assert battle._state == BattleState.COMPLETED
