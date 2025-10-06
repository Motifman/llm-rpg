"""
改良された戦闘アプリケーションサービス

新しいサービスクラスを統合し、責務を明確に分離:
- TurnProcessor: ターン処理ロジック
- BattleLoopService: 非同期戦闘ループ
- PlayerActionWaiter: プレイヤー行動待機

既存のBattleApplicationServiceから段階的に移行するための実装
"""
import random
import asyncio
from typing import Optional, List
from src.domain.battle.battle import Battle
from src.domain.battle.battle_repository import BattleRepository
from src.domain.battle.action_repository import ActionRepository
from src.domain.player.player_repository import PlayerRepository
from src.domain.spot.area_repository import AreaRepository
from src.domain.monster.monster_repository import MonsterRepository
from src.domain.battle.battle_exception import (
    BattleAlreadyExistsException, 
    AreaNotFoundException, 
    BattleNotFoundException
)
from src.domain.battle.battle_enum import ParticipantType
from src.domain.battle.battle_service import BattleLogicService
from src.domain.battle.services.monster_action_service import MonsterActionService
from src.domain.battle.services.turn_processor import TurnProcessor
from src.domain.common.notifier import Notifier
from src.domain.common.event_publisher import EventPublisher
from src.application.combat.contracts.dtos import PlayerActionDto, BattleStatusDto
from src.application.combat.services.battle_loop_service import BattleLoopService
from src.application.combat.services.player_action_waiter import PlayerActionWaiter
from src.application.combat.handlers import (
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


class EnhancedBattleApplicationService:
    """改良された戦闘アプリケーションサービス"""
    
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
        event_publisher: EventPublisher,
        player_action_waiter: Optional[PlayerActionWaiter] = None
    ):
        # 基本的な依存性
        self._battle_repository = battle_repository
        self._player_repository = player_repository
        self._area_repository = area_repository
        self._monster_repository = monster_repository
        self._action_repository = action_repository
        self._battle_logic_service = battle_logic_service
        self._monster_action_service = monster_action_service
        self._notifier = notifier
        self._event_publisher = event_publisher
        
        # 新しいサービスクラス
        self._turn_processor = TurnProcessor(battle_logic_service)
        self._player_action_waiter = player_action_waiter or PlayerActionWaiter()
        self._battle_loop_service = BattleLoopService(
            battle_repository=battle_repository,
            turn_processor=self._turn_processor,
            monster_action_service=monster_action_service,
            action_repository=action_repository,
            event_publisher=event_publisher,
            player_action_waiter=self._player_action_waiter
        )
        
        # イベントハンドラーを初期化して登録
        self._register_event_handlers()
    
    def get_battle_in_spot(self, spot_id: int) -> Optional[Battle]:
        """スポット内の戦闘を取得"""
        return self._battle_repository.find_by_spot_id(spot_id)
    
    async def start_battle(self, player_id: int) -> None:
        """
        戦闘を開始する（非同期版）
        
        Args:
            player_id: 戦闘を開始するプレイヤーID
            
        Raises:
            ValueError: プレイヤーが見つからない場合
            BattleAlreadyExistsException: 既に戦闘が存在する場合
            AreaNotFoundException: エリアが見つからない場合
        """
        # プレイヤー検証
        player = self._player_repository.find_by_id(player_id)
        if not player:
            raise ValueError(f"Player not found. player_id: {player_id}")
        
        spot_id = player.current_spot_id
        
        # 既存戦闘チェック
        existing_battle = self._battle_repository.find_by_spot_id(spot_id)
        if existing_battle:
            raise BattleAlreadyExistsException()
        
        # エリア検証
        area = self._area_repository.find_by_spot_id(spot_id)
        if not area:
            raise AreaNotFoundException()
        
        # モンスター生成
        monster_type_ids = area.get_spawn_monster_type_ids()
        spawned_monster_type_ids = random.choices(
            list(monster_type_ids), 
            k=self._MAX_MONSTERS
        )
        monsters = self._monster_repository.find_by_ids(spawned_monster_type_ids)
        
        # 戦闘作成
        battle = Battle(
            battle_id=self._battle_repository.generate_battle_id(),
            spot_id=spot_id,
            players=[player],
            monsters=monsters
        )
        
        # 戦闘開始
        battle.start_battle()
        
        # イベント発行
        self._event_publisher.publish_all(battle.get_events())
        battle.clear_events()
        
        # 保存
        self._battle_repository.save(battle)
        
        # 戦闘ループを開始
        await self._battle_loop_service.start_battle_loop(battle.battle_id)
    
    def start_battle_sync(self, player_id: int) -> None:
        """
        戦闘を開始する（同期版・既存互換性のため）
        
        Args:
            player_id: 戦闘を開始するプレイヤーID
        """
        # 非同期版を同期的に実行
        asyncio.create_task(self.start_battle(player_id))
    
    async def execute_player_action(
        self, 
        battle_id: int, 
        player_id: int, 
        action_data: PlayerActionDto
    ) -> None:
        """
        プレイヤーの行動を実行する（非同期版）
        
        Args:
            battle_id: 戦闘ID
            player_id: プレイヤーID
            action_data: 行動データ
        """
        # 戦闘とプレイヤーの検証
        battle = self._get_battle_by_id(battle_id)
        
        # ターンロック状態での検証（より柔軟に）
        if not battle.is_waiting_for_player_action():
            self._validate_player_turn(battle, player_id)
        
        player_combat_state = self._get_player_combat_state(battle, player_id)
        
        # アクションの取得と検証
        action = self._get_action_by_id(action_data.action_id)
        
        # ターゲットの解決
        all_participants = list(battle.get_combat_states().values())
        specified_targets = self._resolve_specified_targets(battle, action_data)
        
        # アクションの実行
        battle_action_result = action.execute(
            actor=player_combat_state,
            specified_targets=specified_targets,
            context=self._battle_logic_service,
            all_participants=all_participants
        )
        
        # 結果の適用
        battle.apply_battle_action_result(battle_action_result)
        battle.execute_turn(ParticipantType.PLAYER, player_id, action, battle_action_result)
        
        # イベント発行
        self._event_publisher.publish_all(battle.get_events())
        battle.clear_events()
        
        # ターンロックを解除してターンを進める
        if battle.is_waiting_for_player_action():
            battle.unlock_turn_after_player_action(player_id)
            
            # ターン終了処理
            current_actor = battle.get_current_actor()
            turn_end_result = self._turn_processor.process_turn_end(battle, current_actor)
            self._turn_processor.advance_turn(battle, turn_end_result)
            
            # イベント発行
            self._event_publisher.publish_all(battle.get_events())
            battle.clear_events()
        
        # 保存
        self._battle_repository.save(battle)
        
        # プレイヤー行動完了を通知
        self._player_action_waiter.notify_player_action_completed(battle_id, player_id)
    
    def execute_player_action_sync(
        self, 
        battle_id: int, 
        player_id: int, 
        action_data: PlayerActionDto
    ) -> None:
        """
        プレイヤーの行動を実行する（同期版・既存互換性のため）
        
        Args:
            battle_id: 戦闘ID
            player_id: プレイヤーID
            action_data: 行動データ
        """
        # 非同期版を同期的に実行
        asyncio.create_task(self.execute_player_action(battle_id, player_id, action_data))
    
    def stop_battle_loop(self, battle_id: int) -> None:
        """
        戦闘ループを停止
        
        Args:
            battle_id: 戦闘ID
        """
        self._battle_loop_service.stop_battle_loop(battle_id)
    
    def is_battle_loop_running(self, battle_id: int) -> bool:
        """
        戦闘ループが実行中かどうか
        
        Args:
            battle_id: 戦闘ID
            
        Returns:
            bool: 実行中の場合True
        """
        return self._battle_loop_service.is_battle_loop_running(battle_id)
    
    def join_battle(self, battle_id: int, player_id: int) -> None:
        """
        プレイヤーが戦闘に参加する
        
        Args:
            battle_id: 戦闘ID
            player_id: プレイヤーID
        """
        battle = self._get_battle_by_id(battle_id)
        player = self._get_player_by_id(player_id)
        
        # プレイヤーが同じスポットにいるかチェック
        if player.current_spot_id != battle.spot_id:
            raise ValueError("Player is not in the same spot as the battle")
        
        # 戦闘に参加
        battle.join_player(player, battle._current_turn)
        
        # イベント発行
        self._event_publisher.publish_all(battle.get_events())
        battle.clear_events()
        
        # 保存
        self._battle_repository.save(battle)
    
    def leave_battle(self, battle_id: int, player_id: int) -> None:
        """
        プレイヤーが戦闘から離脱する
        
        Args:
            battle_id: 戦闘ID
            player_id: プレイヤーID
        """
        battle = self._get_battle_by_id(battle_id)
        player = self._get_player_by_id(player_id)
        
        # 戦闘から離脱
        battle.player_escape(player)
        
        # プレイヤー行動待機をキャンセル
        self._player_action_waiter.cancel_player_action_wait(battle_id, player_id)
        
        # イベント発行
        self._event_publisher.publish_all(battle.get_events())
        battle.clear_events()
        
        # 保存
        self._battle_repository.save(battle)
    
    def get_battle_status(self, battle_id: int) -> BattleStatusDto:
        """
        戦闘の状態を取得する
        
        Args:
            battle_id: 戦闘ID
            
        Returns:
            BattleStatusDto: 戦闘状態
        """
        battle = self._get_battle_by_id(battle_id)
        
        return BattleStatusDto(
            battle_id=battle.battle_id,
            is_active=battle.is_in_progress(),
            current_turn=battle._current_turn,
            current_round=battle._current_round,
            player_count=len(battle.get_player_ids()),
            monster_count=len(battle.get_monster_type_ids()),
            can_player_join=battle._state == battle._state.WAITING and len(battle.get_player_ids()) < battle._max_players
        )
    
    def get_player_action_waiter_statistics(self) -> dict:
        """
        プレイヤー行動待機の統計情報を取得（監視用）
        
        Returns:
            dict: 統計情報
        """
        return self._player_action_waiter.get_statistics()
    
    # プライベートヘルパーメソッド
    def _get_battle_by_id(self, battle_id: int) -> Battle:
        """戦闘を取得し、存在チェック"""
        battle = self._battle_repository.find_by_id(battle_id)
        if not battle:
            raise BattleNotFoundException()
        return battle
    
    def _get_player_by_id(self, player_id: int):
        """プレイヤーを取得し、存在チェック"""
        player = self._player_repository.find_by_id(player_id)
        if not player:
            raise ValueError(f"Player not found. player_id: {player_id}")
        return player
    
    def _validate_player_turn(self, battle: Battle, player_id: int) -> None:
        """現在のターンが正しいプレイヤーかチェック"""
        current_actor = battle.get_current_actor()
        participant_type, entity_id = current_actor.participant_key
        if (participant_type != ParticipantType.PLAYER or entity_id != player_id):
            raise ValueError(f"Invalid player turn. Expected: {entity_id}, Got: {player_id}")
    
    def _get_player_combat_state(self, battle: Battle, player_id: int):
        """プレイヤーの戦闘状態を取得"""
        player_combat_state = battle.get_combat_state(ParticipantType.PLAYER, player_id)
        if not player_combat_state:
            raise ValueError(f"Player combat state not found. player_id: {player_id}")
        return player_combat_state
    
    def _get_action_by_id(self, action_id: int):
        """アクションを取得し、存在チェック"""
        action = self._action_repository.find_by_id(action_id)
        if not action:
            raise ValueError(f"Action not found. action_id: {action_id}")
        return action
    
    def _resolve_specified_targets(self, battle: Battle, action_data: PlayerActionDto) -> List:
        """指定されたターゲットを解決"""
        specified_targets = []
        if action_data.target_ids and action_data.target_participant_types:
            for target_id, target_type in zip(action_data.target_ids, action_data.target_participant_types):
                target = battle.get_combat_state(target_type, target_id)
                if target:
                    specified_targets.append(target)
        return specified_targets
    
    def _register_event_handlers(self) -> None:
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
