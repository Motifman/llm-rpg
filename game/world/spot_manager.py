import json
import yaml
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
    
    # === マップ拡張機能 ===
    
    def extend_map_from_json(self, file_path: str):
        """JSONファイルからマップを拡張"""
        self.map_builder.load_from_json(file_path)
        # 既存のマップに統合（上書きではなく追加）
        self._extend_map_builder()
    
    def extend_map_from_yaml(self, file_path: str):
        """YAMLファイルからマップを拡張"""
        self.map_builder.load_from_yaml(file_path)
        # 既存のマップに統合（上書きではなく追加）
        self._extend_map_builder()
    
    def load_connections_from_json(self, file_path: str):
        """JSONファイルから接続のみを読み込み"""
        with open(file_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        self._load_connections_only(config)
    
    def load_connections_from_yaml(self, file_path: str):
        """YAMLファイルから接続のみを読み込み"""
        with open(file_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        self._load_connections_only(config)
    
    def _extend_map_builder(self):
        """MapBuilderの内容を既存のマップに追加統合"""
        # MovementGraphを統合
        builder_graph = self.map_builder.get_movement_graph()
        
        # スポットを統合（既存のスポットは上書きしない）
        for spot in builder_graph.get_all_spots():
            if not self.get_spot(spot.spot_id):  # 存在しない場合のみ追加
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
        
        # グループを統合（既存のグループは上書きしない）
        for group in self.map_builder.get_all_groups():
            if group.group_id not in self.groups:  # 存在しない場合のみ追加
                self.groups[group.group_id] = group
                # グループにスポットを追加
                for spot in group.get_all_spots():
                    group.add_spot(spot)
        
        # 出入り口を統合（既存の出入り口は上書きしない）
        for entrance in self.map_builder.get_all_entrances():
            if not self.entrance_manager.get_entrance(entrance.entrance_id):  # 存在しない場合のみ追加
                self.entrance_manager.add_entrance(entrance)
    
    def _load_connections_only(self, config: Dict):
        """接続のみを読み込み"""
        if 'connections' in config:
            for connection in config['connections']:
                # スポットが存在するかチェック
                if (self.get_spot(connection['from']) and 
                    self.get_spot(connection['to'])):
                    
                    # 接続が既に存在するかチェック
                    existing_destinations = self.get_destination_spot_ids(connection['from'])
                    if connection['to'] not in existing_destinations:
                        self.movement_graph.add_connection(
                            from_spot_id=connection['from'],
                            to_spot_id=connection['to'],
                            description=connection['description'],
                            is_bidirectional=connection.get('bidirectional', True),
                            conditions=connection.get('conditions'),
                            is_dynamic=connection.get('dynamic', False)
                        )
    
    def get_map_extension_summary(self) -> str:
        """マップ拡張の概要を取得"""
        summary = "=== マップ拡張機能概要 ===\n"
        summary += f"現在のスポット数: {len(self.get_all_spots())}\n"
        summary += f"現在のグループ数: {len(self.groups)}\n"
        summary += f"現在の接続数: {sum(len(edges) for edges in self.movement_graph.edges.values())}\n"
        
        summary += "\n=== グループ別スポット数 ===\n"
        for group in self.groups.values():
            summary += f"- {group.config.name}: {len(group.get_all_spots())}スポット\n"
        
        return summary
    
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
        
        # 出入り口を統合
        for entrance in self.map_builder.get_all_entrances():
            self.entrance_manager.add_entrance(entrance)
    
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
    
    # === spot_idから情報を取得する機能 ===
    
    def get_spot_location_info(self, spot_id: str) -> Dict[str, any]:
        """spot_idから位置情報を取得"""
        info = {
            "spot_id": spot_id,
            "spot": self.get_spot(spot_id),
            "groups": [],
            "entrances": [],
            "is_entrance_spot": False,
            "is_exit_spot": False
        }
        
        if not info["spot"]:
            return info
        
        # 所属グループを取得
        groups = self.get_groups_containing_spot(spot_id)
        info["groups"] = groups
        
        # 各グループでの役割を確認
        for group in groups:
            if group.is_entrance_spot(spot_id):
                info["is_entrance_spot"] = True
            if group.is_exit_spot(spot_id):
                info["is_exit_spot"] = True
        
        # 関連する出入り口を取得
        for group in groups:
            entrances = self.get_entrances_for_group(group.group_id)
            for entrance in entrances:
                if entrance.from_spot_id == spot_id or entrance.to_spot_id == spot_id:
                    info["entrances"].append(entrance)
        
        return info
    
    def get_spot_location_summary(self, spot_id: str) -> str:
        """spot_idから位置情報の概要を取得"""
        info = self.get_spot_location_info(spot_id)
        
        if not info["spot"]:
            return f"スポット {spot_id} は存在しません"
        
        summary = f"=== {info['spot'].name} ({spot_id}) ===\n"
        summary += f"説明: {info['spot'].description}\n"
        
        if info["groups"]:
            summary += f"\n所属グループ:\n"
            for group in info["groups"]:
                summary += f"- {group.config.name}: {group.config.description}\n"
                if group.is_entrance_spot(spot_id):
                    summary += f"  → このグループの入り口スポット\n"
                if group.is_exit_spot(spot_id):
                    summary += f"  → このグループの出口スポット\n"
        else:
            summary += f"\n所属グループ: なし\n"
        
        if info["entrances"]:
            summary += f"\n関連する出入り口:\n"
            for entrance in info["entrances"]:
                status = "🔒" if self.is_entrance_locked(entrance.entrance_id) else "🔓"
                direction = "↔" if entrance.is_bidirectional else "→"
                summary += f"- {status} {entrance.name} ({entrance.entrance_id})\n"
                summary += f"  {direction} {entrance.from_group_id}:{entrance.from_spot_id} → {entrance.to_group_id}:{entrance.to_spot_id}\n"
                summary += f"  {entrance.description}\n"
        else:
            summary += f"\n関連する出入り口: なし\n"
        
        # 移動可能なスポット
        destinations = self.get_destination_spot_ids(spot_id)
        if destinations:
            summary += f"\n移動可能なスポット:\n"
            for dest_id in destinations:
                dest_spot = self.get_spot(dest_id)
                if dest_spot:
                    summary += f"- {dest_spot.name} ({dest_id})\n"
        else:
            summary += f"\n移動可能なスポット: なし\n"
        
        return summary
    
    def get_available_exits_from_spot(self, spot_id: str) -> List[EntranceConfig]:
        """spot_idから利用可能な出口を取得"""
        info = self.get_spot_location_info(spot_id)
        available_exits = []
        
        for entrance in info["entrances"]:
            # ロックされていない出入り口のみ
            if not self.is_entrance_locked(entrance.entrance_id):
                available_exits.append(entrance)
        
        return available_exits
    
    def get_spot_group_hierarchy(self, spot_id: str) -> List[SpotGroup]:
        """spot_idの所属グループを階層順に取得（大きいグループから小さいグループへ）"""
        groups = self.get_groups_containing_spot(spot_id)
        
        # スポット数でソート（大きいグループから）
        groups.sort(key=lambda g: len(g.get_all_spots()), reverse=True)
        
        return groups