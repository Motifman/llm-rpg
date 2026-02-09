import logging
from typing import List, Callable, Any, Optional

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.service.behavior_service import BehaviorService
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException


class WorldSimulationApplicationService:
    """ワールド全体の進行・シミュレーションを管理するアプリケーションサービス"""
    
    def __init__(
        self,
        time_provider: GameTimeProvider,
        physical_map_repository: PhysicalMapRepository,
        behavior_service: BehaviorService,
        unit_of_work: UnitOfWork
    ):
        self._time_provider = time_provider
        self._physical_map_repository = physical_map_repository
        self._behavior_service = behavior_service
        self._unit_of_work = unit_of_work
        self._logger = logging.getLogger(self.__class__.__name__)

    def tick(self) -> WorldTick:
        """1ティック進め、世界の全ての要素を更新する"""
        return self._execute_with_error_handling(
            operation=lambda: self._tick_impl(),
            context={"action": "tick"}
        )

    def _tick_impl(self) -> WorldTick:
        with self._unit_of_work:
            # 1. ティックを進める
            current_tick = self._time_provider.advance_tick()
            
            # 2. マップを順番に処理
            maps = self._physical_map_repository.find_all()
            
            for physical_map in maps:
                # 3. マップ内のアクターの更新
                for actor in physical_map.actors:
                    # Busy状態のアクターはスキップ
                    if actor.is_busy(current_tick):
                        continue
                    
                    try:
                        # 自律行動アクターの計画
                        next_coord = self._behavior_service.plan_next_move(actor.object_id, physical_map)
                        if next_coord:
                            # 移動実行
                            physical_map.move_object(actor.object_id, next_coord, current_tick)
                    except Exception as e:
                        # 個別のアクターの更新失敗が全体に影響しないようにする
                        self._logger.error(
                            f"Failed to update actor {actor.object_id} in map {physical_map.spot_id}: {str(e)}",
                            exc_info=True
                        )
                
                # 4. マップの状態を保存
                self._physical_map_repository.save(physical_map)
                
                # 5. イベントの収集
                self._unit_of_work.add_events(physical_map.get_events())
                physical_map.clear_events()
            
            return current_tick

    def _execute_with_error_handling(self, operation: Callable[[], Any], context: dict) -> Any:
        try:
            return operation()
        except ApplicationException as e:
            raise e
        except DomainException as e:
            # ドメイン例外をアプリケーション例外に変換
            raise ApplicationException(str(e), cause=e, **context)
        except Exception as e:
            self._logger.error(f"Unexpected error in {context.get('action', 'unknown')}: {str(e)}",
                             extra=context)
            raise SystemErrorException(f"{context.get('action', 'unknown')} failed: {str(e)}",
                                     original_exception=e)
