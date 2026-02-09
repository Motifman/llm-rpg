from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.world.event.map_events import GatewayTriggeredEvent
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.world.service.map_transition_service import MapTransitionService
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

class GatewayTriggeredEventHandler(EventHandler[GatewayTriggeredEvent]):
    """ゲートウェイ通過時にマップ遷移を同期的に実行するハンドラ"""
    
    def __init__(
        self,
        physical_map_repository: PhysicalMapRepository,
        player_status_repository: PlayerStatusRepository,
        map_transition_service: MapTransitionService,
        event_publisher = None # 後で循環参照対策で検討
    ):
        self._physical_map_repository = physical_map_repository
        self._player_status_repository = player_status_repository
        self._map_transition_service = map_transition_service
        self._event_publisher = event_publisher

    def handle(self, event: GatewayTriggeredEvent):
        # 現時点では、全てのWorldObjectがプレイヤーと仮定されている設計を反映
        # (WorldObjectIdはPlayerIdのint値をラップしている)
        player_id_int = int(event.object_id)
        player_id = PlayerId(player_id_int)
        
        player_status = self._player_status_repository.find_by_id(player_id)
        if not player_status:
            # プレイヤー以外（NPCなど）がゲートウェイを通る可能性もあるが、
            # 現状はPlayerStatusAggregateが必要な設計
            return

        from_map = self._physical_map_repository.find_by_spot_id(event.spot_id)
        if not from_map:
            from ai_rpg_world.application.world.exceptions.command.movement_command_exception import MapNotFoundException
            raise MapNotFoundException(int(event.spot_id))

        to_map = self._physical_map_repository.find_by_spot_id(event.target_spot_id)
        if not to_map:
            from ai_rpg_world.application.world.exceptions.command.movement_command_exception import MapNotFoundException
            raise MapNotFoundException(int(event.target_spot_id))

        # 同期的なマップ遷移実行
        self._map_transition_service.transition_player(
            player_status, from_map, to_map, event.landing_coordinate
        )
        
        # 遷移先マップで発生したイベントを収集
        if self._event_publisher:
            self._event_publisher.publish_all(to_map.get_events())
        
        # リポジトリへの保存（同一トランザクション内）
        self._physical_map_repository.save(to_map)
        self._player_status_repository.save(player_status)
        # from_map は MovementApplicationService 側で保存される
