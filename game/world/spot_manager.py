from typing import List, Dict, Optional
from game.world.spot import Spot
from game.world.movement_graph import MovementGraph
from game.world.movement_cache import MovementCache
from game.world.movement_validator import MovementValidator
from game.world.spot_group import SpotGroup, SpotGroupConfig
from game.world.entrance_manager import EntranceManager, EntranceConfig
from game.world.map_builder import MapBuilder


class SpotManager:
    def __init__(self):
        self.movement_graph = MovementGraph()
        self.movement_cache = MovementCache(self.movement_graph)
        self.movement_validator = MovementValidator(self.movement_graph)
        self.groups: Dict[str, SpotGroup] = {}
        self.entrance_manager = EntranceManager()
        self.map_builder = MapBuilder()

    def add_spot(self, spot: Spot):
        self.movement_graph.add_spot(spot)

    def get_spot(self, spot_id: str) -> Spot:
        try:
            return self.movement_graph.get_spot(spot_id)
        except KeyError:
            return None
    
    def get_all_spots(self) -> List[Spot]:
        return list(self.movement_graph.get_all_spots())
    
    def get_movement_graph(self) -> MovementGraph:
        return self.movement_graph
    
    def get_movement_cache(self) -> MovementCache:
        return self.movement_cache
    
    def get_movement_validator(self) -> MovementValidator:
        return self.movement_validator

    def get_destination_spot_ids(self, spot_id: str) -> List[str]:
        return self.movement_graph.get_destination_spot_ids(spot_id)
    
    # === グループ管理機能 ===
    
    def create_group(self, config: SpotGroupConfig) -> SpotGroup:
        """新しいグループを作成"""
        group = SpotGroup(config)
        self.groups[config.group_id] = group
        return group
    
    def get_group(self, group_id: str) -> Optional[SpotGroup]:
        """指定されたIDのグループを取得"""
        return self.groups.get(group_id)
    
    def get_all_groups(self) -> List[SpotGroup]:
        """全てのグループを取得"""
        return list(self.groups.values())
    
    def get_groups_by_tag(self, tag: str) -> List[SpotGroup]:
        """指定されたタグを持つグループを取得"""
        return [group for group in self.groups.values() if group.has_tag(tag)]
    
    def get_groups_containing_spot(self, spot_id: str) -> List[SpotGroup]:
        """指定されたSpotを含むグループを取得"""
        return [group for group in self.groups.values() if group.has_spot(spot_id)]
    
    def add_spot_to_group(self, spot: Spot, group_id: str) -> bool:
        """Spotをグループに追加"""
        if group_id in self.groups:
            self.groups[group_id].add_spot(spot)
            return True
        return False
    
    # === 出入り口管理機能 ===
    
    def add_entrance(self, config: EntranceConfig):
        """出入り口を追加"""
        self.entrance_manager.add_entrance(config)
    
    def get_entrance(self, entrance_id: str) -> Optional[EntranceConfig]:
        """指定されたIDの出入り口を取得"""
        return self.entrance_manager.get_entrance(entrance_id)
    
    def get_entrances_for_group(self, group_id: str) -> List[EntranceConfig]:
        """指定されたグループの出入り口を取得"""
        return self.entrance_manager.get_entrances_for_group(group_id)
    
    def get_entrances_between_groups(self, from_group_id: str, to_group_id: str) -> List[EntranceConfig]:
        """2つのグループ間の出入り口を取得"""
        return self.entrance_manager.get_entrances_between_groups(from_group_id, to_group_id)
    
    def is_entrance_locked(self, entrance_id: str) -> bool:
        """出入り口がロックされているかチェック"""
        return self.entrance_manager.is_entrance_locked(entrance_id)
    
    def lock_entrance(self, entrance_id: str):
        """出入り口をロック"""
        self.entrance_manager.lock_entrance(entrance_id)
    
    def unlock_entrance(self, entrance_id: str):
        """出入り口のロックを解除"""
        self.entrance_manager.unlock_entrance(entrance_id)
    
    # === マップ構築機能 ===
    
    def load_map_from_json(self, file_path: str):
        """JSONファイルからマップを読み込み"""
        self.map_builder.load_from_json(file_path)
        # 構築されたマップをSpotManagerに統合
        self._integrate_map_builder()
    
    def load_map_from_yaml(self, file_path: str):
        """YAMLファイルからマップを読み込み"""
        self.map_builder.load_from_yaml(file_path)
        # 構築されたマップをSpotManagerに統合
        self._integrate_map_builder()
    
    def _integrate_map_builder(self):
        """MapBuilderの内容をSpotManagerに統合"""
        # MovementGraphを統合
        builder_graph = self.map_builder.get_movement_graph()
        
        # スポットを統合
        for spot in builder_graph.get_all_spots():
            if not self.get_spot(spot.spot_id):  # 重複を避ける
                self.add_spot(spot)
        
        # 接続を統合
        for spot_id in builder_graph.nodes:
            if spot_id in builder_graph.edges:
                for edge in builder_graph.edges[spot_id]:
                    # 接続が既に存在するかチェック
                    existing_destinations = self.get_destination_spot_ids(spot_id)
                    if edge.to_spot_id not in existing_destinations:
                        self.movement_graph.add_connection(
                            from_spot_id=edge.from_spot_id,
                            to_spot_id=edge.to_spot_id,
                            description=edge.description,
                            is_bidirectional=edge.is_bidirectional,
                            conditions=edge.conditions,
                            is_dynamic=edge.is_dynamic
                        )
        
        # グループを統合
        for group in self.map_builder.get_all_groups():
            self.groups[group.config.group_id] = group
            # グループにスポットを追加
            for spot in group.get_all_spots():
                group.add_spot(spot)
        
        # 出入り口を統合（MapBuilderからは直接取得できないので、別途設定が必要）
    
    def get_map_summary(self) -> str:
        """マップの概要を取得"""
        summary = "=== SpotManager マップ概要 ===\n"
        summary += f"スポット数: {len(self.get_all_spots())}\n"
        summary += f"グループ数: {len(self.groups)}\n"
        summary += f"出入り口数: {len(self.entrance_manager.entrances)}\n"
        
        summary += "\n=== グループ一覧 ===\n"
        for group in self.groups.values():
            summary += group.get_summary() + "\n"
        
        summary += "\n" + self.entrance_manager.get_entrance_summary()
        
        return summary
    
    def validate_map(self) -> List[str]:
        """マップの整合性をチェック"""
        errors = []
        
        # MovementGraphの整合性チェック
        graph_errors = self.movement_graph.validate_graph()
        errors.extend(graph_errors)
        
        # グループの整合性チェック
        for group in self.groups.values():
            for spot_id in group.config.spot_ids:
                if not self.get_spot(spot_id):
                    errors.append(f"グループ {group.config.name} に存在しないスポット {spot_id} が含まれています")
        
        # 出入り口の整合性チェック
        entrance_errors = self.entrance_manager.validate_entrances(self.groups)
        errors.extend(entrance_errors)
        
        return errors