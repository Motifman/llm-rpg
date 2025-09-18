"""
戦闘ループを管理するアプリケーションサービス

責務:
- 非同期戦闘ループの実行
- ターン進行の管理
- プレイヤー行動待機の制御
- モンスター行動の自動実行
"""
import asyncio
from typing import Optional, Dict, Set, Protocol
from src.domain.battle.battle import Battle
from src.domain.battle.battle_repository import BattleRepository
from src.domain.battle.battle_enum import ParticipantType
from src.domain.battle.battle_exception import BattleNotFoundException
from src.domain.battle.services.turn_processor import TurnProcessor
from src.domain.battle.services.monster_action_service import MonsterActionService
from src.domain.battle.action_repository import ActionRepository
from src.domain.common.event_publisher import EventPublisher


class PlayerActionWaiterProtocol(Protocol):
    """プレイヤー行動待機サービスのプロトコル"""
    
    async def wait_for_player_action(self, battle_id: int, player_id: int) -> bool:
        """プレイヤーの行動を待機"""
        ...


class BattleLoopService:
    """戦闘ループ管理アプリケーションサービス"""
    
    def __init__(
        self,
        battle_repository: BattleRepository,
        turn_processor: TurnProcessor,
        monster_action_service: MonsterActionService,
        action_repository: ActionRepository,
        event_publisher: EventPublisher,
        player_action_waiter: Optional[PlayerActionWaiterProtocol] = None
    ):
        self._battle_repository = battle_repository
        self._turn_processor = turn_processor
        self._monster_action_service = monster_action_service
        self._action_repository = action_repository
        self._event_publisher = event_publisher
        self._player_action_waiter = player_action_waiter
        
        # 実行中の戦闘ループを追跡
        self._running_battles: Set[int] = set()
        self._battle_loop_tasks: Dict[int, asyncio.Task] = {}
    
    async def start_battle_loop(self, battle_id: int) -> None:
        """
        戦闘ループを開始
        
        Args:
            battle_id: 戦闘ID
            
        Raises:
            BattleNotFoundException: 戦闘が見つからない場合
            ValueError: 戦闘が既に実行中の場合
        """
        if battle_id in self._running_battles:
            raise ValueError(f"Battle loop already running for battle_id: {battle_id}")
        
        battle = self._battle_repository.find_by_id(battle_id)
        if not battle:
            raise BattleNotFoundException(f"Battle not found: {battle_id}")
        
        if not battle.is_in_progress():
            raise ValueError(f"Battle is not in progress: {battle_id}")
        
        # 戦闘ループをバックグラウンドタスクとして実行
        task = asyncio.create_task(self._process_battle_loop(battle_id))
        self._battle_loop_tasks[battle_id] = task
        self._running_battles.add(battle_id)
        
        # タスクの完了時に自動的にクリーンアップ
        task.add_done_callback(lambda t: self._cleanup_battle_loop(battle_id))
    
    def stop_battle_loop(self, battle_id: int) -> None:
        """
        戦闘ループを停止
        
        Args:
            battle_id: 戦闘ID
        """
        if battle_id in self._battle_loop_tasks:
            task = self._battle_loop_tasks[battle_id]
            if not task.done():
                task.cancel()
            self._cleanup_battle_loop(battle_id)
    
    def is_battle_loop_running(self, battle_id: int) -> bool:
        """
        戦闘ループが実行中かどうか
        
        Args:
            battle_id: 戦闘ID
            
        Returns:
            bool: 実行中の場合True
        """
        return battle_id in self._running_battles
    
    async def _process_battle_loop(self, battle_id: int) -> None:
        """
        戦闘ループのメイン処理
        
        Args:
            battle_id: 戦闘ID
        """
        try:
            while True:
                battle = self._battle_repository.find_by_id(battle_id)
                if not battle or not battle.is_in_progress():
                    break
                
                # 単一ターンを処理
                battle_ended = await self._process_single_turn(battle)
                
                # 戦闘終了チェック
                if battle_ended:
                    break
                
                # ターン間の短い待機（システム負荷軽減）
                await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            # ループがキャンセルされた場合の処理
            pass
        except Exception as e:
            # エラーログを記録（実際の実装では適切なロガーを使用）
            print(f"Error in battle loop for battle_id {battle_id}: {e}")
        finally:
            self._cleanup_battle_loop(battle_id)
    
    async def _process_single_turn(self, battle: Battle) -> bool:
        """
        単一ターンを処理
        
        Args:
            battle: 戦闘エンティティ
            
        Returns:
            bool: 戦闘が終了した場合True
        """
        # ターンがロックされている場合は待機
        if battle.is_turn_locked():
            return False
        
        # ターン開始
        battle.start_turn()
        current_actor = battle.get_current_actor()
        
        # ターン開始処理
        turn_start_result = self._turn_processor.process_turn_start(battle, current_actor)
        
        # イベント発行
        self._event_publisher.publish_all(battle.get_events())
        battle.clear_events()
        
        # 戦闘終了チェック
        if self._turn_processor.check_and_handle_battle_end(battle):
            self._event_publisher.publish_all(battle.get_events())
            battle.clear_events()
            self._battle_repository.save(battle)
            return True
        
        # アクター行動処理
        if turn_start_result.can_act:
            participant_type, entity_id = current_actor.participant_key
            
            if participant_type == ParticipantType.PLAYER:
                # プレイヤーターン: ターンをロックして行動待機
                battle.lock_turn_for_player_action(entity_id)
                self._battle_repository.save(battle)
                await self._handle_player_turn(battle.battle_id, entity_id)
                # プレイヤー行動完了後の処理は execute_player_action で実行
                return False
            else:
                # モンスターターン: 自動実行
                self._execute_monster_action(battle, current_actor)
        
        # ターン終了処理（モンスターターンまたは行動不能な場合）
        if not battle.is_waiting_for_player_action():
            turn_end_result = self._turn_processor.process_turn_end(battle, current_actor)
            if battle.can_advance_turn():
                self._turn_processor.advance_turn(battle, turn_end_result)
        
        # イベント発行と保存
        self._event_publisher.publish_all(battle.get_events())
        battle.clear_events()
        self._battle_repository.save(battle)
        
        return False
    
    async def _handle_player_turn(self, battle_id: int, player_id: int) -> None:
        """
        プレイヤーターンの処理
        
        Args:
            battle_id: 戦闘ID
            player_id: プレイヤーID
        """
        if self._player_action_waiter:
            # 高度な待機システムを使用
            await self._player_action_waiter.wait_for_player_action(battle_id, player_id)
        else:
            # シンプルな待機（デモ用）
            await self._simple_player_action_wait(battle_id, player_id)
    
    async def _simple_player_action_wait(self, battle_id: int, player_id: int) -> None:
        """
        シンプルなプレイヤー行動待機（デモ用）
        
        実際の実装では、WebSocketやメッセージキューを使用して
        より効率的な待機システムを実装する
        
        Args:
            battle_id: 戦闘ID
            player_id: プレイヤーID
        """
        timeout_seconds = 30  # タイムアウト時間
        check_interval = 0.5  # チェック間隔
        elapsed_time = 0.0
        
        while elapsed_time < timeout_seconds:
            # 行動が実行されたかチェック
            # 実際の実装では、フラグやイベントを使用
            if self._check_player_action_executed(battle_id, player_id):
                return
            
            await asyncio.sleep(check_interval)
            elapsed_time += check_interval
        
        # タイムアウト時の処理（スキップなど）
        # 実際の実装では適切なデフォルト行動を実行
    
    def _check_player_action_executed(self, battle_id: int, player_id: int) -> bool:
        """
        プレイヤーの行動が実行されたかチェック（デモ用）
        
        実際の実装では、戦闘状態やイベントフラグを確認
        
        Args:
            battle_id: 戦闘ID
            player_id: プレイヤーID
            
        Returns:
            bool: 行動が実行された場合True
        """
        # デモ実装: 常にFalse（実際の実装で置き換える）
        return False
    
    def _execute_monster_action(self, battle: Battle, monster_actor) -> None:
        """
        モンスターの行動を実行
        
        Args:
            battle: 戦闘エンティティ
            monster_actor: モンスターアクター
        """
        try:
            participant_type, entity_id = monster_actor.participant_key
            monster_combat_state = battle.get_combat_state(participant_type, entity_id)
            
            if not monster_combat_state:
                raise ValueError(f"Monster combat state not found: {entity_id}")
            
            # 利用可能なアクションを取得
            available_actions = []
            for action_id in monster_combat_state.available_action_ids:
                action = self._action_repository.find_by_id(action_id)
                if action:
                    available_actions.append(action)
            
            if not available_actions:
                return  # 行動不能の場合はスキップ
            
            # モンスターの行動選択
            all_participants = list(battle.get_combat_states().values())
            action_and_targets = self._monster_action_service.select_monster_action_with_targets(
                monster_combat_state, available_actions, all_participants
            )
            
            if not action_and_targets:
                return  # 行動選択失敗の場合はスキップ
            
            selected_action, selected_targets = action_and_targets
            
            # アクション実行
            from src.domain.battle.battle_service import BattleLogicService
            # 実際の実装では依存性注入で取得
            battle_logic_service = BattleLogicService()
            
            battle_action_result = selected_action.execute(
                actor=monster_combat_state,
                specified_targets=selected_targets,
                context=battle_logic_service,
                all_participants=all_participants
            )
            
            # 結果適用
            battle.apply_battle_action_result(battle_action_result)
            battle.execute_turn(participant_type, entity_id, selected_action, battle_action_result)
            
        except Exception as e:
            # エラーログを記録（実際の実装では適切なロガーを使用）
            print(f"Monster action execution failed: {e}")
    
    def _cleanup_battle_loop(self, battle_id: int) -> None:
        """
        戦闘ループのクリーンアップ
        
        Args:
            battle_id: 戦闘ID
        """
        self._running_battles.discard(battle_id)
        if battle_id in self._battle_loop_tasks:
            del self._battle_loop_tasks[battle_id]
