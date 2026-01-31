from typing import Dict, Optional, List
from ai_rpg_world.domain.battle.battle import Battle
from ai_rpg_world.domain.battle.battle_repository import BattleRepository


class BattleRepositoryImpl(BattleRepository):
    """BattleRepositoryの実装クラス"""

    def __init__(self):
        # 実際の実装ではデータベース接続など
        # ここではメモリ上にデータを保持する簡易実装
        self._battles: Dict[int, Battle] = {}
        self._spot_battles: Dict[int, int] = {}  # spot_id -> battle_id
        self._next_id = 1

    def find_by_id(self, battle_id: int) -> Optional[Battle]:
        """戦闘IDで戦闘を検索"""
        return self._battles.get(battle_id)

    def find_by_spot_id(self, spot_id: int) -> Optional[Battle]:
        """スポットIDで戦闘を検索"""
        battle_id = self._spot_battles.get(spot_id)
        if battle_id:
            return self._battles.get(battle_id)
        return None

    def save(self, battle: Battle) -> None:
        """戦闘を保存"""
        if battle.battle_id not in self._battles:
            # 新しい戦闘の場合、IDを設定
            if battle.battle_id == 0:
                battle._battle_id = self.generate_battle_id()
        
        self._battles[battle.battle_id] = battle
        self._spot_battles[battle.spot_id] = battle.battle_id

    def delete(self, battle_id: int) -> None:
        """戦闘を削除"""
        if battle_id in self._battles:
            battle = self._battles[battle_id]
            del self._battles[battle_id]
            # スポットマッピングからも削除
            if battle.spot_id in self._spot_battles:
                del self._spot_battles[battle.spot_id]

    def find_all(self) -> List[Battle]:
        """全ての戦闘を取得"""
        return list(self._battles.values())

    def exists_by_id(self, battle_id: int) -> bool:
        """戦闘IDが存在するかチェック"""
        return battle_id in self._battles

    def count(self) -> int:
        """戦闘の総数を取得"""
        return len(self._battles)

    # テスト用のヘルパーメソッド
    def clear(self) -> None:
        """全ての戦闘を削除（テスト用）"""
        self._battles.clear()
        self._spot_battles.clear()
        self._next_id = 1

    def generate_battle_id(self) -> int:
        """新しい戦闘IDを生成（テスト用）"""
        battle_id = self._next_id
        self._next_id += 1
        return battle_id

    def find_by_ids(self, battle_ids: List[int]) -> List[Battle]:
        """複数の戦闘IDで戦闘を検索"""
        result = []
        for battle_id in battle_ids:
            battle = self._battles.get(battle_id)
            if battle:
                result.append(battle)
        return result
