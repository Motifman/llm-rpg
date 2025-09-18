import random
from typing import Optional, List, Dict, Any
from src.domain.battle.battle import Battle
from src.domain.battle.battle_repository import BattleRepository
from src.domain.battle.action_repository import ActionRepository
from src.domain.battle.battle_action import BattleAction
from src.domain.player.player_repository import PlayerRepository
from src.domain.spot.area_repository import AreaRepository
from src.domain.monster.monster_repository import MonsterRepository
from src.domain.battle.battle_exception import BattleAlreadyExistsException, AreaNotFoundException, BattleNotFoundException, ActorNotFoundException
from src.domain.battle.turn_order_service import TurnEntry
from src.domain.battle.battle_service import BattleLogicService
from src.domain.battle.battle_enum import ParticipantType
from src.domain.battle.services.monster_action_service import MonsterActionService
from src.domain.common.notifier import Notifier
from src.domain.common.event_publisher import EventPublisher
from src.application.battle.contracts.dtos import PlayerActionDto, BattleStatusDto
from src.application.battle.handlers import (
    BattleStartedNotificationHandler,
    PlayerJoinedBattleNotificationHandler,
    TurnStartedNotificationHandler,
    TurnExecutedNotificationHandler,
    BattleEndedNotificationHandler,
    MonsterDefeatedNotificationHandler,
    PlayerDefeatedNotificationHandler,
    StatusEffectAppliedNotificationHandler,
    BuffAppliedNotificationHandler,
)
from src.domain.battle.battle_result import BattleActionResult
from src.domain.battle.battle_enum import BattleResultType, ParticipantType


class BattleApplicationService:
    _MAX_MONSTERS = 4

    def __init__(
        self,
        battle_repository: BattleRepository,
        player_repository: PlayerRepository,
        area_repository: AreaRepository,
        monster_repository: MonsterRepository,
        action_repository: ActionRepository,
        battle_logic_service: BattleLogicService,
        monster_action_service: MonsterActionService,
        notifier: Notifier,
        event_publisher: EventPublisher
    ):
        self._battle_repository = battle_repository
        self._player_repository = player_repository
        self._area_repository = area_repository
        self._monster_repository = monster_repository
        self._action_repository = action_repository
        self._battle_logic_service = battle_logic_service
        self._monster_action_service = monster_action_service
        self._notifier = notifier
        self._event_publisher = event_publisher

        # イベントハンドラーを初期化して登録
        self._register_event_handlers()
    
    def get_battle_in_spot(self, spot_id: int) -> Optional[Battle]:
        return self._battle_repository.find_by_spot_id(spot_id)
    
    def start_battle(self, player_id: int):
        """
        戦闘を開始する
        """
        try:
            player = self._player_repository.find_by_id(player_id)
            if not player:
                raise ValueError(f"Player not found. player_id: {player_id}")

            spot_id = player.current_spot_id
            battle = self._battle_repository.find_by_spot_id(spot_id)
            if battle:
                raise BattleAlreadyExistsException()

            area = self._area_repository.find_by_spot_id(spot_id)
            if not area:
                raise AreaNotFoundException()

            monster_type_ids = area.get_spawn_monster_type_ids()
            spawned_monster_type_ids = random.choices(list(monster_type_ids), k=self._MAX_MONSTERS)

            monsters = self._monster_repository.find_by_ids(spawned_monster_type_ids)
            battle = Battle(
                battle_id=self._battle_repository.generate_battle_id(),
                spot_id=spot_id,
                players=[player],
                monsters=monsters
            )

            # 戦闘を開始
            battle.start_battle()

            # イベントをパブリッシュ
            self._event_publisher.publish_all(battle.get_events())
            battle.clear_events()

            self._battle_repository.save(battle)

            # 戦闘を開始したら最初のターンを開始
            self.start_turn(battle.battle_id)

        except (BattleAlreadyExistsException, AreaNotFoundException) as e:
            raise e
        except Exception as e:
            raise e

    def start_turn(self, battle_id: int):
        """
        ターンを開始する
        """
        battle = self._battle_repository.find_by_id(battle_id)
        if not battle:
            raise BattleNotFoundException()

        battle.start_turn()
        current_actor = battle.get_current_actor()

        # イベントをパブリッシュ
        self._event_publisher.publish_all(battle.get_events())
        battle.clear_events()

        participant_type, entity_id = current_actor.participant_key
        if participant_type == ParticipantType.PLAYER:
            self._start_player_turn(battle, current_actor)
        else:
            self._start_monster_turn(battle, current_actor)
    
    def _start_player_turn(self, battle: Battle, actor: TurnEntry):
        """
        プレイヤーのターンを開始する
        """
        participant_type, entity_id = actor.participant_key
        actor_combat_state = battle.get_combat_state(participant_type, entity_id)
        if not actor_combat_state:
            raise ActorNotFoundException()

        turn_start_result = self._battle_logic_service.process_on_turn_start(actor_combat_state)
        battle.apply_turn_start_result(turn_start_result)

        # イベントをパブリッシュ
        self._event_publisher.publish_all(battle.get_events())
        battle.clear_events()

        battle_result = battle.check_battle_end_conditions()
        if battle_result:
            battle.end_battle(battle_result)
            # イベントをパブリッシュ
            self._event_publisher.publish_all(battle.get_events())
            battle.clear_events()
            self._battle_repository.save(battle)
        else:
            if turn_start_result.can_act:
                self._battle_repository.save(battle)
                # プレイヤーに次の行動を選択するように促す通知はイベントハンドラーが処理
            else:
                turn_end_result = self._battle_logic_service.process_on_turn_end(actor)
                battle.apply_turn_end_result(turn_end_result)
                battle.advance_to_next_turn(turn_end_result)
                # イベントをパブリッシュ
                self._event_publisher.publish_all(battle.get_events())
                battle.clear_events()
                self._battle_repository.save(battle)
                self.start_turn(battle.battle_id)

    def _start_monster_turn(self, battle: Battle, actor: TurnEntry):
        """
        モンスターのターンを開始する
        """
        participant_type, entity_id = actor.participant_key
        actor_combat_state = battle.get_combat_state(participant_type, entity_id)
        if not actor_combat_state:
            raise ActorNotFoundException()

        turn_start_result = self._battle_logic_service.process_on_turn_start(actor_combat_state)
        battle.apply_turn_start_result(turn_start_result)

        # イベントをパブリッシュ
        self._event_publisher.publish_all(battle.get_events())
        battle.clear_events()

        battle_result = battle.check_battle_end_conditions()
        if battle_result:
            battle.end_battle(battle_result)
            # イベントをパブリッシュ
            self._event_publisher.publish_all(battle.get_events())
            battle.clear_events()
            self._battle_repository.save(battle)
        else:
            if turn_start_result.can_act:
                # モンスターの行動選択と実行
                self._execute_monster_action(battle, actor)
            else:
                # モンスターが行動不能の場合の処理
                # イベントハンドラーが通知を処理
                pass

            turn_end_result = self._battle_logic_service.process_on_turn_end(actor_combat_state)
            battle.apply_turn_end_result(turn_end_result)
            battle.advance_to_next_turn(turn_end_result)
            # イベントをパブリッシュ
            self._event_publisher.publish_all(battle.get_events())
            battle.clear_events()
            self._battle_repository.save(battle)
            self.start_turn(battle.battle_id)

    def _execute_monster_action(self, battle: Battle, monster_actor):
        """
        モンスターの行動を実行する
        """
        try:
            # モンスターの戦闘状態を取得
            participant_type, entity_id = monster_actor.participant_key
            monster_combat_state = battle.get_combat_state(participant_type, entity_id)
            if not monster_combat_state:
                raise ValueError("Monster combat state not found")
            
            # 利用可能なアクションを取得（アプリケーション層の責務）
            available_actions = []
            for action_id in monster_combat_state.available_action_ids:
                action = self._action_repository.find_by_id(action_id)
                if action:
                    available_actions.append(action)

            if not available_actions:
                raise ValueError("No available actions for monster")

            # モンスターの行動とターゲットを選択（ドメインサービス）
            all_participants = list(battle.get_combat_states().values())
            action_and_targets = self._monster_action_service.select_monster_action_with_targets(
                monster_combat_state, available_actions, all_participants
            )

            if not action_and_targets:
                raise ValueError("Monster action selection failed")
            
            selected_action, selected_targets = action_and_targets

            # アクションを実行（BattleAction.execute()を使用）
            battle_action_result = selected_action.execute(
                actor=monster_combat_state,
                specified_targets=selected_targets,
                context=self._battle_logic_service,
                all_participants=all_participants
            )

            # アクション結果を適用
            battle.apply_battle_action_result(battle_action_result)

            # ターン実行イベントを発行
            participant_type, entity_id = monster_actor.participant_key
            battle.execute_turn(
                participant_type,
                entity_id,
                selected_action,
                battle_action_result
            )

            # イベントをパブリッシュ
            self._event_publisher.publish_all(battle.get_events())
            battle.clear_events()

        except Exception as e:
            raise ValueError(f"Monster action execution failed: {e}")

    def execute_player_action(self, battle_id: int, player_id: int, action_data: PlayerActionDto):
        """
        プレイヤーの行動を実行する
        """
        # 戦闘とプレイヤーの検証
        battle = self._get_battle_by_id(battle_id)
        self._validate_player_turn(battle, player_id)
        player_actor = self._get_player_combat_state(battle, player_id)

        # アクションの取得と検証
        action = self._get_action_by_id(action_data.action_id)

        # ターゲットの解決
        all_participants = list(battle.get_combat_states().values())
        specified_targets = self._resolve_specified_targets(battle, action_data)

        # アクションの実行
        self._execute_and_process_player_action(
            battle, player_actor, action, specified_targets, all_participants, battle_id
        )

    def _get_battle_by_id(self, battle_id: int) -> Battle:
        """戦闘を取得し、存在チェック"""
        battle = self._battle_repository.find_by_id(battle_id)
        if not battle:
            raise BattleNotFoundException()
        return battle

    def _validate_player_turn(self, battle: Battle, player_id: int):
        """現在のターンが正しいプレイヤーかチェック"""
        current_actor = battle.get_current_actor()
        participant_type, entity_id = current_actor.participant_key
        if (participant_type != ParticipantType.PLAYER or
            entity_id != player_id):
            raise ValueError(f"Invalid player turn. Expected: {entity_id}, Got: {player_id}")

    def _get_player_combat_state(self, battle: Battle, player_id: int):
        """プレイヤーの戦闘状態を取得"""
        player_actor = battle.get_combat_state(ParticipantType.PLAYER, player_id)
        if not player_actor:
            raise ActorNotFoundException()
        return player_actor

    def _get_action_by_id(self, action_id: int):
        """アクションを取得し、存在チェック"""
        action = self._action_repository.find_by_id(action_id)
        if not action:
            raise ValueError(f"Action not found. action_id: {action_id}")
        return action

    def _resolve_specified_targets(self, battle: Battle, action_data: PlayerActionDto):
        """指定されたターゲットを解決"""
        specified_targets = []
        if action_data.target_ids and action_data.target_participant_types:
            for target_id, target_type in zip(action_data.target_ids, action_data.target_participant_types):
                target = battle.get_combat_state(target_type, target_id)
                if target:
                    specified_targets.append(target)
        return specified_targets

    def _execute_and_process_player_action(
        self, battle: Battle, player_actor, action, specified_targets, all_participants, battle_id: int
    ):
        """アクションを実行し結果を処理"""
        try:
            battle_action_result = action.execute(
                actor=player_actor,
                specified_targets=specified_targets,
                context=self._battle_logic_service,
                all_participants=all_participants
            )

            # 結果の適用とイベント処理
            battle.apply_battle_action_result(battle_action_result)
            battle.execute_turn(ParticipantType.PLAYER, player_actor.entity_id, action, battle_action_result)
            self._event_publisher.publish_all(battle.get_events())
            battle.clear_events()

            # 次のターンへ
            battle.advance_to_next_turn()
            self._battle_repository.save(battle)
            self.start_turn(battle_id)

        except Exception as e:
            raise ValueError(f"Player action execution failed: {e}")
    
    def end_battle(self, battle_id: int):
        """
        戦闘を終了する
        """
        battle = self._battle_repository.find_by_id(battle_id)
        if not battle:
            raise BattleNotFoundException()

        # 戦闘終了条件をチェック
        battle_result = battle.check_battle_end_conditions()
        if battle_result:
            battle.end_battle(battle_result)
            # イベントをパブリッシュ
            self._event_publisher.publish_all(battle.get_events())
            battle.clear_events()
            self._battle_repository.save(battle)
        else:
            raise ValueError("Battle is not ready to end")

    def join_battle(self, battle_id: int, player_id: int):
        """
        プレイヤーが戦闘に参加する
        """
        battle = self._battle_repository.find_by_id(battle_id)
        if not battle:
            raise BattleNotFoundException()

        player = self._player_repository.find_by_id(player_id)
        if not player:
            raise ValueError(f"Player not found. player_id: {player_id}")

        # プレイヤーが同じスポットにいるかチェック
        if player.current_spot_id != battle.spot_id:
            raise ValueError("Player is not in the same spot as the battle")

        # 戦闘に参加
        battle.join_player(player, battle._current_turn)
        # イベントをパブリッシュ
        self._event_publisher.publish_all(battle.get_events())
        battle.clear_events()
        self._battle_repository.save(battle)

    def leave_battle(self, battle_id: int, player_id: int):
        """
        プレイヤーが戦闘から離脱する
        """
        battle = self._battle_repository.find_by_id(battle_id)
        if not battle:
            raise BattleNotFoundException()

        player = self._player_repository.find_by_id(player_id)
        if not player:
            raise ValueError(f"Player not found. player_id: {player_id}")

        # 戦闘から離脱
        battle.player_escape(player)
        # イベントをパブリッシュ
        self._event_publisher.publish_all(battle.get_events())
        battle.clear_events()
        self._battle_repository.save(battle)

    def get_battle_status(self, battle_id: int) -> BattleStatusDto:
        """
        戦闘の状態を取得する
        """
        battle = self._battle_repository.find_by_id(battle_id)
        if not battle:
            raise BattleNotFoundException()

        return BattleStatusDto(
            battle_id=battle.battle_id,
            is_active=battle._state == battle._state.IN_PROGRESS,
            current_turn=battle._current_turn,
            current_round=battle._current_round,
            player_count=len(battle.get_player_ids()),
            monster_count=len(battle.get_monster_type_ids()),
            can_player_join=battle._state == battle._state.WAITING and len(battle.get_player_ids()) < battle._max_players
        )

    def _register_event_handlers(self):
        """イベントハンドラーを初期化して登録"""
        from src.domain.battle.events.battle_events import (
            BattleStartedEvent,
            PlayerJoinedBattleEvent,
            TurnStartedEvent,
            TurnExecutedEvent,
            BattleEndedEvent,
            MonsterDefeatedEvent,
            PlayerDefeatedEvent,
            StatusEffectAppliedEvent,
            BuffAppliedEvent,
        )

        # ハンドラーの初期化
        battle_started_handler = BattleStartedNotificationHandler(
            self._notifier, self._area_repository, self._player_repository
        )
        player_joined_handler = PlayerJoinedBattleNotificationHandler(
            self._notifier, self._player_repository
        )
        turn_started_handler = TurnStartedNotificationHandler(
            self._notifier, self._player_repository
        )
        turn_executed_handler = TurnExecutedNotificationHandler(
            self._notifier, self._player_repository
        )
        battle_ended_handler = BattleEndedNotificationHandler(
            self._notifier, self._player_repository
        )
        monster_defeated_handler = MonsterDefeatedNotificationHandler(
            self._notifier, self._player_repository
        )
        player_defeated_handler = PlayerDefeatedNotificationHandler(
            self._notifier, self._player_repository
        )
        status_effect_handler = StatusEffectAppliedNotificationHandler(
            self._notifier, self._player_repository
        )
        buff_handler = BuffAppliedNotificationHandler(
            self._notifier, self._player_repository
        )

        # イベントパブリッシャーに登録
        self._event_publisher.register_handler(BattleStartedEvent, battle_started_handler)
        self._event_publisher.register_handler(PlayerJoinedBattleEvent, player_joined_handler)
        self._event_publisher.register_handler(TurnStartedEvent, turn_started_handler)
        self._event_publisher.register_handler(TurnExecutedEvent, turn_executed_handler)
        self._event_publisher.register_handler(BattleEndedEvent, battle_ended_handler)
        self._event_publisher.register_handler(MonsterDefeatedEvent, monster_defeated_handler)
        self._event_publisher.register_handler(PlayerDefeatedEvent, player_defeated_handler)
        self._event_publisher.register_handler(StatusEffectAppliedEvent, status_effect_handler)
        self._event_publisher.register_handler(BuffAppliedEvent, buff_handler)