"""
InMemoryBattleRepository - 実際のBattleクラスを使用するインメモリ実装
"""
from typing import List, Optional, Dict
from src.domain.battle.battle_repository import BattleRepository
from src.domain.battle.battle import Battle


class InMemoryBattleRepository(BattleRepository):
    """実際のBattleクラスを使用するインメモリリポジトリ"""
    
    def __init__(self):
        self._battles: Dict[int, Battle] = {}
        self._spot_to_battle: Dict[int, int] = {}  # spot_id -> battle_id のマッピング
        self._next_id = 1
    
    def find_by_id(self, battle_id: int) -> Optional[Battle]:
        """戦闘IDで戦闘を検索"""
        return self._battles.get(battle_id)
    
    def find_by_ids(self, battle_ids: List[int]) -> List[Battle]:
        """複数の戦闘IDで戦闘を検索"""
        result = []
        for battle_id in battle_ids:
            battle = self._battles.get(battle_id)
            if battle:
                result.append(battle)
        return result
    
    def find_by_spot_id(self, spot_id: int) -> Optional[Battle]:
        """スポットIDで戦闘を検索"""
        battle_id = self._spot_to_battle.get(spot_id)
        if battle_id:
            return self._battles.get(battle_id)
        return None
    
    def find_active_battles(self) -> List[Battle]:
        """アクティブな戦闘を検索"""
        return [battle for battle in self._battles.values()
                if battle.is_in_progress()]
    
    def find_by_player_id(self, player_id: int) -> List[Battle]:
        """プレイヤーIDで戦闘を検索"""
        result = []
        for battle in self._battles.values():
            if player_id in battle.get_player_ids():
                result.append(battle)
        return result
    
    def find_all(self) -> List[Battle]:
        """全ての戦闘を取得"""
        return list(self._battles.values())
    
    def save(self, battle: Battle) -> Battle:
        """戦闘を保存"""
        self._battles[battle.battle_id] = battle
        self._spot_to_battle[battle.spot_id] = battle.battle_id
        return battle
    
    def delete(self, battle_id: int) -> bool:
        """戦闘を削除"""
        if battle_id in self._battles:
            battle = self._battles[battle_id]
            # スポットマッピングからも削除
            if battle.spot_id in self._spot_to_battle:
                del self._spot_to_battle[battle.spot_id]
            del self._battles[battle_id]
            return True
        return False
    
    def exists_by_id(self, battle_id: int) -> bool:
        """戦闘IDが存在するかチェック"""
        return battle_id in self._battles
    
    def count(self) -> int:
        """戦闘の総数を取得"""
        return len(self._battles)
    
    def generate_battle_id(self) -> int:
        """新しい戦闘IDを生成"""
        battle_id = self._next_id
        self._next_id += 1
        return battle_id
    
    # テスト用のヘルパーメソッド
    def clear(self) -> None:
        """全ての戦闘を削除（テスト用）"""
        self._battles.clear()
        self._spot_to_battle.clear()
        self._next_id = 1
    
    def count_active_battles(self) -> int:
        """アクティブな戦闘数を取得"""
        return len(self.find_active_battles())
    
    def count_battles_in_spot(self, spot_id: int) -> int:
        """指定されたスポットの戦闘数を取得"""
        return 1 if spot_id in self._spot_to_battle else 0
