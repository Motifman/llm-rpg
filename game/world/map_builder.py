import json
import yaml
from typing import Dict, List, Optional
from pathlib import Path
from game.world.spot import Spot
from game.world.spot_group import SpotGroup, SpotGroupConfig
from game.world.movement_graph import MovementGraph


class MapBuilder:
    """設定ファイルからマップを構築するクラス"""
    
    def __init__(self):
        self.spots: Dict[str, Spot] = {}
        self.groups: Dict[str, SpotGroup] = {}
        self.movement_graph = MovementGraph()
    
    def load_from_json(self, file_path: str) -> 'MapBuilder':
        """JSONファイルからマップ設定を読み込み"""
        with open(file_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return self._build_from_config(config)
    
    def load_from_yaml(self, file_path: str) -> 'MapBuilder':
        """YAMLファイルからマップ設定を読み込み"""
        with open(file_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return self._build_from_config(config)
    
    def _build_from_config(self, config: Dict) -> 'MapBuilder':
        """設定辞書からマップを構築"""
        # スポットの作成
        if 'spots' in config:
            for spot_config in config['spots']:
                spot = Spot(
                    spot_id=spot_config['id'],
                    name=spot_config['name'],
                    description=spot_config['description']
                )
                self.spots[spot.spot_id] = spot
                self.movement_graph.add_spot(spot)
        
        # グループの作成
        if 'groups' in config:
            for group_config in config['groups']:
                group_config_obj = SpotGroupConfig(
                    group_id=group_config['id'],
                    name=group_config['name'],
                    description=group_config['description'],
                    spot_ids=group_config['spot_ids'],
                    entrance_spot_ids=group_config.get('entrance_spot_ids'),
                    exit_spot_ids=group_config.get('exit_spot_ids'),
                    tags=group_config.get('tags')
                )
                group = SpotGroup(group_config_obj)
                self.groups[group.group_id] = group
                
                # グループにスポットを追加
                for spot_id in group_config['spot_ids']:
                    if spot_id in self.spots:
                        group.add_spot(self.spots[spot_id])
        
        # 接続の作成
        if 'connections' in config:
            for connection in config['connections']:
                self.movement_graph.add_connection(
                    from_spot_id=connection['from'],
                    to_spot_id=connection['to'],
                    description=connection['description'],
                    is_bidirectional=connection.get('bidirectional', True),
                    conditions=connection.get('conditions'),
                    is_dynamic=connection.get('dynamic', False)
                )
        
        return self
    
    def get_spot(self, spot_id: str) -> Optional[Spot]:
        """指定されたIDのSpotを取得"""
        return self.spots.get(spot_id)
    
    def get_all_spots(self) -> List[Spot]:
        """全てのSpotを取得"""
        return list(self.spots.values())
    
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
    
    def get_movement_graph(self) -> MovementGraph:
        """MovementGraphを取得"""
        return self.movement_graph
    
    def get_map_summary(self) -> str:
        """マップの概要を取得"""
        summary = "=== マップ概要 ===\n"
        summary += f"スポット数: {len(self.spots)}\n"
        summary += f"グループ数: {len(self.groups)}\n"
        summary += f"接続数: {sum(len(edges) for edges in self.movement_graph.edges.values())}\n\n"
        
        summary += "=== スポット一覧 ===\n"
        for spot in self.spots.values():
            summary += f"- {spot.spot_id}: {spot.name}\n"
        
        summary += "\n=== グループ一覧 ===\n"
        for group in self.groups.values():
            summary += group.get_summary() + "\n"
        
        return summary
    
    def validate_map(self) -> List[str]:
        """マップの整合性をチェック"""
        errors = []
        
        # グループ内のスポットが存在するかチェック
        for group in self.groups.values():
            for spot_id in group.config.spot_ids:
                if spot_id not in self.spots:
                    errors.append(f"グループ {group.config.name} に存在しないスポット {spot_id} が含まれています")
            
            # 入り口スポットがグループ内に存在するかチェック
            if group.config.entrance_spot_ids:
                for entrance_id in group.config.entrance_spot_ids:
                    if entrance_id not in group.config.spot_ids:
                        errors.append(f"グループ {group.config.name} の入り口スポット {entrance_id} がグループに含まれていません")
            
            # 出口スポットがグループ内に存在するかチェック
            if group.config.exit_spot_ids:
                for exit_id in group.config.exit_spot_ids:
                    if exit_id not in group.config.spot_ids:
                        errors.append(f"グループ {group.config.name} の出口スポット {exit_id} がグループに含まれていません")
        
        # MovementGraphの整合性チェック
        graph_errors = self.movement_graph.validate_graph()
        errors.extend(graph_errors)
        
        return errors 