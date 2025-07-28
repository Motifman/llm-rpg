from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from game.world.spot import Spot
from game.world.spot_group import SpotGroup


@dataclass
class EntranceConfig:
    """出入り口の設定を定義するデータクラス"""
    entrance_id: str
    name: str
    description: str
    from_group_id: str
    to_group_id: str
    from_spot_id: str
    to_spot_id: str
    conditions: Dict[str, any] = None
    is_bidirectional: bool = True
    is_locked: bool = False
    lock_conditions: Dict[str, any] = None


class EntranceManager:
    """出入り口を管理するクラス"""
    
    def __init__(self):
        self.entrances: Dict[str, EntranceConfig] = {}
        self.group_entrances: Dict[str, List[str]] = {}  # group_id -> entrance_ids
        self.locked_entrances: Set[str] = set()
    
    def add_entrance(self, config: EntranceConfig):
        """出入り口を追加"""
        self.entrances[config.entrance_id] = config
        
        # グループ別の出入り口管理
        if config.from_group_id not in self.group_entrances:
            self.group_entrances[config.from_group_id] = []
        if config.to_group_id not in self.group_entrances:
            self.group_entrances[config.to_group_id] = []
        
        self.group_entrances[config.from_group_id].append(config.entrance_id)
        if config.is_bidirectional:
            self.group_entrances[config.to_group_id].append(config.entrance_id)
        
        # ロック状態の管理
        if config.is_locked:
            self.locked_entrances.add(config.entrance_id)
    
    def get_entrance(self, entrance_id: str) -> Optional[EntranceConfig]:
        """指定されたIDの出入り口を取得"""
        return self.entrances.get(entrance_id)
    
    def get_entrances_for_group(self, group_id: str) -> List[EntranceConfig]:
        """指定されたグループの出入り口を取得"""
        entrance_ids = self.group_entrances.get(group_id, [])
        return [self.entrances[entrance_id] for entrance_id in entrance_ids]
    
    def get_entrances_between_groups(self, from_group_id: str, to_group_id: str) -> List[EntranceConfig]:
        """2つのグループ間の出入り口を取得"""
        entrances = []
        for entrance in self.entrances.values():
            if (entrance.from_group_id == from_group_id and entrance.to_group_id == to_group_id) or \
               (entrance.is_bidirectional and entrance.from_group_id == to_group_id and entrance.to_group_id == from_group_id):
                entrances.append(entrance)
        return entrances
    
    def get_entrance_by_spots(self, from_spot_id: str, to_spot_id: str) -> Optional[EntranceConfig]:
        """スポット間の出入り口を取得"""
        for entrance in self.entrances.values():
            if (entrance.from_spot_id == from_spot_id and entrance.to_spot_id == to_spot_id) or \
               (entrance.is_bidirectional and entrance.from_spot_id == to_spot_id and entrance.to_spot_id == from_spot_id):
                return entrance
        return None
    
    def is_entrance_locked(self, entrance_id: str) -> bool:
        """出入り口がロックされているかチェック"""
        return entrance_id in self.locked_entrances
    
    def lock_entrance(self, entrance_id: str):
        """出入り口をロック"""
        if entrance_id in self.entrances:
            self.locked_entrances.add(entrance_id)
    
    def unlock_entrance(self, entrance_id: str):
        """出入り口のロックを解除"""
        if entrance_id in self.locked_entrances:
            self.locked_entrances.remove(entrance_id)
    
    def get_available_entrances_for_group(self, group_id: str) -> List[EntranceConfig]:
        """指定されたグループの利用可能な出入り口を取得（ロックされていないもの）"""
        entrances = self.get_entrances_for_group(group_id)
        return [entrance for entrance in entrances if not self.is_entrance_locked(entrance.entrance_id)]
    
    def get_locked_entrances(self) -> List[EntranceConfig]:
        """ロックされている出入り口を取得"""
        return [self.entrances[entrance_id] for entrance_id in self.locked_entrances]
    
    def get_entrance_summary(self) -> str:
        """出入り口の概要を取得"""
        summary = "=== 出入り口一覧 ===\n"
        for entrance in self.entrances.values():
            status = "🔒" if self.is_entrance_locked(entrance.entrance_id) else "🔓"
            direction = "↔" if entrance.is_bidirectional else "→"
            summary += f"{status} {entrance.name} ({entrance.entrance_id})\n"
            summary += f"  {direction} {entrance.from_group_id}:{entrance.from_spot_id} → {entrance.to_group_id}:{entrance.to_spot_id}\n"
            summary += f"  {entrance.description}\n"
            if entrance.conditions:
                summary += f"  条件: {entrance.conditions}\n"
            summary += "\n"
        return summary
    
    def validate_entrances(self, groups: Dict[str, SpotGroup]) -> List[str]:
        """出入り口の整合性をチェック"""
        errors = []
        
        for entrance in self.entrances.values():
            # グループが存在するかチェック
            if entrance.from_group_id not in groups:
                errors.append(f"出入り口 {entrance.entrance_id} のfrom_group_id {entrance.from_group_id} が存在しません")
            if entrance.to_group_id not in groups:
                errors.append(f"出入り口 {entrance.entrance_id} のto_group_id {entrance.to_group_id} が存在しません")
            
            # スポットがグループに含まれているかチェック
            if entrance.from_group_id in groups:
                from_group = groups[entrance.from_group_id]
                if not from_group.has_spot(entrance.from_spot_id):
                    errors.append(f"出入り口 {entrance.entrance_id} のfrom_spot_id {entrance.from_spot_id} がグループ {entrance.from_group_id} に含まれていません")
            
            if entrance.to_group_id in groups:
                to_group = groups[entrance.to_group_id]
                if not to_group.has_spot(entrance.to_spot_id):
                    errors.append(f"出入り口 {entrance.entrance_id} のto_spot_id {entrance.to_spot_id} がグループ {entrance.to_group_id} に含まれていません")
        
        return errors 