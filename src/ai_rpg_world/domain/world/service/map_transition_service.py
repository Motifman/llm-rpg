from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.exception.map_exception import SpotNotFoundException


class MapTransitionService:
    """マップ（スポット）間の遷移を管理するドメインサービス"""

    def transition_player(
        self,
        player_status: PlayerStatusAggregate,
        from_map: PhysicalMapAggregate,
        to_map: PhysicalMapAggregate,
        landing_coordinate: Coordinate
    ) -> None:
        """
        プレイヤーを現在のマップから別のマップへ遷移させる。
        
        Args:
            player_status: プレイヤーの状態集約
            from_map: 遷移元の物理マップ集約
            to_map: 遷移先の物理マップ集約
            landing_coordinate: 遷移先での着地座標
        """
        world_object_id = WorldObjectId.create(int(player_status.player_id))
        
        # 1. 元のマップからオブジェクトを取得・削除
        old_object = from_map.get_object(world_object_id)
        from_map.remove_object(world_object_id)
        
        # 2. 新しいマップにオブジェクトを追加
        # 既存のオブジェクト情報を引き継いで新しいマップ用のWorldObjectを作成
        new_object = WorldObject(
            object_id=world_object_id,
            coordinate=landing_coordinate,
            object_type=old_object.object_type,
            is_blocking=old_object.is_blocking,
            component=old_object.component,
            busy_until=old_object.busy_until
        )
        to_map.add_object(new_object)
        
        # 3. プレイヤー状態の更新
        player_status.update_location(to_map.spot_id, landing_coordinate)
        
        # 4. 経路情報のクリア（スポットが変わったため）
        player_status.clear_path()
